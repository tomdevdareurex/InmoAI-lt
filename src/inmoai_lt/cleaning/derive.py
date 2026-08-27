"""Derived / engineered columns, all reproducible from `reference_date`.

Not implemented (documented as deferred): rolling price index / relative price --
only 4 distinct scrape days exist in the source data, so a 7-day rolling window would
be noise, not signal.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def add_derived_features(
    df: pd.DataFrame,
    reference_date: pd.Timestamp,
    report: Any = None,
) -> pd.DataFrame:
    result = df.copy()
    reference_year = reference_date.year

    construction_year = pd.to_numeric(result.get("construction_year"), errors="coerce")
    renovation_year = pd.to_numeric(result.get("renovation_year"), errors="coerce")

    building_age_years = (reference_year - construction_year).clip(lower=0)
    result["building_age_years"] = building_age_years

    result["effective_year"] = construction_year.combine(
        renovation_year, lambda c, r: max(c, r) if pd.notna(c) and pd.notna(r) else (c if pd.notna(c) else r)
    )

    result["years_since_renovation"] = (reference_year - renovation_year).where(renovation_year.notna())

    result["is_new_build"] = (construction_year >= reference_year).astype("boolean")
    result.loc[construction_year.isna(), "is_new_build"] = pd.NA

    if "floor" in result.columns and "total_floors" in result.columns:
        floor = pd.to_numeric(result["floor"], errors="coerce")
        total_floors = pd.to_numeric(result["total_floors"], errors="coerce")
        safe_total_floors = total_floors.where(total_floors != 0)
        result["floor_ratio"] = floor / safe_total_floors
        result["is_ground_floor"] = (floor == 0).astype("boolean")
        result.loc[floor.isna(), "is_ground_floor"] = pd.NA
        result["is_top_floor"] = (floor.notna() & total_floors.notna() & (floor == total_floors)).astype("boolean")
        result.loc[floor.isna() | total_floors.isna(), "is_top_floor"] = pd.NA
    else:
        result["floor_ratio"] = pd.NA
        result["is_ground_floor"] = pd.NA
        result["is_top_floor"] = pd.NA

    if "rooms" in result.columns and "total_area_sqm" in result.columns:
        rooms = pd.to_numeric(result["rooms"], errors="coerce")
        area = pd.to_numeric(result["total_area_sqm"], errors="coerce")
        safe_rooms = rooms.where(rooms != 0)
        result["area_per_room"] = area / safe_rooms
    else:
        result["area_per_room"] = pd.NA

    if "plot_area_sqm" in result.columns and "total_area_sqm" in result.columns:
        plot_area = pd.to_numeric(result["plot_area_sqm"], errors="coerce")
        area = pd.to_numeric(result["total_area_sqm"], errors="coerce")
        safe_plot_area = plot_area.where(plot_area > 0)
        result["plot_to_building_ratio"] = safe_plot_area / area
    else:
        result["plot_to_building_ratio"] = pd.NA

    if "water_body" in result.columns:
        result["has_water_body_nearby"] = result["water_body"].notna().astype("boolean")
    else:
        result["has_water_body_nearby"] = False

    if "listing_updated_date" in result.columns:
        updated = pd.to_datetime(result["listing_updated_date"], errors="coerce")
        reference_naive = pd.Timestamp(reference_date).tz_localize(None) if reference_date.tzinfo else reference_date
        result["days_since_update"] = (reference_naive.normalize() - updated).dt.days
    else:
        result["days_since_update"] = pd.NA

    if "security_features" in result.columns:
        result["security_feature_count"] = result["security_features"].map(
            lambda v: len(v) if isinstance(v, list) else 0
        ).astype("Int64")
    else:
        result["security_feature_count"] = pd.NA

    if report is not None:
        report.record_derived_summary(
            {
                "building_age_years_non_null": int(result["building_age_years"].notna().sum()),
                "is_new_build_true": int((result["is_new_build"] == True).sum()),  # noqa: E712
            }
        )

    return result
