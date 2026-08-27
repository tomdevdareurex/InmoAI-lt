from __future__ import annotations

import pandas as pd

from inmoai_lt.cleaning.categorical import (
    HEATING_TOKENS,
    apply_categorical_mapping,
    apply_multi_value_mapping,
    build_lookup,
)

_BUILDING_TYPE_VOCAB = {
    "mūrinis": "brick",
    "blokinis": "concrete_block",
    "brick": "brick",
}

_HEATING_VOCAB = {
    "centrinis": "central",
    "centrinis kolektorinis": "central_collector",
    "dujinis": "gas",
}


class _FakeReport:
    def __init__(self):
        self.unmapped = {}

    def record_unmapped_category_values(self, unmapped):
        self.unmapped.update(unmapped)


class TestBuildLookup:
    def test_casefolds_keys(self):
        lookup = build_lookup({"Mūrinis": "brick"})
        assert lookup["mūrinis"] == "brick"


class TestApplyCategoricalMapping:
    def test_case_insensitive_lookup(self):
        df = pd.DataFrame({"building_type": ["Mūrinis", "mūrinis", "MŪRINIS"]})
        out = apply_categorical_mapping(df, {"building_type": _BUILDING_TYPE_VOCAB})
        assert (out["building_type"] == "brick").all()

    def test_english_passthrough(self):
        df = pd.DataFrame({"building_type": ["brick"]})
        out = apply_categorical_mapping(df, {"building_type": _BUILDING_TYPE_VOCAB})
        assert out.loc[0, "building_type"] == "brick"

    def test_unmapped_value_preserved_verbatim_with_diacritics(self):
        df = pd.DataFrame({"building_type": ["Rąstinis"]})
        report = _FakeReport()
        out = apply_categorical_mapping(df, {"building_type": _BUILDING_TYPE_VOCAB}, report)
        assert out.loc[0, "building_type"] == "Rąstinis"
        assert report.unmapped["building_type"]["Rąstinis"] == 1

    def test_raw_column_added_only_when_changed(self):
        df = pd.DataFrame({"building_type": ["Mūrinis", "Unknown"]})
        out = apply_categorical_mapping(df, {"building_type": _BUILDING_TYPE_VOCAB})
        assert out.loc[0, "building_type_raw"] == "Mūrinis"
        assert pd.isna(out.loc[1, "building_type_raw"])


class TestApplyMultiValueMapping:
    def test_split_and_canonical_sorted_string(self):
        df = pd.DataFrame({"heating_type": ["Centrinis, dujinis"]})
        out = apply_multi_value_mapping(
            df,
            source_col="heating_type",
            types_col="heating_types",
            count_col="heating_type_count",
            bool_prefix="heating",
            vocabulary=_HEATING_VOCAB,
            boolean_tokens=HEATING_TOKENS,
        )
        assert out.loc[0, "heating_types"] == "central,gas"
        assert out.loc[0, "heating_type_count"] == 2
        assert bool(out.loc[0, "heating_central"]) is True
        assert bool(out.loc[0, "heating_gas"]) is True
        assert bool(out.loc[0, "heating_electric"]) is False

    def test_case_insensitive_second_token(self):
        # Source lowercases second-and-later tokens: "Centrinis kolektorinis, aeroterminis"
        df = pd.DataFrame({"heating_type": ["Centrinis kolektorinis, dujinis"]})
        out = apply_multi_value_mapping(
            df,
            source_col="heating_type",
            types_col="heating_types",
            count_col="heating_type_count",
            bool_prefix="heating",
            vocabulary=_HEATING_VOCAB,
            boolean_tokens=HEATING_TOKENS,
        )
        assert "central_collector" in out.loc[0, "heating_types"]
        assert "gas" in out.loc[0, "heating_types"]

    def test_source_column_dropped(self):
        df = pd.DataFrame({"heating_type": ["Centrinis"]})
        out = apply_multi_value_mapping(
            df,
            source_col="heating_type",
            types_col="heating_types",
            count_col="heating_type_count",
            bool_prefix="heating",
            vocabulary=_HEATING_VOCAB,
            boolean_tokens=HEATING_TOKENS,
        )
        assert "heating_type" not in out.columns
        assert "heating_type_raw" in out.columns
