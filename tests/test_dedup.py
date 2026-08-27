from __future__ import annotations

import pandas as pd

from inmoai_lt.cleaning.dedup import flag_content_duplicates, flag_identity_duplicates

_CONTENT_KEY = [
    "property_type",
    "district",
    "street",
    "house_number",
    "total_area_sqm_rounded",
    "rooms",
    "price_eur",
]


class _FakeReport:
    def __init__(self):
        self.identity = None
        self.content = None

    def record_identity_duplicates(self, count, listing_ids):
        self.identity = (count, listing_ids)

    def record_content_duplicates(self, group_count, duplicate_row_count, groups):
        self.content = (group_count, duplicate_row_count, groups)


class TestFlagIdentityDuplicates:
    def test_drops_duplicate_listing_id_keeps_first(self):
        df = pd.DataFrame({"listing_id": ["1", "1", "2"], "value": ["a", "b", "c"]})
        out = flag_identity_duplicates(df)
        assert len(out) == 2
        assert out.loc[out["listing_id"] == "1", "value"].iloc[0] == "a"

    def test_reports_dropped_count(self):
        df = pd.DataFrame({"listing_id": ["1", "1"]})
        report = _FakeReport()
        flag_identity_duplicates(df, report)
        assert report.identity[0] == 1


def _base_row(**overrides):
    row = {
        "listing_id": "1",
        "property_type": "apartment",
        "district": "Senamiestis",
        "street": "Pilies g.",
        "house_number": "5",
        "total_area_sqm": 50.0,
        "rooms": 2,
        "price_eur": 150000,
        "listing_updated_date": "2026-08-20",
        "views_count": 100,
    }
    row.update(overrides)
    return row


class TestFlagContentDuplicates:
    def test_exact_content_dupes_grouped(self):
        df = pd.DataFrame([_base_row(listing_id="1"), _base_row(listing_id="2")])
        out = flag_content_duplicates(df, _CONTENT_KEY, area_round_dp=1)
        assert out["duplicate_group_id"].notna().sum() == 2
        assert out["is_duplicate"].sum() == 1
        assert out["is_duplicate_primary"].sum() == 1

    def test_na_key_part_prevents_grouping(self):
        df = pd.DataFrame(
            [
                _base_row(listing_id="1", house_number=None),
                _base_row(listing_id="2", house_number=None),
            ]
        )
        out = flag_content_duplicates(df, _CONTENT_KEY, area_round_dp=1)
        assert out["duplicate_group_id"].isna().all()
        assert out["is_duplicate"].sum() == 0

    def test_keep_latest_updated_is_primary(self):
        df = pd.DataFrame(
            [
                _base_row(listing_id="1", listing_updated_date="2026-08-10"),
                _base_row(listing_id="2", listing_updated_date="2026-08-25"),
            ]
        )
        out = flag_content_duplicates(df, _CONTENT_KEY, area_round_dp=1)
        primary = out.loc[out["is_duplicate_primary"], "listing_id"].iloc[0]
        assert primary == "2"

    def test_tie_break_by_views_then_listing_id(self):
        df = pd.DataFrame(
            [
                _base_row(listing_id="2", listing_updated_date="2026-08-10", views_count=50),
                _base_row(listing_id="1", listing_updated_date="2026-08-10", views_count=200),
            ]
        )
        out = flag_content_duplicates(df, _CONTENT_KEY, area_round_dp=1)
        primary = out.loc[out["is_duplicate_primary"], "listing_id"].iloc[0]
        assert primary == "1"  # higher views wins the tie on identical updated date

    def test_no_rows_deleted(self):
        df = pd.DataFrame([_base_row(listing_id="1"), _base_row(listing_id="2")])
        out = flag_content_duplicates(df, _CONTENT_KEY, area_round_dp=1)
        assert len(out) == len(df)
