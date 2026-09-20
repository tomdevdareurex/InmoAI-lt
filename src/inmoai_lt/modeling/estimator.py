"""Assemble the estimator: geo-neighbour KNN stacked under CatBoost.

Mirrors the reference notebook's structure -- a ``StackingRegressor`` whose single base
learner is a KNN over coordinates and whose final estimator is CatBoost, with
``passthrough=True`` so CatBoost sees the original features alongside the neighbour estimate.

Stacking is what makes the neighbour feature safe: sklearn cross-fits base learners, so a
row's own price never feeds the neighbour value used to train on that row.
"""

from __future__ import annotations

from catboost import CatBoostRegressor
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import StackingRegressor
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline

from .config import ModelConfig
from .features import AREA_COLUMN, FeatureSpec
from .target import TargetTransform
from .transformers import GeoNeighbourRegressor, PricePerAreaTargetEncoder


def build_estimator(
    spec: FeatureSpec,
    transform: TargetTransform,
    config: ModelConfig,
) -> Pipeline:
    """Two steps: preprocess categoricals, then the stacked regressor."""
    preprocessor = ColumnTransformer(
        transformers=[
            # The area column rides along so the encoder can normalise by it; it is
            # emitted by the numeric branch, not this one, so it appears exactly once.
            (
                "categorical",
                PricePerAreaTargetEncoder(AREA_COLUMN, random_state=config.random_seed),
                list(spec.categorical) + [AREA_COLUMN],
            ),
            ("numeric", "passthrough", list(spec.numeric)),
        ],
        verbose_feature_names_out=False,
    ).set_output(transform="pandas")

    # Trees are scale-invariant, so unlike the reference notebook there is no StandardScaler
    # here: scaling the features or the target would leave CatBoost's predictions unchanged.
    final_estimator = CatBoostRegressor(
        **config.catboost,
        random_state=config.random_seed,
        verbose=False,
        allow_writing_files=False,
    )

    stack = StackingRegressor(
        estimators=[
            (
                "geo_neighbours",
                GeoNeighbourRegressor(AREA_COLUMN, transform, config.n_neighbors),
            )
        ],
        final_estimator=final_estimator,
        passthrough=True,
        cv=KFold(n_splits=config.stacking_cv, shuffle=True, random_state=config.random_seed),
    )

    return Pipeline([("preprocess", preprocessor), ("stack", stack)])
