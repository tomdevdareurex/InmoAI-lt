from __future__ import annotations

import json

import pandas as pd

from inmoai_lt.cleaning.features import expand_boolean_features


class _FakeReport:
    def __init__(self):
        self.coverage = None

    def record_feature_coverage(self, coverage):
        self.coverage = coverage


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class TestTriStateRule:
    def test_feature_seen_for_type_absence_becomes_false(self):
        df = _make_df(
            [
                {"property_type": "apartment", "all_features_json": json.dumps({"balcony": True})},
                {"property_type": "apartment", "all_features_json": json.dumps({})},
            ]
        )
        out = expand_boolean_features(df)
        # balcony seen at least once for apartment -> NaN becomes False for row 2
        assert bool(out.loc[0, "balcony"]) is True
        assert bool(out.loc[1, "balcony"]) is False

    def test_feature_never_seen_for_type_stays_na(self):
        df = _make_df(
            [
                {"property_type": "apartment", "all_features_json": json.dumps({"balcony": True})},
            ]
        )
        out = expand_boolean_features(df)
        # garage never appears for apartment type in this fixture -> stays NA
        assert pd.isna(out.loc[0, "garage"])

    def test_dtype_is_nullable_boolean(self):
        df = _make_df(
            [{"property_type": "apartment", "all_features_json": json.dumps({"balcony": True})}]
        )
        out = expand_boolean_features(df)
        assert str(out["balcony"].dtype) == "boolean"

    def test_coverage_differs_per_property_type(self):
        df = _make_df(
            [
                {"property_type": "apartment", "all_features_json": json.dumps({"balcony": True})},
                {"property_type": "house", "all_features_json": json.dumps({"garage": True})},
            ]
        )
        out = expand_boolean_features(df)
        # balcony captured for apartment but not house -> house stays NA
        assert pd.isna(out.loc[1, "balcony"])
        # garage captured for house but not apartment -> apartment stays NA
        assert pd.isna(out.loc[0, "garage"])

    def test_all_features_json_dropped(self):
        df = _make_df(
            [{"property_type": "apartment", "all_features_json": json.dumps({"balcony": True})}]
        )
        out = expand_boolean_features(df)
        assert "all_features_json" not in out.columns

    def test_report_records_coverage(self):
        df = _make_df(
            [{"property_type": "apartment", "all_features_json": json.dumps({"balcony": True})}]
        )
        report = _FakeReport()
        expand_boolean_features(df, report=report)
        assert report.coverage["apartment"]["balcony"] is True
        assert report.coverage["apartment"]["garage"] is False
