from __future__ import annotations

import json

import pandas as pd

from inmoai_lt.cleaning.attributes import recover_attributes


class _FakeReport:
    def __init__(self):
        self.counts = None
        self.mismatches = None
        self.unmapped = None

    def record_attribute_recovery(self, counts, construction_year_mismatches):
        self.counts = counts
        self.mismatches = construction_year_mismatches

    def record_unmapped_attributes(self, tally):
        self.unmapped = tally


def _make_df(rows: list[dict]) -> pd.DataFrame:
    base = {
        "listing_id": None,
        "listing_url": "http://example.com",
        "construction_year": None,
        "raw_attributes_json": "{}",
    }
    records = []
    for i, row in enumerate(rows):
        rec = dict(base)
        rec["listing_id"] = str(i)
        rec.update(row)
        records.append(rec)
    return pd.DataFrame(records)


class TestMetaiYearRecovery:
    def test_construction_and_renovation_recovered(self):
        df = _make_df(
            [{"raw_attributes_json": json.dumps({"Metai": "1960 statyba, 2026 renovacija"})}]
        )
        out = recover_attributes(df)
        assert out.loc[0, "construction_year"] == 1960
        assert out.loc[0, "renovation_year"] == 2026
        assert bool(out.loc[0, "has_renovation"]) is True

    def test_bare_year_no_renovation(self):
        df = _make_df([{"raw_attributes_json": json.dumps({"Metai": "2013"})}])
        out = recover_attributes(df)
        assert out.loc[0, "construction_year"] == 2013
        assert pd.isna(out.loc[0, "renovation_year"])


class TestOrientationRecovery:
    def test_order_independent_same_result(self):
        df = _make_df(
            [
                {"raw_attributes_json": json.dumps({"Langų orientacija": "Pietūs, šiaurė"})},
                {"raw_attributes_json": json.dumps({"Langų orientacija": "Šiaurė, pietūs"})},
            ]
        )
        out = recover_attributes(df)
        assert out.loc[0, "window_orientation"] == "north,south"
        assert out.loc[1, "window_orientation"] == "north,south"
        assert bool(out.loc[0, "orientation_north"]) == bool(out.loc[1, "orientation_north"]) is True
        assert bool(out.loc[0, "orientation_south"]) == bool(out.loc[1, "orientation_south"]) is True
        assert bool(out.loc[0, "orientation_east"]) is False
        assert bool(out.loc[0, "orientation_west"]) is False


class TestHouseNumberRecovery:
    def test_alphanumeric_house_number_stays_string(self):
        df = _make_df([{"raw_attributes_json": json.dumps({"Namo numeris": "8A"})}])
        out = recover_attributes(df)
        assert out.loc[0, "house_number"] == "8A"
        assert isinstance(out.loc[0, "house_number"], str)


class TestDistanceToWaterRecovery:
    def test_space_thousands_separator_parsed(self):
        df = _make_df([{"raw_attributes_json": json.dumps({"Iki vandens telkinio (m)": "1 000"})}])
        out = recover_attributes(df)
        assert out.loc[0, "distance_to_water_m"] == 1000.0


class TestUnmappedAttributes:
    def test_unknown_label_recorded_and_not_lost(self):
        df = _make_df(
            [{"raw_attributes_json": json.dumps({"Some New Label": "some value"})}]
        )
        report = _FakeReport()
        recover_attributes(df, report=report)
        assert "Some New Label" in report.unmapped
        assert report.unmapped["Some New Label"]["count"] == 1

    def test_already_promoted_labels_are_not_unmapped(self):
        df = _make_df(
            [
                {
                    "raw_attributes_json": json.dumps(
                        {"Aukštas": "3", "Plotas": "54,02 m²", "Metai": "2013"}
                    )
                }
            ]
        )
        report = _FakeReport()
        recover_attributes(df, report=report)
        assert report.unmapped == {}


class TestRawAttributesDropped:
    def test_raw_attributes_json_column_removed(self):
        df = _make_df([{"raw_attributes_json": "{}"}])
        out = recover_attributes(df)
        assert "raw_attributes_json" not in out.columns
