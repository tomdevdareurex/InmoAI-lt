"""Custom sklearn steps, adapted from InmoAI/models/pipeline_classes.py.

The Chilean original normalised by ``suputilval`` (useful surface); the Lithuanian
equivalent is ``total_area_sqm``. Two ideas are carried over:

* encode a categorical by the mean *price per sqm* of its rows, not the mean price, so a
  district full of large flats is not mistaken for an expensive one;
* estimate a local price level from the nearest listings by geographic distance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin
from sklearn.model_selection import KFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import TargetEncoder

from .target import TargetTransform

_ENCODER_FOLDS = 5


class PricePerAreaTargetEncoder(BaseEstimator, TransformerMixin):
    """Target-encode categoricals against price-per-sqm.

    Port of ``TargetPerSuputilvalEncoder``. Receives the categorical columns *plus* the area
    column (needed to normalise the target) and emits only the encoded categoricals.
    Unseen categories fall back to the global mean, which is what makes the rent model
    usable on sale listings from districts it never saw during training.
    """

    def __init__(self, area_column: str, random_state: int = 42):
        self.area_column = area_column
        self.random_state = random_state

    def _split(self, X: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        categoricals = X.drop(columns=[self.area_column])
        return categoricals, X[self.area_column]

    def _new_encoder(self) -> TargetEncoder:
        # Seed via an explicit KFold: TargetEncoder's own `random_state` is deprecated.
        return TargetEncoder(
            target_type="continuous",
            cv=KFold(n_splits=_ENCODER_FOLDS, shuffle=True, random_state=self.random_state),
        )

    def fit(self, X: pd.DataFrame, y=None):
        categoricals, area = self._split(X)
        self.feature_names_out_ = list(categoricals.columns)
        self.encoder_ = self._new_encoder()
        self.encoder_.fit(categoricals, np.asarray(y) / np.asarray(area))
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        categoricals, _ = self._split(X)
        encoded = self.encoder_.transform(categoricals)
        return pd.DataFrame(encoded, columns=self.feature_names_out_, index=X.index)

    def fit_transform(self, X: pd.DataFrame, y=None, **fit_params) -> pd.DataFrame:
        # TargetEncoder.fit_transform cross-fits internally to avoid leaking the target
        # into the training rows; that is why this is not just fit().transform().
        categoricals, area = self._split(X)
        self.feature_names_out_ = list(categoricals.columns)
        self.encoder_ = self._new_encoder()
        encoded = self.encoder_.fit_transform(categoricals, np.asarray(y) / np.asarray(area))
        return pd.DataFrame(encoded, columns=self.feature_names_out_, index=X.index)

    def get_feature_names_out(self, input_features=None) -> np.ndarray:
        return np.asarray(self.feature_names_out_, dtype=object)


class GeoNeighbourRegressor(RegressorMixin, BaseEstimator):
    """Local price-per-sqm from the k nearest listings by great-circle distance.

    Port of the notebook's ``TargetPerSuputilvalRegressor(KNeighborsRegressor(30,
    metric="haversine"))`` -- the "neighbours percentages" feature. Used as a base learner
    inside a ``StackingRegressor``, which cross-fits it so a row never contributes to its
    own neighbour estimate.

    Predicts on a per-sqm basis in the target's own space; the final estimator combines that
    with the raw features.
    """

    def __init__(self, area_column: str, transform: TargetTransform, n_neighbors: int = 30):
        self.area_column = area_column
        self.transform = transform
        self.n_neighbors = n_neighbors

    def _coordinates(self, X: pd.DataFrame) -> np.ndarray:
        # haversine expects radians, not degrees.
        return np.radians(X[["latitude", "longitude"]].to_numpy(dtype=float))

    def fit(self, X: pd.DataFrame, y):
        area = X[self.area_column].to_numpy(dtype=float)
        y_per_sqm = self.transform.to_per_sqm(np.asarray(y, dtype=float), area)

        # ball_tree is the only algorithm supporting the haversine metric; "auto" may pick
        # kd_tree and fail. Uniform weights (sklearn's default, as in the reference
        # notebook): many listings share a building and so share exact coordinates, which
        # would give distance weighting an infinite weight on a single neighbour.
        self.knn_ = KNeighborsRegressor(
            n_neighbors=min(self.n_neighbors, len(X)),
            metric="haversine",
            algorithm="ball_tree",
        )
        self.knn_.fit(self._coordinates(X), y_per_sqm)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.knn_.predict(self._coordinates(X))
