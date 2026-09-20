"""Load a cleaned segment and shape it into model inputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..config import REPO_ROOT
from .features import AREA_COLUMN, PRICE_COLUMN, FeatureSpec, features_for

SEGMENTS = ("apartment_sale", "apartment_rent", "house_sale", "house_rent")

_UNKNOWN_CATEGORY = "unknown"


def segment_path(segment: str, processed_dir: Path | None = None) -> Path:
    processed_dir = processed_dir or (REPO_ROOT / "data" / "processed")
    return processed_dir / "segments" / f"{segment}_analysis.csv"


def split_segment(segment: str) -> tuple[str, str]:
    """``apartment_sale`` -> ``("apartment", "sale")``."""
    if segment not in SEGMENTS:
        raise ValueError(f"unknown segment {segment!r}; expected one of {SEGMENTS}")
    property_type, listing_type = segment.rsplit("_", 1)
    return property_type, listing_type


def load_segment(segment: str, processed_dir: Path | None = None) -> pd.DataFrame:
    """Read one cleaned segment file. Run `python -m inmoai_lt clean` first."""
    path = segment_path(segment, processed_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run `python -m inmoai_lt clean` to generate segment files"
        )
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def build_feature_frame(df: pd.DataFrame, spec: FeatureSpec) -> pd.DataFrame:
    """Select the model columns and coerce them to dtypes the pipeline expects.

    Booleans become floats so the whole numeric block is one float matrix (CatBoost reads
    NaN natively, so missing values are left as-is). Categoricals become strings with an
    explicit "unknown" level, because energy_class is only 16-31% populated and NaN needs to
    be a category the target encoder can learn from rather than an error.
    """
    missing = [column for column in spec.all_columns if column not in df.columns]
    if missing:
        raise KeyError(f"segment frame is missing expected columns: {missing}")

    numeric = df[list(spec.numeric)].apply(pd.to_numeric, errors="coerce").astype("float64")
    categorical = df[list(spec.categorical)].astype("object").fillna(_UNKNOWN_CATEGORY).astype(str)
    return pd.concat([numeric, categorical], axis=1)


def build_target(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return ``(price_eur, total_area_sqm)`` as floats."""
    price = pd.to_numeric(df[PRICE_COLUMN], errors="coerce").astype("float64")
    area = pd.to_numeric(df[AREA_COLUMN], errors="coerce").astype("float64")
    return price, area


def prepare(
    segment: str, df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.Series, pd.Series, FeatureSpec]:
    """One call to get everything a model needs: ``(X, price, area, spec)``."""
    property_type, _ = split_segment(segment)
    spec = features_for(property_type)
    features = build_feature_frame(df, spec)
    price, area = build_target(df)
    return features, price, area, spec
