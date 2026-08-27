"""Recover data stranded in `raw_attributes_json`.

Labels already promoted by the scraper into their own column are consumed silently
(they are not "recovered", just confirmed). Labels that never made it to a promoted
column are the recovery target of this module. Anything left over is surfaced in
`unmapped_attributes` rather than dropped.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import pandas as pd

from inmoai_lt.cleaning.parsers import parse_decimal, parse_years

# Labels the scraper already promoted to a dedicated column. Present in
# raw_attributes_json but not "recovered" here -- just acknowledged so they don't show
# up as unmapped.
_ALREADY_PROMOTED_LABELS = {
    "Aukštas",
    "Aukštų sk.",
    "Kambarių sk.",
    "Pastato tipas",
    "Plotas",
    "Įrengimas",
    "Šildymas",
    "Pastato energijos suvartojimo klasė",
    "Buto numeris",
    "Namo tipas",
    "Sklypo plotas",
    "Vanduo",
    "Metai",  # partially promoted (construction_year); renovation_year recovered here
}

# Fallback vocabularies, used only if the caller does not supply config-driven maps
# (e.g. in unit tests). Production runs pass the maps loaded from
# config/mappings_lt_en.yaml so the vocabulary lives in exactly one place.
_DEFAULT_ORIENTATION_LT = {"šiaurė": "north", "pietūs": "south", "rytai": "east", "vakarai": "west"}
_DEFAULT_WATER_BODY_LT = {
    "ežeras": "lake",
    "upė": "river",
    "tvenkinys": "pond",
    "jūra": "sea",
    "marios": "lagoon",
}
_DEFAULT_OBJECT_TYPE_LT = {
    "buto dalis": "apartment_share",
    "patalpa, poilsio paskirtis": "recreational_premises",
    "patalpa, viešbučių paskirtis": "hotel_premises",
}


def _load_json(raw: object) -> dict[str, Any]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_orientation(raw: Optional[str], orientation_map: dict[str, str]) -> dict[str, Any]:
    result = {
        "orientation_north": pd.NA,
        "orientation_south": pd.NA,
        "orientation_east": pd.NA,
        "orientation_west": pd.NA,
        "orientation_count": pd.NA,
        "window_orientation": pd.NA,
    }
    if not raw:
        return result
    tokens = [t.strip().casefold() for t in raw.split(",") if t.strip()]
    english = sorted({orientation_map[t] for t in tokens if t in orientation_map})
    if not english:
        return result
    result["orientation_north"] = "north" in english
    result["orientation_south"] = "south" in english
    result["orientation_east"] = "east" in english
    result["orientation_west"] = "west" in english
    result["orientation_count"] = len(english)
    result["window_orientation"] = ",".join(english)
    return result


def _recover_row(
    raw_json: object,
    object_type_map: dict[str, str],
    water_body_map: dict[str, str],
    orientation_map: dict[str, str],
) -> dict[str, Any]:
    attrs = _load_json(raw_json)

    metai_raw = attrs.get("Metai")
    construction_recovered, renovation_year = parse_years(metai_raw)

    house_number = attrs.get("Namo numeris")
    house_number = house_number.strip() if isinstance(house_number, str) and house_number.strip() else None

    cadastral_id = attrs.get("Unikalus daikto numeris (RC numeris)")
    cadastral_id = cadastral_id.strip() if isinstance(cadastral_id, str) and cadastral_id.strip() else None

    object_type_lt = attrs.get("Objektas")
    object_type_lt = object_type_lt.strip() if isinstance(object_type_lt, str) and object_type_lt.strip() else None
    object_type = None
    if object_type_lt:
        object_type = object_type_map.get(object_type_lt.strip().casefold(), object_type_lt)

    water_body_lt = attrs.get("Artimiausias vandens telkinys")
    water_body_lt = water_body_lt.strip() if isinstance(water_body_lt, str) and water_body_lt.strip() else None
    water_body = None
    if water_body_lt:
        water_body = water_body_map.get(water_body_lt.strip().casefold(), water_body_lt)

    distance_raw = attrs.get("Iki vandens telkinio (m)")
    distance_to_water_m = parse_decimal(distance_raw) if distance_raw else None

    orientation_fields = _parse_orientation(attrs.get("Langų orientacija"), orientation_map)

    unmapped = {
        label: value
        for label, value in attrs.items()
        if label not in _ALREADY_PROMOTED_LABELS
        and label
        not in {
            "Namo numeris",
            "Langų orientacija",
            "Unikalus daikto numeris (RC numeris)",
            "Objektas",
            "Artimiausias vandens telkinys",
            "Iki vandens telkinio (m)",
        }
    }

    result: dict[str, Any] = {
        "construction_year_recovered": construction_recovered,
        "renovation_year": renovation_year,
        "has_renovation": renovation_year is not None,
        "house_number": house_number,
        "cadastral_id": cadastral_id,
        "object_type_lt": object_type_lt,
        "object_type": object_type,
        "water_body_lt": water_body_lt,
        "water_body": water_body,
        "distance_to_water_m": distance_to_water_m,
        "_unmapped_attributes": unmapped,
    }
    result.update(orientation_fields)
    return result


def recover_attributes(
    df: pd.DataFrame,
    report: Any = None,
    object_type_map: Optional[dict[str, str]] = None,
    water_body_map: Optional[dict[str, str]] = None,
    orientation_map: Optional[dict[str, str]] = None,
) -> pd.DataFrame:
    """Recover renovation_year, window_orientation, house_number, cadastral_id,
    object_type, water_body, distance_to_water_m from `raw_attributes_json`.

    `object_type_map`, `water_body_map`, `orientation_map` should be the
    case-folded vocabularies loaded from `config/mappings_lt_en.yaml`
    (`categorical.build_lookup(mappings["object_type"])`, etc). Falls back to a
    built-in copy of the vocabulary when not supplied (used by unit tests).

    Drops `raw_attributes_json` from the output after recovery. Asserts the recovered
    construction year matches the existing `construction_year` column where both exist,
    logging mismatches.
    """
    if "raw_attributes_json" not in df.columns:
        return df

    object_type_map = object_type_map if object_type_map is not None else _DEFAULT_OBJECT_TYPE_LT
    water_body_map = water_body_map if water_body_map is not None else _DEFAULT_WATER_BODY_LT
    orientation_map = orientation_map if orientation_map is not None else _DEFAULT_ORIENTATION_LT

    recovered_rows = df["raw_attributes_json"].map(
        lambda raw: _recover_row(raw, object_type_map, water_body_map, orientation_map)
    )
    recovered_df = pd.DataFrame(list(recovered_rows), index=df.index)

    mismatches = []
    if "construction_year" in df.columns:
        existing = pd.to_numeric(df["construction_year"], errors="coerce")
        recovered_year = pd.to_numeric(recovered_df["construction_year_recovered"], errors="coerce")
        both_present = existing.notna() & recovered_year.notna()
        differs = both_present & (existing != recovered_year)
        if differs.any():
            id_col = df["listing_id"] if "listing_id" in df.columns else df.index.to_series()
            mismatches = id_col[differs].tolist()
        # Prefer the existing value; fall back to the recovered value when missing.
        df = df.copy()
        df["construction_year"] = existing.where(existing.notna(), recovered_year)
    elif report is not None:
        df = df.copy()
        df["construction_year"] = recovered_df["construction_year_recovered"]

    result = pd.concat(
        [df.drop(columns=["raw_attributes_json"]), recovered_df.drop(columns=["construction_year_recovered", "_unmapped_attributes"])],
        axis=1,
    )

    if report is not None:
        report.record_attribute_recovery(
            counts={
                "renovation_year": int(recovered_df["renovation_year"].notna().sum()),
                "window_orientation": int(recovered_df["window_orientation"].notna().sum()),
                "house_number": int(recovered_df["house_number"].notna().sum()),
                "cadastral_id": int(recovered_df["cadastral_id"].notna().sum()),
                "object_type": int(recovered_df["object_type"].notna().sum()),
                "water_body": int(recovered_df["water_body"].notna().sum()),
                "distance_to_water_m": int(recovered_df["distance_to_water_m"].notna().sum()),
            },
            construction_year_mismatches=mismatches,
        )
        _record_unmapped(df, recovered_df, report)

    return result


def _record_unmapped(df: pd.DataFrame, recovered_df: pd.DataFrame, report: Any) -> None:
    from collections import defaultdict

    tally: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "sample_value": None, "sample_url": None})
    url_col = df["listing_url"] if "listing_url" in df.columns else None
    for idx, unmapped in recovered_df["_unmapped_attributes"].items():
        for label, value in unmapped.items():
            entry = tally[label]
            entry["count"] += 1
            if entry["sample_value"] is None:
                entry["sample_value"] = value
                entry["sample_url"] = url_col.loc[idx] if url_col is not None else None
    report.record_unmapped_attributes(dict(tally))
