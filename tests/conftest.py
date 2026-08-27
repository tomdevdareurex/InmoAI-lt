"""Shared pytest fixtures: config/mappings loading and a synthetic raw-data directory."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from inmoai_lt.config import REPO_ROOT

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def synthetic_raw_dir(tmp_path: Path) -> Path:
    """A `data/raw`-shaped directory containing only the synthetic fixture CSV."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    shutil.copyfile(
        FIXTURES_DIR / "synthetic_listings.csv", raw_dir / "synthetic_listings.csv"
    )
    return raw_dir


@pytest.fixture
def synthetic_cleaning_config() -> dict:
    """A `cleaning.yaml`-shaped dict pointed at the single synthetic source file.

    Reuses every threshold from the real `config/cleaning.yaml` (loaded fresh so tests
    never mutate shared state) but overrides `input.sources` to the one synthetic file,
    which already carries correct per-row `property_type`/`listing_type` values (a mix
    of apartment and house rows), matching how the real source CSVs are structured.
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
    ]
    return cleaning


@pytest.fixture
def mappings() -> dict:
    import yaml

    with (REPO_ROOT / "config" / "mappings_lt_en.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
