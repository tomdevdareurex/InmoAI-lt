"""One trained price model for one segment: train, predict, evaluate, save, load.

The same class serves all four segments. What differs between them -- the feature list and
the neighbour settings -- is looked up from the segment name, so there is no per-segment code.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.model_selection import train_test_split

from .config import ModelConfig, load_model_config
from .dataset import load_segment, prepare, split_segment
from .estimator import build_estimator
from .features import FeatureSpec
from .metrics import regression_metrics
from .target import TargetTransform, target_transform


@dataclass
class SegmentModel:
    """A fitted pipeline plus the metadata needed to reuse and trust it."""

    segment: str
    property_type: str
    listing_type: str
    target: str
    feature_spec: FeatureSpec
    pipeline: Any
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def low_n(self) -> bool:
        """True when the segment was too small to trust; propagates into cap rates."""
        return bool(self.metadata.get("low_n", False))

    # ---------------------------------------------------------------- training

    @classmethod
    def train(
        cls,
        segment: str,
        df: pd.DataFrame | None = None,
        config: ModelConfig | None = None,
    ) -> SegmentModel:
        """Fit on a train split and score on a held-out split.

        The saved model is the one fitted on the train split, so ``metrics`` describes
        exactly the object you later load -- not a differently-fitted refit.
        """
        config = (config or load_model_config()).for_segment(segment)
        property_type, listing_type = split_segment(segment)
        frame = load_segment(segment) if df is None else df

        features, price, area, spec = prepare(segment, frame)
        transform = target_transform(config.target)

        idx_train, idx_test = train_test_split(
            np.arange(len(features)),
            test_size=config.test_size,
            random_state=config.random_seed,
        )

        y_model = transform.forward(price.to_numpy(), area.to_numpy())
        pipeline = build_estimator(spec, transform, config)
        pipeline.fit(features.iloc[idx_train], y_model[idx_train])

        model = cls(
            segment=segment,
            property_type=property_type,
            listing_type=listing_type,
            target=config.target,
            feature_spec=spec,
            pipeline=pipeline,
            metadata={
                "n_train": len(idx_train),
                "n_test": len(idx_test),
                # Positional indices of the held-out rows, so the same rows can be re-scored
                # later (e.g. to plot predicted vs actual) without redoing the split.
                "test_index": idx_test.tolist(),
                "low_n": len(idx_train) < config.low_n_threshold,
                "n_neighbors": config.n_neighbors,
                "stacking_cv": config.stacking_cv,
                "catboost": dict(config.catboost),
                "random_seed": config.random_seed,
                # Lets cap-rate reporting warn when scoring districts never seen in training.
                "districts_seen": sorted(features["district"].unique().tolist()),
                "trained_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "sklearn_version": sklearn.__version__,
            },
        )

        predicted = model._predict_frame(features.iloc[idx_test], area.iloc[idx_test])
        model.metrics = regression_metrics(price.iloc[idx_test].to_numpy(), predicted)
        return model

    # -------------------------------------------------------------- prediction

    def _predict_frame(self, features: pd.DataFrame, area: pd.Series) -> np.ndarray:
        raw = self.pipeline.predict(features)
        transform: TargetTransform = target_transform(self.target)
        return np.asarray(transform.inverse(raw, area.to_numpy()), dtype=float)

    def predict(self, listings: pd.DataFrame, as_target_unit: bool = False) -> np.ndarray:
        """Predict price in EUR (EUR/month for rent segments).

        Always returns EUR regardless of the configured target, so the three target modes
        stay comparable. Set ``as_target_unit=True`` to inspect the untransformed model
        output instead (e.g. EUR/sqm when target is ``price_per_sqm``).

        ``listings`` is a cleaned segment frame. It does not have to come from this model's
        own segment -- passing sale listings to a rent model is exactly how cross-prediction
        works.
        """
        from .dataset import build_feature_frame, build_target

        features = build_feature_frame(listings, self.feature_spec)
        _, area = build_target(listings)
        if as_target_unit:
            return np.asarray(self.pipeline.predict(features), dtype=float)
        return self._predict_frame(features, area)

    def evaluate(self, listings: pd.DataFrame) -> dict[str, float]:
        """Score this model against any labelled frame, in EUR."""
        from .dataset import build_target

        price, _ = build_target(listings)
        return regression_metrics(price.to_numpy(), self.predict(listings))

    # ------------------------------------------------------------- persistence

    def save(self, models_dir: Path | None = None) -> Path:
        models_dir = models_dir or load_model_config().models_dir
        models_dir.mkdir(parents=True, exist_ok=True)
        path = models_dir / f"{self.segment}.joblib"
        joblib.dump(self, path)
        return path

    @classmethod
    def load(cls, segment_or_path: str | Path, models_dir: Path | None = None) -> SegmentModel:
        """Load by segment name (``"apartment_sale"``) or by explicit path."""
        path = Path(segment_or_path)
        if path.suffix != ".joblib":
            models_dir = models_dir or load_model_config().models_dir
            path = models_dir / f"{segment_or_path}.joblib"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found -- train and save the model first")
        return joblib.load(path)


def train_all(
    segments: tuple[str, ...] | None = None,
    config: ModelConfig | None = None,
    save: bool = True,
) -> dict[str, SegmentModel]:
    """Train every segment model and optionally persist them."""
    from .dataset import SEGMENTS

    models: dict[str, SegmentModel] = {}
    for segment in segments or SEGMENTS:
        model = SegmentModel.train(segment, config=config)
        if save:
            model.save()
        models[segment] = model
    return models
