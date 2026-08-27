from __future__ import annotations

import pandas as pd

from inmoai_lt.cleaning.columns import (
    collapse_district,
    collapse_redundant_columns,
    drop_all_null_columns,
    drop_constant_columns,
    normalize_column_names,
    to_snake_case,
)


class _FakeReport:
    def __init__(self):
        self.renames = {}
        self.dropped = []
        self.constants = {}
        self.district_diffs = None

    def record_renames(self, renames):
        self.renames.update(renames)

    def record_dropped_columns(self, cols, reason):
        self.dropped.append((tuple(cols), reason))

    def record_constant_columns(self, values):
        self.constants.update(values)

    def record_district_collapse(self, differing_listing_ids, dropped_columns):
        self.district_diffs = (differing_listing_ids, dropped_columns)


class TestToSnakeCase:
    def test_idempotent_on_already_snake(self):
        assert to_snake_case("total_area_sqm") == "total_area_sqm"

    def test_camel_case_converted(self):
        assert to_snake_case("TotalAreaSqm") == "total_area_sqm"

    def test_spaces_converted(self):
        assert to_snake_case("Total Area") == "total_area"


class TestNormalizeColumnNames:
    def test_records_only_actual_renames(self):
        df = pd.DataFrame({"already_snake": [1], "CamelCase": [2]})
        report = _FakeReport()
        out = normalize_column_names(df, report)
        assert list(out.columns) == ["already_snake", "camel_case"]
        assert report.renames == {"CamelCase": "camel_case"}


class TestDropAllNullColumns:
    def test_keeps_column_populated_for_only_one_property_type(self):
        # `floor` is populated for apartments but null for houses in the combined frame.
        df = pd.DataFrame(
            {
                "property_type": ["apartment", "house"],
                "floor": [3, None],
                "fully_empty": [None, None],
            }
        )
        report = _FakeReport()
        out = drop_all_null_columns(df, report)
        assert "floor" in out.columns
        assert "fully_empty" not in out.columns
        assert report.dropped == [(("fully_empty",), "all_null")]


class TestCollapseRedundantColumns:
    def test_drops_redundant_and_keeps_survivor(self):
        df = pd.DataFrame(
            {
                "municipality": ["Vilnius"],
                "city": ["Vilnius"],
                "canonical_url": ["http://x"],
                "listing_url": ["http://x"],
            }
        )
        report = _FakeReport()
        out = collapse_redundant_columns(df, report)
        assert "municipality" not in out.columns
        assert "canonical_url" not in out.columns
        assert "city" in out.columns
        assert "listing_url" in out.columns
        assert len(report.dropped) == 2


class TestCollapseDistrict:
    def test_fills_district_from_neighbourhood_when_null(self):
        df = pd.DataFrame(
            {
                "listing_id": ["1", "2"],
                "district": [None, "Senamiestis"],
                "local_area": ["Zirmunai", "Senamiestis"],
                "neighbourhood": ["Zirmunai", "Senamiestis"],
            }
        )
        report = _FakeReport()
        out = collapse_district(df, report)
        assert out.loc[0, "district"] == "Zirmunai"
        assert "local_area" not in out.columns
        assert "neighbourhood" not in out.columns

    def test_logs_rows_where_district_and_neighbourhood_differ(self):
        df = pd.DataFrame(
            {
                "listing_id": ["1"],
                "district": ["Vilnius"],
                "local_area": ["Bajorai"],
                "neighbourhood": ["Bajorai"],
            }
        )
        report = _FakeReport()
        collapse_district(df, report)
        assert report.district_diffs[0] == ["1"]


class TestDropConstantColumns:
    def test_drops_and_records_value(self):
        df = pd.DataFrame({"country": ["Lithuania", "Lithuania"], "other": [1, 2]})
        report = _FakeReport()
        out = drop_constant_columns(df, report)
        assert "country" not in out.columns
        assert report.constants == {"country": "Lithuania"}
