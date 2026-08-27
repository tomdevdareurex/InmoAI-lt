from __future__ import annotations

import pytest

from inmoai_lt import schema


class TestExpectedRawColumns:
    def test_has_102_columns(self):
        assert len(schema.EXPECTED_RAW_COLUMNS) == 102

    def test_no_duplicate_columns(self):
        assert len(schema.EXPECTED_RAW_COLUMNS) == len(set(schema.EXPECTED_RAW_COLUMNS))


class TestFinalColumnOrder:
    def test_no_duplicate_columns(self):
        assert len(schema.FINAL_COLUMN_ORDER) == len(set(schema.FINAL_COLUMN_ORDER))

    def test_core_identity_columns_present(self):
        for col in ("listing_id", "property_type", "price_eur", "is_valid"):
            assert col in schema.FINAL_COLUMN_ORDER


class TestAssertRawSchema:
    def test_matching_schema_passes(self):
        schema.assert_raw_schema(schema.EXPECTED_RAW_COLUMNS)  # no raise

    def test_mismatch_raises_with_useful_message(self):
        cols = list(schema.EXPECTED_RAW_COLUMNS)
        cols.remove("listing_id")
        cols.append("some_new_column")
        with pytest.raises(ValueError, match="Raw schema mismatch"):
            schema.assert_raw_schema(cols)


class TestEnforceFinalColumnOrder:
    def test_orders_and_filters_to_present_columns(self):
        present = ["price_eur", "listing_id", "property_type"]
        ordered = schema.enforce_final_column_order(present)
        assert ordered == ["listing_id", "property_type", "price_eur"]

    def test_unlisted_column_raises(self):
        with pytest.raises(ValueError, match="Unlisted columns"):
            schema.enforce_final_column_order(["listing_id", "totally_new_column"])
