"""Quality flags and the fatal filter.

Flags are computed first so the report can show what would have been removed; only the
explicit fatal rules actually remove a row ("flag, don't delete").
"""

from __future__ import annotations

from typing import Any

import pandas as pd

_FLAG_NAMES = [
    "price_out_of_range",
    "area_out_of_range",
    "price_per_sqm_out_of_range",
    "price_per_sqm_inconsistent",
    "construction_year_out_of_range",
    "rooms_out_of_range",
    "floor_gt_total_floors",
    "plot_area_zero",
    "non_standard_object",
    "not_habitable",
    "missing_coordinates",
    "coords_outside_vilnius",
    "coords_outside_lithuania",
    "coords_approximate",
    "stale_listing",
    "description_redacted",
    "missing_description",
    "duplicate",
]

_NOT_HABITABLE_CONDITIONS = {"foundation_only", "under_construction"}


def build_segment(df: pd.DataFrame) -> pd.Series:
    """`<property_type>_<listing_type>`, e.g. `apartment_sale`, `house_rent`.

    The unit every price/area bound is calibrated against: rent and sale are different
    price regimes, so `property_type` alone is not a sufficient key.
    """
    return df["property_type"].astype("string") + "_" + df["listing_type"].astype("string")


def _per_segment_bounds(
    series: pd.Series, segment: pd.Series, bounds_by_segment: dict[str, dict]
) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    out_of_range = pd.Series(False, index=series.index)
    for seg, bounds in bounds_by_segment.items():
        mask = (segment == seg).fillna(False)
        out_of_range |= mask & numeric.notna() & ((numeric < bounds["min"]) | (numeric > bounds["max"]))
    return out_of_range


def compute_quality_flags(
    df: pd.DataFrame,
    quality_cfg: dict[str, Any],
    reference_date: pd.Timestamp,
    report: Any = None,
) -> pd.DataFrame:
    """Compute all `flag_*` boolean columns plus `quality_flag_count`, `quality_flags`,
    `is_valid`. Does not remove any rows.
    """
    result = df.copy()
    flags_cfg = quality_cfg["flags"]
    ptype = result["property_type"]
    segment = build_segment(result)

    price = pd.to_numeric(result["price_eur"], errors="coerce")
    area = pd.to_numeric(result["total_area_sqm"], errors="coerce")
    price_per_sqm = pd.to_numeric(result["price_per_sqm_eur"], errors="coerce")

    result["flag_price_out_of_range"] = _per_segment_bounds(price, segment, flags_cfg["price_eur"])
    result["flag_area_out_of_range"] = _per_segment_bounds(area, segment, flags_cfg["total_area_sqm"])
    result["flag_price_per_sqm_out_of_range"] = _per_segment_bounds(
        price_per_sqm, segment, flags_cfg["price_per_sqm_eur"]
    )

    area_safe = area.where(area != 0)
    computed_price_per_sqm = price / area_safe
    result["flag_price_per_sqm_inconsistent"] = (
        (computed_price_per_sqm - price_per_sqm).abs() > 1
    ).fillna(False)

    construction_year = pd.to_numeric(result["construction_year"], errors="coerce")
    year_cfg = flags_cfg["construction_year"]
    reference_year = reference_date.year
    max_year = reference_year + year_cfg["max_offset_from_reference_year"]
    result["flag_construction_year_out_of_range"] = construction_year.notna() & (
        (construction_year < year_cfg["min"]) | (construction_year > max_year)
    )

    rooms = pd.to_numeric(result["rooms"], errors="coerce")
    rooms_cfg = flags_cfg["rooms"]
    result["flag_rooms_out_of_range"] = rooms.notna() & (
        (rooms < rooms_cfg["min"]) | (rooms > rooms_cfg["max"])
    )

    if "floor" in result.columns and "total_floors" in result.columns:
        floor = pd.to_numeric(result["floor"], errors="coerce")
        total_floors = pd.to_numeric(result["total_floors"], errors="coerce")
        result["flag_floor_gt_total_floors"] = (
            floor.notna() & total_floors.notna() & (floor > total_floors)
        )
    else:
        result["flag_floor_gt_total_floors"] = False

    if "plot_area_sqm" in result.columns:
        plot_area = pd.to_numeric(result["plot_area_sqm"], errors="coerce")
        result["flag_plot_area_zero"] = (ptype == "house") & plot_area.notna() & (
            plot_area <= flags_cfg["plot_area_sqm_min_exclusive"]
        )
    else:
        result["flag_plot_area_zero"] = False

    result["flag_non_standard_object"] = (
        result["object_type_lt"].notna() if "object_type_lt" in result.columns else False
    )

    if "condition" in result.columns:
        result["flag_not_habitable"] = result["condition"].isin(_NOT_HABITABLE_CONDITIONS)
    else:
        result["flag_not_habitable"] = False

    # geo flags already computed in geo.py; keep them if present, else default False.
    for col in (
        "flag_missing_coordinates",
        "flag_coords_outside_vilnius",
        "flag_coords_outside_lithuania",
        "flag_coords_approximate",
    ):
        if col not in result.columns:
            result[col] = False

    listing_age_days = pd.to_numeric(result.get("listing_age_days"), errors="coerce")
    result["flag_stale_listing"] = listing_age_days.notna() & (
        listing_age_days > flags_cfg["stale_listing_age_days"]
    )

    if "description_lt" in result.columns:
        result["flag_description_redacted"] = result["description_lt"].fillna("").str.contains(
            r"\[REDACTED_", regex=True
        )
        result["flag_missing_description"] = result["description_lt"].isna()
    else:
        result["flag_description_redacted"] = False
        result["flag_missing_description"] = True

    result["flag_duplicate"] = (
        result["is_duplicate"].fillna(False) if "is_duplicate" in result.columns else False
    )

    flag_cols = [f"flag_{name}" for name in _FLAG_NAMES]
    for col in flag_cols:
        result[col] = result[col].astype("boolean")

    result["quality_flag_count"] = result[flag_cols].sum(axis=1).astype("Int64")
    result["quality_flags"] = result[flag_cols].apply(
        lambda row: ",".join(sorted(name for name, col in zip(_FLAG_NAMES, flag_cols) if row[col])),
        axis=1,
    )

    blocking_flags = set(quality_cfg.get("blocking_flags", []))
    blocking_cols = [f"flag_{name}" for name in blocking_flags]
    is_blocked = pd.Series(False, index=result.index)
    for col in blocking_cols:
        if col in result.columns:
            is_blocked |= result[col].fillna(False)
    result["is_valid"] = (~is_blocked).astype("boolean")

    if report is not None:
        flag_counts = {name: int(result[f"flag_{name}"].sum()) for name in _FLAG_NAMES}
        report.record_quality_flags(flag_counts)

    return result


def apply_fatal_filter(
    df: pd.DataFrame,
    fatal_cfg: dict[str, Any],
    report: Any = None,
) -> pd.DataFrame:
    """Remove rows failing the fatal rules. This is the only step that deletes rows."""
    result = df.copy()
    removal_mask = pd.Series(False, index=result.index)
    removal_reasons: dict[Any, list[str]] = {}

    def _mark(mask: pd.Series, reason: str) -> None:
        nonlocal removal_mask
        for idx in result.index[mask]:
            removal_reasons.setdefault(idx, []).append(reason)
        removal_mask = removal_mask | mask

    for col in fatal_cfg["require_non_null"]:
        if col in result.columns:
            _mark(result[col].isna(), f"null_{col}")

    price = pd.to_numeric(result["price_eur"], errors="coerce")
    _mark(price.notna() & (price <= fatal_cfg["price_eur_min_exclusive"]), "price_eur_not_positive")

    area = pd.to_numeric(result["total_area_sqm"], errors="coerce")
    _mark(
        area.notna() & (area <= fatal_cfg["total_area_sqm_min_exclusive"]),
        "total_area_sqm_not_positive",
    )

    removed_ids = [
        {"listing_id": result.loc[idx, "listing_id"] if "listing_id" in result.columns else idx, "reasons": reasons}
        for idx, reasons in removal_reasons.items()
    ]
    if report is not None:
        report.record_fatal_removals(count=int(removal_mask.sum()), removals=removed_ids)

    return result.loc[~removal_mask].reset_index(drop=True)
