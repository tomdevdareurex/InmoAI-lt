from __future__ import annotations

import pandas as pd

from inmoai_lt.cleaning.quality import apply_fatal_filter, compute_quality_flags

_QUALITY_CFG = {
    "flags": {
        "price_eur": {
            "apartment": {"min": 10000, "max": 7500000},
            "house": {"min": 15000, "max": 7500000},
        },
        "total_area_sqm": {
            "apartment": {"min": 15, "max": 1400},
            "house": {"min": 20, "max": 3000},
        },
        "price_per_sqm_eur": {
            "apartment": {"min": 400, "max": 12000},
            "house": {"min": 400, "max": 12000},
        },
        "construction_year": {"min": 1600, "max_offset_from_reference_year": 5},
        "rooms": {"min": 1, "max": 25},
        "stale_listing_age_days": 730,
        "plot_area_sqm_min_exclusive": 0,
    },
    "blocking_flags": [
        "price_out_of_range",
        "area_out_of_range",
        "price_per_sqm_out_of_range",
        "construction_year_out_of_range",
        "coords_outside_vilnius",
        "non_standard_object",
        "not_habitable",
    ],
}

_REFERENCE_DATE = pd.Timestamp("2026-08-25", tz="UTC")


def _clean_row(**overrides):
    row = {
        "listing_id": "1",
        "property_type": "apartment",
        "price_eur": 150000,
        "total_area_sqm": 50.0,
        "price_per_sqm_eur": 3000.0,
        "construction_year": 2000,
        "rooms": 2,
        "floor": 3,
        "total_floors": 9,
        "plot_area_sqm": None,
        "object_type_lt": None,
        "condition": "fully_finished",
        "listing_age_days": 10,
        "description_lt": "A normal description",
        "is_duplicate": False,
    }
    row.update(overrides)
    return row


class TestIndividualFlags:
    def test_price_out_of_range_fires(self):
        df = pd.DataFrame([_clean_row(price_eur=5000)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_price_out_of_range"]) is True

    def test_price_in_range_does_not_fire(self):
        df = pd.DataFrame([_clean_row()])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_price_out_of_range"]) is False

    def test_area_out_of_range(self):
        df = pd.DataFrame([_clean_row(total_area_sqm=5.0)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_area_out_of_range"]) is True

    def test_price_per_sqm_inconsistent(self):
        df = pd.DataFrame([_clean_row(price_eur=150000, total_area_sqm=50.0, price_per_sqm_eur=100.0)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_price_per_sqm_inconsistent"]) is True

    def test_price_per_sqm_consistent_no_flag(self):
        df = pd.DataFrame([_clean_row(price_eur=150000, total_area_sqm=50.0, price_per_sqm_eur=3000.0)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_price_per_sqm_inconsistent"]) is False

    def test_construction_year_out_of_range_future(self):
        df = pd.DataFrame([_clean_row(construction_year=2100)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_construction_year_out_of_range"]) is True

    def test_rooms_out_of_range(self):
        df = pd.DataFrame([_clean_row(rooms=99)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_rooms_out_of_range"]) is True

    def test_floor_gt_total_floors(self):
        df = pd.DataFrame([_clean_row(floor=15, total_floors=9)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_floor_gt_total_floors"]) is True

    def test_plot_area_zero_for_house(self):
        df = pd.DataFrame([_clean_row(property_type="house", plot_area_sqm=0)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_plot_area_zero"]) is True

    def test_non_standard_object(self):
        df = pd.DataFrame([_clean_row(object_type_lt="Buto dalis")])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_non_standard_object"]) is True

    def test_not_habitable(self):
        df = pd.DataFrame([_clean_row(condition="under_construction")])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_not_habitable"]) is True

    def test_stale_listing(self):
        df = pd.DataFrame([_clean_row(listing_age_days=1000)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_stale_listing"]) is True

    def test_description_redacted(self):
        df = pd.DataFrame([_clean_row(description_lt="Call [REDACTED_PHONE] now")])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_description_redacted"]) is True

    def test_missing_description(self):
        df = pd.DataFrame([_clean_row(description_lt=None)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "flag_missing_description"]) is True


class TestIsValid:
    def test_is_valid_true_on_clean_row(self):
        df = pd.DataFrame([_clean_row()])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "is_valid"]) is True

    def test_advisory_flags_do_not_clear_is_valid(self):
        df = pd.DataFrame([_clean_row(listing_age_days=1000, description_lt=None)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "is_valid"]) is True

    def test_blocking_flag_clears_is_valid(self):
        df = pd.DataFrame([_clean_row(price_eur=1)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        assert bool(out.loc[0, "is_valid"]) is False


class TestQualityFlagsString:
    def test_sorted_comma_joined(self):
        df = pd.DataFrame([_clean_row(price_eur=5000, rooms=99)])
        out = compute_quality_flags(df, _QUALITY_CFG, _REFERENCE_DATE)
        flags = out.loc[0, "quality_flags"].split(",")
        assert flags == sorted(flags)
        assert "price_out_of_range" in flags
        assert "rooms_out_of_range" in flags


class TestFatalFilter:
    _FATAL_CFG = {
        "require_non_null": ["listing_id", "property_type", "price_eur", "total_area_sqm", "latitude", "longitude"],
        "price_eur_min_exclusive": 0,
        "total_area_sqm_min_exclusive": 0,
    }

    def test_removes_zero_price_row(self):
        df = pd.DataFrame(
            [
                {
                    "listing_id": "1",
                    "property_type": "apartment",
                    "price_eur": 0,
                    "total_area_sqm": 50.0,
                    "latitude": 54.7,
                    "longitude": 25.3,
                }
            ]
        )
        out = apply_fatal_filter(df, self._FATAL_CFG)
        assert len(out) == 0

    def test_keeps_valid_row(self):
        df = pd.DataFrame(
            [
                {
                    "listing_id": "1",
                    "property_type": "apartment",
                    "price_eur": 100000,
                    "total_area_sqm": 50.0,
                    "latitude": 54.7,
                    "longitude": 25.3,
                }
            ]
        )
        out = apply_fatal_filter(df, self._FATAL_CFG)
        assert len(out) == 1

    def test_reports_reason(self):
        df = pd.DataFrame(
            [
                {
                    "listing_id": "1",
                    "property_type": "apartment",
                    "price_eur": 0,
                    "total_area_sqm": 50.0,
                    "latitude": 54.7,
                    "longitude": 25.3,
                }
            ]
        )

        class _FakeReport:
            def record_fatal_removals(self, count, removals):
                self.count = count
                self.removals = removals

        report = _FakeReport()
        apply_fatal_filter(df, self._FATAL_CFG, report)
        assert report.count == 1
        assert report.removals[0]["reasons"] == ["price_eur_not_positive"]
