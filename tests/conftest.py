"""Shared pytest fixtures: config/mappings loading and synthetic raw and segment data."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from inmoai_lt.config import REPO_ROOT
from inmoai_lt.modeling import ModelConfig, features_for, load_model_config

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

_DISTRICTS = ("Alpha", "Beta", "Gamma", "Delta")
_PRICE_PER_SQM_BY_DISTRICT = {"Alpha": 4200.0, "Beta": 3100.0, "Gamma": 2400.0, "Delta": 5000.0}
_RENT_PER_SQM = 0.004  # monthly rent as a fraction of sale price per sqm


@pytest.fixture
def synthetic_raw_dir(tmp_path: Path) -> Path:
    """A `data/raw`-shaped directory containing only the synthetic fixture CSV."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for name in ("synthetic_listings.csv", "synthetic_rent_listings.csv"):
        shutil.copyfile(FIXTURES_DIR / name, raw_dir / name)
    return raw_dir


@pytest.fixture
def synthetic_cleaning_config() -> dict:
    """A `cleaning.yaml`-shaped dict pointed at the single synthetic source file.

    Reuses every threshold from the real `config/cleaning.yaml` (loaded fresh so tests
    never mutate shared state) but overrides `input.sources` to the synthetic files,
    which already carry correct per-row `property_type`/`listing_type` values (a mix of
    apartment, house and rent rows), matching how the real source CSVs are structured.
    """
    import yaml

    with (REPO_ROOT / "config" / "cleaning.yaml").open("r", encoding="utf-8") as f:
        cleaning = yaml.safe_load(f)
    cleaning["input"]["sources"] = [
        {
            "file": "synthetic_listings.csv",
            "property_type": "apartment",
            "listing_type": "sale",
            "enabled": True,
        },
        {
            "file": "synthetic_rent_listings.csv",
            "property_type": "apartment",
            "listing_type": "rent",
            "enabled": True,
        },
    ]
    return cleaning


@pytest.fixture
def make_segment_frame() -> Callable[..., pd.DataFrame]:
    """Build a frame shaped like `data/processed/segments/<segment>_analysis.csv`.

    Price is a deterministic function of area and district so a model can actually learn
    something, but these fixtures exist to exercise plumbing (units, persistence, cap-rate
    arithmetic), not to say anything about accuracy.
    """

    def _make(
        property_type: str = "apartment",
        listing_type: str = "sale",
        n: int = 200,
        seed: int = 0,
        districts: tuple[str, ...] = _DISTRICTS,
    ) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        spec = features_for(property_type)

        district = rng.choice(np.array(districts), n)
        area = rng.uniform(25.0, 130.0, n)

        frame = pd.DataFrame(
            {column: rng.uniform(0.0, 1.0, n) for column in spec.numeric}
            | {column: rng.choice(np.array(["a", "b"]), n) for column in spec.categorical}
        )
        frame["total_area_sqm"] = area
        frame["rooms"] = rng.integers(1, 5, n).astype(float)
        frame["latitude"] = 54.68 + rng.uniform(-0.05, 0.05, n)
        frame["longitude"] = 25.28 + rng.uniform(-0.05, 0.05, n)
        frame["district"] = district

        per_sqm = np.array([_PRICE_PER_SQM_BY_DISTRICT.get(d, 3000.0) for d in district])
        price = area * per_sqm * rng.uniform(0.9, 1.1, n)
        if listing_type == "rent":
            price = price * _RENT_PER_SQM

        frame["price_eur"] = price.round(2)
        frame["listing_id"] = [f"{property_type[:1]}-{i}" for i in range(n)]
        frame["property_type"] = property_type
        frame["listing_type"] = listing_type
        return frame

    return _make


@pytest.fixture
def fast_config() -> ModelConfig:
    """The real config shrunk so training a test model takes a fraction of a second."""
    return replace(
        load_model_config(),
        catboost={"n_estimators": 30, "max_depth": 4, "learning_rate": 0.3},
        n_neighbors=5,
        stacking_cv=2,
        per_segment={},
    )


@pytest.fixture
def mappings() -> dict:
    import yaml

    with (REPO_ROOT / "config" / "mappings_lt_en.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
