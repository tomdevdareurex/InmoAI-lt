"""Coordinate validation flags. No geocoding, no external geography joins (deferred)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def flag_coordinates(
    df: pd.DataFrame,
    vilnius_bbox: dict[str, float],
    lithuania_bbox: dict[str, float],
    report: Any = None,
) -> pd.DataFrame:
    """Add `flag_missing_coordinates`, `flag_coords_outside_lithuania`,
    `flag_coords_outside_vilnius`, `flag_coords_approximate`; round lat/lon to 6dp;
    drop `coordinate_precision`.

    "No coordinates" and "coordinates in the wrong place" are separate facts and get
    separate flags. Only the latter is blocking -- treating a missing location as a
    location outside Vilnius would silently invalidate every listing whose source simply
    never published coordinates.
    """
    result = df.copy()
    lat = pd.to_numeric(result["latitude"], errors="coerce")
    lon = pd.to_numeric(result["longitude"], errors="coerce")

    missing = lat.isna() | lon.isna()
    outside_lithuania = ~missing & (
        (lat < lithuania_bbox["lat_min"])
        | (lat > lithuania_bbox["lat_max"])
        | (lon < lithuania_bbox["lon_min"])
        | (lon > lithuania_bbox["lon_max"])
    )
    outside_vilnius = ~missing & (
        (lat < vilnius_bbox["lat_min"])
        | (lat > vilnius_bbox["lat_max"])
        | (lon < vilnius_bbox["lon_min"])
        | (lon > vilnius_bbox["lon_max"])
    )

    result["flag_missing_coordinates"] = missing.astype("boolean")
    result["flag_coords_outside_lithuania"] = outside_lithuania.astype("boolean")
    result["flag_coords_outside_vilnius"] = outside_vilnius.astype("boolean")

    if "coordinate_precision" in result.columns:
        result["flag_coords_approximate"] = (
            result["coordinate_precision"] == "approximate"
        ).astype("boolean")
        result = result.drop(columns=["coordinate_precision"])
    else:
        result["flag_coords_approximate"] = pd.array([False] * len(result), dtype="boolean")

    result["latitude"] = lat.round(6)
    result["longitude"] = lon.round(6)

    if report is not None:
        report.record_geo_flags(
            {
                "flag_missing_coordinates": int(missing.sum()),
                "flag_coords_outside_lithuania": int(outside_lithuania.sum()),
                "flag_coords_outside_vilnius": int(outside_vilnius.sum()),
                "flag_coords_approximate": int(result["flag_coords_approximate"].sum()),
            }
        )

    return result
