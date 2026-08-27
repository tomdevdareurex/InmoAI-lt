from __future__ import annotations

import pandas as pd

from inmoai_lt.cleaning.parsers import (
    contains_redacted_marker,
    fold_key,
    normalize_text,
    parse_decimal,
    parse_int,
    parse_iso_date,
    parse_years,
    to_nullable_int_series,
)


class TestParseDecimal:
    def test_area_with_comma_decimal_and_unit_suffix(self):
        assert parse_decimal("54,02 m²") == 54.02

    def test_space_thousands_separator(self):
        assert parse_decimal("1 000") == 1000.0

    def test_nbsp_thousands_separator(self):
        assert parse_decimal("1\u00a0000") == 1000.0

    def test_ares_with_comma_decimal(self):
        assert parse_decimal("2,6 a") == 2.6

    def test_zero_ares(self):
        assert parse_decimal("0 a") == 0.0

    def test_garbage_returns_none_not_zero(self):
        assert parse_decimal("abc") is None

    def test_none_returns_none(self):
        assert parse_decimal(None) is None

    def test_empty_string_returns_none(self):
        assert parse_decimal("") is None

    def test_nan_returns_none(self):
        assert parse_decimal(float("nan")) is None

    def test_numeric_input_passthrough(self):
        assert parse_decimal(42) == 42.0

    def test_never_fabricates_zero(self):
        # A clearly-unparseable string must return None, not 0.
        result = parse_decimal("N/A")
        assert result is None
        assert result != 0


class TestParseInt:
    def test_rounds_to_int(self):
        assert parse_int("3,6") == 4

    def test_garbage_returns_none(self):
        assert parse_int("garbage") is None


class TestNullableIntSeries:
    def test_int64_nullable_survives_missing(self):
        series = pd.Series(["3", None, "5,0", "bad"])
        out = to_nullable_int_series(series)
        assert str(out.dtype) == "Int64"
        assert out[0] == 3
        assert pd.isna(out[1])
        assert out[2] == 5
        assert pd.isna(out[3])


class TestParseYears:
    def test_bare_year(self):
        assert parse_years("2013") == (2013, None)

    def test_construction_and_renovation(self):
        assert parse_years("1960 statyba, 2026 renovacija") == (1960, 2026)

    def test_none_input(self):
        assert parse_years(None) == (None, None)

    def test_empty_string(self):
        assert parse_years("") == (None, None)


class TestNormalizeText:
    def test_collapses_whitespace_and_nbsp(self):
        assert normalize_text("Vilnius\u00a0 city   center") == "Vilnius city center"

    def test_empty_becomes_none(self):
        assert normalize_text("   ") is None

    def test_none_becomes_none(self):
        assert normalize_text(None) is None

    def test_preserves_lithuanian_diacritics(self):
        assert normalize_text(" Žirmūnai ") == "Žirmūnai"


class TestFoldKey:
    def test_folds_diacritics_and_casefolds(self):
        assert fold_key("Žirmūnai") == "zirmunai"

    def test_matches_across_case_and_diacritics(self):
        assert fold_key("ŠIAURĖ") == fold_key("siaure")

    def test_none_input(self):
        assert fold_key(None) is None


class TestContainsRedactedMarker:
    def test_detects_marker(self):
        assert contains_redacted_marker("Call me [REDACTED_PHONE] now") is True

    def test_no_marker(self):
        assert contains_redacted_marker("Plain description") is False

    def test_none_input(self):
        assert contains_redacted_marker(None) is False


class TestParseIsoDate:
    def test_parses_iso_date(self):
        result = parse_iso_date("2026-08-17")
        assert result == pd.Timestamp("2026-08-17")

    def test_none_returns_nat(self):
        assert pd.isna(parse_iso_date(None))
