"""Column normalisation: snake_case, all-null drop, redundant collapse, constant drop."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

# Columns collapsed because they duplicate another column. Each entry documents the
# survivor and the reason, recorded verbatim in the cleaning report.
_REDUNDANT_COLLAPSES: list[dict[str, Any]] = [
    {"drop": "municipality", "keep": "city", "reason": "== city (100%)"},
    {"drop": "canonical_url", "keep": "listing_url", "reason": "== listing_url (100%)"},
    {
        "drop": "apartment_total_area_sqm",
        "keep": "total_area_sqm",
        "reason": "== total_area_sqm where apartment",
    },
    {
        "drop": "house_total_area_sqm",
        "keep": "total_area_sqm",
        "reason": "== total_area_sqm where house",
    },
    {
        "drop": "number_of_floors",
        "keep": "total_floors",
        "reason": "== total_floors where house",
    },
    {
        "drop": "plot_area_ares",
        "keep": "plot_area_sqm",
        "reason": "== plot_area_sqm / 100",
    },
]

# Single-valued constant columns dropped after logging their (single) value.
_CONSTANT_COLUMNS = [
    "country",
    "currency",
    "listing_status",
    "record_source",
    "coordinate_source",
    "city",
]

_SNAKE_RE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_RE_2 = re.compile(r"([a-z0-9])([A-Z])")


def to_snake_case(name: str) -> str:
    """Convert a column name to snake_case. Idempotent for already-snake names."""
    s1 = _SNAKE_RE_1.sub(r"\1_\2", name)
    s2 = _SNAKE_RE_2.sub(r"\1_\2", s1)
    s3 = s2.replace(" ", "_").replace("-", "_").lower()
    return re.sub(r"_+", "_", s3).strip("_")


def normalize_column_names(df: pd.DataFrame, report: Any = None) -> pd.DataFrame:
    """Run `to_snake_case` on every column name; record any actual renames."""
    rename_map = {col: to_snake_case(col) for col in df.columns}
    actual_renames = {k: v for k, v in rename_map.items() if k != v}
    if report is not None:
        report.record_renames(actual_renames)
    return df.rename(columns=rename_map)


def drop_all_null_columns(df: pd.DataFrame, report: Any = None) -> pd.DataFrame:
    """Drop columns that are null across the WHOLE combined frame.

    Evaluated on the combined table so a column null for one property_type but
    populated for another (e.g. `floor` apartments-only) survives.
    """
    all_null_cols = [col for col in df.columns if df[col].isna().all()]
    if report is not None:
        report.record_dropped_columns(all_null_cols, reason="all_null")
    return df.drop(columns=all_null_cols)


def collapse_redundant_columns(df: pd.DataFrame, report: Any = None) -> pd.DataFrame:
    """Drop columns that duplicate another column's information (see `_REDUNDANT_COLLAPSES`)."""
    result = df
    dropped = []
    for spec in _REDUNDANT_COLLAPSES:
        drop_col, keep_col = spec["drop"], spec["keep"]
        if drop_col not in result.columns:
            continue
        dropped.append(drop_col)
        result = result.drop(columns=[drop_col])
    if report is not None:
        for spec in _REDUNDANT_COLLAPSES:
            if spec["drop"] in dropped:
                report.record_dropped_columns(
                    [spec["drop"]], reason=f"redundant ({spec['reason']}, keep={spec['keep']})"
                )
    return result


def collapse_district(df: pd.DataFrame, report: Any = None) -> pd.DataFrame:
    """Collapse `local_area`/`neighbourhood` into `district`.

    Verifies equality first and logs the rows where they differ. Fills `district` from
    `neighbourhood` only where `district` itself is null.
    """
    result = df.copy()
    if "district" not in result.columns:
        return result

    diff_rows = []
    if "neighbourhood" in result.columns:
        mismatch = (result["district"] != result["neighbourhood"]) & ~(
            result["district"].isna() & result["neighbourhood"].isna()
        )
        diff_rows.extend(result.loc[mismatch, "listing_id"].tolist() if "listing_id" in result.columns else [])
        needs_fill = result["district"].isna() & result["neighbourhood"].notna()
        result.loc[needs_fill, "district"] = result.loc[needs_fill, "neighbourhood"]

    to_drop = [c for c in ("local_area", "neighbourhood") if c in result.columns]
    if report is not None:
        report.record_district_collapse(differing_listing_ids=diff_rows, dropped_columns=to_drop)
        report.record_dropped_columns(to_drop, reason="redundant (collapsed into district)")
    result = result.drop(columns=to_drop)
    return result


def drop_constant_columns(df: pd.DataFrame, report: Any = None) -> pd.DataFrame:
    """Drop single-valued constant columns, recording each dropped value in the report."""
    result = df
    present = [c for c in _CONSTANT_COLUMNS if c in result.columns]
    values = {}
    for col in present:
        non_null = result[col].dropna().unique()
        values[col] = non_null[0] if len(non_null) > 0 else None
    if report is not None:
        report.record_constant_columns(values)
    return result.drop(columns=present)
