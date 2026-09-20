from __future__ import annotations

import pandas as pd

from inmoai_lt.cleaning.derive import add_derived_features

_REFERENCE_DATE = pd.Timestamp("2026-08-25", tz="UTC")


def _base_row(**overrides):
    row = {
        "property_type": "apartment",
        "listing_type": "sale",
        "construction_year": 2000,
        "renovation_year": None,
        "floor": 3,
        "total_floors": 9,
        "rooms": 2,
        "total_area_sqm": 50.0,
        "plot_area_sqm": None,
        "water_body": None,
        "listing_updated_date": "2026-08-20",
        "security_features": [],
    }
    row.update(overrides)
    return row


class TestBuildingAgeYears:
    def test_uses_reference_date_not_wall_clock(self):
        df = pd.DataFrame([_base_row(construction_year=2000)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert out.loc[0, "building_age_years"] == 26  # 2026 - 2000, exact

    def test_clipped_at_zero_for_future_build(self):
        df = pd.DataFrame([_base_row(construction_year=2028)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert out.loc[0, "building_age_years"] == 0


class TestEffectiveYear:
    def test_uses_renovation_when_later(self):
        df = pd.DataFrame([_base_row(construction_year=1960, renovation_year=2020)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert out.loc[0, "effective_year"] == 2020

    def test_falls_back_to_construction_when_no_renovation(self):
        df = pd.DataFrame([_base_row(construction_year=1960, renovation_year=None)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert out.loc[0, "effective_year"] == 1960


class TestIsNewBuild:
    def test_true_when_construction_year_ge_reference_year(self):
        df = pd.DataFrame([_base_row(construction_year=2027)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert bool(out.loc[0, "is_new_build"]) is True

    def test_false_for_old_build(self):
        df = pd.DataFrame([_base_row(construction_year=1990)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert bool(out.loc[0, "is_new_build"]) is False


class TestFloorDerived:
    def test_floor_ratio(self):
        df = pd.DataFrame([_base_row(floor=3, total_floors=9)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert abs(out.loc[0, "floor_ratio"] - (3 / 9)) < 1e-9

    def test_is_ground_floor(self):
        df = pd.DataFrame([_base_row(floor=0, total_floors=5)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert bool(out.loc[0, "is_ground_floor"]) is True

    def test_is_top_floor(self):
        df = pd.DataFrame([_base_row(floor=9, total_floors=9)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert bool(out.loc[0, "is_top_floor"]) is True


class TestAreaPerRoom:
    def test_na_when_rooms_is_zero(self):
        df = pd.DataFrame([_base_row(rooms=0, total_area_sqm=50.0)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert pd.isna(out.loc[0, "area_per_room"])

    def test_computed_when_rooms_present(self):
        df = pd.DataFrame([_base_row(rooms=2, total_area_sqm=50.0)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert out.loc[0, "area_per_room"] == 25.0


class TestPlotToBuildingRatio:
    def test_na_when_plot_area_zero_or_missing(self):
        df = pd.DataFrame([_base_row(plot_area_sqm=0, total_area_sqm=100.0)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert pd.isna(out.loc[0, "plot_to_building_ratio"])

    def test_computed_when_plot_area_present(self):
        df = pd.DataFrame([_base_row(plot_area_sqm=200.0, total_area_sqm=100.0)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert out.loc[0, "plot_to_building_ratio"] == 2.0


class TestHasWaterBodyNearby:
    def test_true_when_water_body_present(self):
        df = pd.DataFrame([_base_row(water_body="lake")])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert bool(out.loc[0, "has_water_body_nearby"]) is True

    def test_false_when_absent(self):
        df = pd.DataFrame([_base_row(water_body=None)])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert bool(out.loc[0, "has_water_body_nearby"]) is False


class TestDaysSinceUpdate:
    def test_computed_from_reference_date(self):
        df = pd.DataFrame([_base_row(listing_updated_date="2026-08-20")])
        out = add_derived_features(df, _REFERENCE_DATE)
        assert out.loc[0, "days_since_update"] == 5
