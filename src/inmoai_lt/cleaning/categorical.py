"""LT -> EN controlled vocabulary application, single- and multi-value fields.

Lookup is case-insensitive and whitespace-trimmed. English values pass through
identically. Unmapped values are preserved verbatim (with diacritics) and recorded.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

# Single-value categorical columns mapped via the vocabulary.
_SINGLE_VALUE_COLUMNS = ["building_type", "condition", "house_type"]

# Multi-value (comma-separated) columns and the canonical boolean-flag token set.
_HEATING_TOKENS = [
    "central",
    "central_collector",
    "gas",
    "electric",
    "air_source_heat_pump",
    "geothermal",
    "solid_fuel",
    "liquid_fuel",
    "solar",
    "stove",
    "other",
]
_WATER_SUPPLY_TOKENS = ["city_water", "local_water", "artesian_well", "well", "other"]


def _lookup(value: Optional[str], mapping: dict[str, str]) -> Optional[str]:
    if value is None:
        return None
    key = value.strip().casefold()
    if not key:
        return None
    # Vocabulary keys are stored casefolded by build_lookup(); this is the fallback path.
    return mapping.get(key, value.strip())


def build_lookup(vocabulary: dict[str, str]) -> dict[str, str]:
    """Casefold every vocabulary key so lookups are case-insensitive."""
    return {str(k).strip().casefold(): v for k, v in vocabulary.items()}


def apply_categorical_mapping(
    df: pd.DataFrame,
    mappings: dict[str, dict[str, str]],
    report: Any = None,
) -> pd.DataFrame:
    """Map `_SINGLE_VALUE_COLUMNS` through their vocabularies.

    Keeps the original value in `<col>_raw` only where the mapping changed it.
    Records unmapped values (present in data, absent from vocabulary) in the report.
    """
    result = df.copy()
    unmapped: dict[str, dict[str, int]] = {}

    for col in _SINGLE_VALUE_COLUMNS:
        if col not in result.columns or col not in mappings:
            continue
        lookup = build_lookup(mappings[col])
        original = result[col]
        mapped = original.map(lambda v: _lookup(v, lookup) if pd.notna(v) else v)

        changed = original.notna() & (original != mapped)
        if changed.any():
            result[f"{col}_raw"] = pd.NA
            result.loc[changed, f"{col}_raw"] = original.loc[changed]

        col_unmapped: dict[str, int] = {}
        for value in original.dropna().unique():
            if value.strip().casefold() not in lookup:
                count = int((original == value).sum())
                col_unmapped[value] = count
        if col_unmapped:
            unmapped[col] = col_unmapped

        result[col] = mapped

    if report is not None:
        report.record_unmapped_category_values(unmapped)

    return result


def _split_multi_value(raw: Optional[str], lookup: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (canonical mapped tokens sorted, unmapped-original tokens)."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return [], []
    tokens = [t.strip() for t in str(raw).split(",") if t.strip()]
    mapped: list[str] = []
    unmapped: list[str] = []
    for token in tokens:
        key = token.casefold()
        if key in lookup:
            mapped.append(lookup[key])
        else:
            unmapped.append(token)
            mapped.append(token)
    return sorted(set(mapped)), unmapped


def apply_multi_value_mapping(
    df: pd.DataFrame,
    source_col: str,
    types_col: str,
    count_col: str,
    bool_prefix: str,
    vocabulary: dict[str, str],
    boolean_tokens: list[str],
    report: Any = None,
    token_suffixes: Optional[dict[str, str]] = None,
) -> pd.DataFrame:
    """Split, map and expand a comma-separated multi-value column.

    Produces `<types_col>` (canonical sorted joined string), `<count_col>` (int) and
    one `<bool_prefix>_<suffix>` boolean per known token, where `<suffix>` is
    `token_suffixes.get(token, token)` -- e.g. water's canonical token `city_water`
    becomes the column `water_city` via `token_suffixes={"city_water": "city", ...}`,
    while heating's tokens are already the desired suffixes (no mapping needed).
    """
    result = df.copy()
    if source_col not in result.columns:
        return result

    lookup = build_lookup(vocabulary)
    raw_col = f"{source_col}_raw"
    result[raw_col] = result[source_col]

    parsed = result[source_col].map(lambda v: _split_multi_value(v, lookup))
    types_series = parsed.map(lambda t: ",".join(t[0]) if t[0] else pd.NA)
    count_series = parsed.map(lambda t: len(t[0]) if t[0] else pd.NA)

    result[types_col] = types_series
    result[count_col] = pd.array(
        [c if c is not pd.NA else None for c in count_series], dtype="Int64"
    )

    suffixes = token_suffixes or {}
    for token in boolean_tokens:
        suffix = suffixes.get(token, token)
        col_name = f"{bool_prefix}_{suffix}"
        result[col_name] = parsed.map(
            lambda t, tok=token: (tok in t[0]) if t[0] else pd.NA
        )
        result[col_name] = result[col_name].astype("boolean")

    unmapped_tally: dict[str, int] = {}
    for _, unmapped_tokens in parsed:
        for tok in unmapped_tokens:
            unmapped_tally[tok] = unmapped_tally.get(tok, 0) + 1
    if report is not None and unmapped_tally:
        report.record_unmapped_category_values({source_col: unmapped_tally})

    result = result.drop(columns=[source_col])
    return result


HEATING_TOKENS = _HEATING_TOKENS
WATER_SUPPLY_TOKENS = _WATER_SUPPLY_TOKENS
