"""The feature lists must name columns that the cleaning pipeline actually produces."""

from __future__ import annotations

import pandas as pd
import pytest

from inmoai_lt.modeling import SEGMENTS, features_for, split_segment
from inmoai_lt.modeling.dataset import segment_path
from inmoai_lt.modeling.features import AREA_COLUMN, PRICE_COLUMN

LEAKY_COLUMNS = ("price_eur", "price_per_sqm_eur", "views_count", "listing_age_days")


def test_apartment_and_house_share_the_common_features():
    apartment = set(features_for("apartment").all_columns)
    house = set(features_for("house").all_columns)
    assert {"district", AREA_COLUMN, "latitude", "longitude"} <= apartment & house


def test_property_types_get_their_own_exclusive_features():
    apartment = set(features_for("apartment").all_columns)
    house = set(features_for("house").all_columns)
    assert {"floor", "balcony"} <= apartment - house
    assert {"plot_area_sqm", "house_type"} <= house - apartment


def test_no_feature_leaks_the_target_or_describes_the_advertisement():
    for property_type in ("apartment", "house"):
        assert not set(features_for(property_type).all_columns) & set(LEAKY_COLUMNS)


def test_unknown_property_type_is_rejected():
    with pytest.raises(ValueError, match="unknown property_type"):
        features_for("garage")


@pytest.mark.parametrize("segment", SEGMENTS)
def test_features_exist_in_the_real_segment_file(segment: str):
    """Guards against the cleaning schema and the feature lists drifting apart."""
    path = segment_path(segment)
    if not path.exists():
        pytest.skip(f"{path.name} not generated; run `python -m inmoai_lt clean`")

    property_type, _ = split_segment(segment)
    columns = set(pd.read_csv(path, encoding="utf-8-sig", nrows=1).columns)
    expected = set(features_for(property_type).all_columns) | {PRICE_COLUMN}
    assert expected <= columns
