"""Pipeline orchestration: runs all cleaning stages in order.

Every stage function takes a DataFrame (and config/report/logger context) and returns
a NEW DataFrame. No `inplace=True` anywhere.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from inmoai_lt.cleaning import attributes, categorical, columns, dedup, derive, features, geo, quality
from inmoai_lt.cleaning.parsers import (
    normalize_text,
    parse_iso_date,
    parse_iso_datetime_utc,
    to_nullable_int_series,
)
from inmoai_lt.config import PipelineConfig
from inmoai_lt.io import compute_reference_date, load_sources, write_outputs, write_unmapped_attributes
from inmoai_lt.report import CleaningReport

logger = logging.getLogger("inmoai_lt")

_INT_COLUMNS = [
    "rooms",
    "floor",
    "total_floors",
    "construction_year",
    "renovation_year",
    "views_count",
    "saved_by_users_count",
    "image_count",
    "source_page_number",
    "search_position",
    "listing_age_days",
]
_DATE_COLUMNS = ["listing_created_date", "listing_updated_date"]
_TEXT_COLUMNS = ["district", "street", "full_address", "title_lt", "description_lt", "energy_class"]
_JSON_LIST_COLUMNS = ["image_urls", "security_features", "diagnostic_warnings"]

# `apply_multi_value_mapping`'s canonical water tokens (from mappings_lt_en.yaml) are
# "city_water"/"local_water", but the plan's boolean column names are the shorter
# `water_city`/`water_local` (bool_prefix "water" + suffix, not the full token).
_WATER_SUPPLY_TOKEN_SUFFIXES = {"city_water": "city", "local_water": "local"}

import json


@dataclass
class PipelineResult:
    clean_df: pd.DataFrame
    report: CleaningReport
    reference_date: pd.Timestamp
    clean_csv_path: Path
    analysis_csv_path: Path


def _normalize_types_and_categories(df: pd.DataFrame, ctx: PipelineConfig, report: CleaningReport) -> pd.DataFrame:
    """Stage 4: numeric/int coercion, dates, categoricals, multi-value fields, text, JSON."""
    result = df.copy()

    for col in _INT_COLUMNS:
        if col in result.columns:
            result[col] = to_nullable_int_series(result[col])

    for col in _DATE_COLUMNS:
        if col in result.columns:
            result[col] = result[col].map(parse_iso_date)

    if "scrape_timestamp_utc" in result.columns:
        result["scrape_timestamp_utc"] = result["scrape_timestamp_utc"].map(parse_iso_datetime_utc)

    for col in _TEXT_COLUMNS:
        if col in result.columns:
            result[col] = result[col].map(normalize_text)

    for col in _JSON_LIST_COLUMNS:
        if col in result.columns:
            result[col] = result[col].map(_parse_json_list)

    mappings = ctx.mappings
    result = categorical.apply_categorical_mapping(
        result,
        {
            "building_type": mappings.get("building_type", {}),
            "condition": mappings.get("condition", {}),
            "house_type": mappings.get("house_type", {}),
        },
        report=report,
    )

    if "heating_type" in result.columns:
        result = categorical.apply_multi_value_mapping(
            result,
            source_col="heating_type",
            types_col="heating_types",
            count_col="heating_type_count",
            bool_prefix="heating",
            vocabulary=mappings.get("heating_type", {}),
            boolean_tokens=categorical.HEATING_TOKENS,
            report=report,
        )

    if "water_supply" in result.columns:
        result = categorical.apply_multi_value_mapping(
            result,
            source_col="water_supply",
            types_col="water_supply_types",
            count_col="water_supply_type_count",
            bool_prefix="water",
            vocabulary=mappings.get("water_supply", {}),
            boolean_tokens=categorical.WATER_SUPPLY_TOKENS,
            report=report,
            token_suffixes=_WATER_SUPPLY_TOKEN_SUFFIXES,
        )

    # `security_features` (e.g. ["Vaizdo kameros"]) has no controlled vocabulary in
    # config/mappings_lt_en.yaml -- it is already parsed to a list above (JSON columns
    # loop) and kept verbatim in Lithuanian; `security_feature_count` is added in
    # derive.py. Translating it would require inventing an unmeasured vocabulary,
    # which the "don't fabricate" rule forbids.

    return result


def _parse_json_list(raw: object) -> list:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def run_pipeline(ctx: PipelineConfig) -> PipelineResult:
    """Run every cleaning stage in order and write the final outputs."""
    report = CleaningReport()
    report.config_hash = ctx.config_hash

    input_cfg = ctx.cleaning["input"]
    df = load_sources(ctx.raw_dir, input_cfg["sources"], input_cfg["encoding"], report=report)
    rows_after_load = len(df)
    report.record_stage("load", rows_after_load, rows_after_load)

    reference_date = compute_reference_date(df)
    report.reference_date = reference_date.isoformat()
    logger.info("reference_date = %s", reference_date.isoformat())

    # Stage 2 -- column normalisation
    rows_before = len(df)
    df = columns.normalize_column_names(df, report=report)
    df = columns.drop_all_null_columns(df, report=report)
    df = columns.collapse_redundant_columns(df, report=report)
    df = columns.collapse_district(df, report=report)
    df = columns.drop_constant_columns(df, report=report)
    report.record_stage("column_normalisation", rows_before, len(df))

    # Stage 3 -- attribute recovery
    rows_before = len(df)
    mappings = ctx.mappings
    df = attributes.recover_attributes(
        df,
        report=report,
        object_type_map=categorical.build_lookup(mappings.get("object_type", {})),
        water_body_map=categorical.build_lookup(mappings.get("water_body", {})),
        orientation_map=categorical.build_lookup(mappings.get("orientation", {})),
    )
    report.record_stage("attribute_recovery", rows_before, len(df))

    # Always written (header-only when empty) -- Stage 10 lists it as a standing output
    # so a future scrape with new raw_attributes_json labels surfaces here automatically.
    write_unmapped_attributes(report.unmapped_attributes, ctx.output_dir)

    # Stage 4 -- type & value normalisation
    rows_before = len(df)
    df = _normalize_types_and_categories(df, ctx, report)
    report.record_stage("type_normalisation", rows_before, len(df))

    # Stage 5 -- boolean features
    rows_before = len(df)
    df = features.expand_boolean_features(df, report=report)
    report.record_stage("boolean_features", rows_before, len(df))

    # Stage 6 -- geography
    rows_before = len(df)
    quality_cfg = ctx.cleaning["quality"]
    df = geo.flag_coordinates(df, quality_cfg["vilnius_bbox"], quality_cfg["lithuania_bbox"], report=report)
    report.record_stage("geography", rows_before, len(df))

    # Stage 7 -- duplicates
    rows_before = len(df)
    dedup_cfg = ctx.cleaning["dedup"]
    df = dedup.flag_identity_duplicates(df, report=report)
    df = dedup.flag_content_duplicates(
        df, dedup_cfg["content_key"], dedup_cfg["area_round_dp"], report=report
    )
    report.record_stage("duplicates", rows_before, len(df))

    # Stage 8 -- quality flags & fatal filter
    rows_before = len(df)
    df = quality.compute_quality_flags(df, quality_cfg, reference_date, report=report)
    df = quality.apply_fatal_filter(df, quality_cfg["fatal"], report=report)
    report.record_stage("quality_and_fatal_filter", rows_before, len(df))

    # Stage 9 -- derived features
    rows_before = len(df)
    df = derive.add_derived_features(df, reference_date, report=report)
    report.record_stage("derive", rows_before, len(df))

    # Stage 10 -- output
    output_cfg = ctx.cleaning["output"]
    clean_csv_path, analysis_csv_path = write_outputs(
        df,
        ctx.output_dir,
        output_cfg["clean_basename"],
        output_cfg["analysis_basename"],
        output_cfg["float_round"],
        output_cfg["write_parquet"],
    )

    ordered_clean = pd.read_csv(clean_csv_path, encoding="utf-8-sig")
    ordered_analysis = pd.read_csv(analysis_csv_path, encoding="utf-8-sig")
    report.record_final_counts(
        clean_rows=len(ordered_clean),
        clean_cols=len(ordered_clean.columns),
        analysis_rows=len(ordered_analysis),
        analysis_cols=len(ordered_analysis.columns),
    )

    report.write_json(ctx.output_dir / "cleaning_report.json")
    report.write_markdown(ctx.output_dir / "cleaning_report.md")

    return PipelineResult(
        clean_df=df,
        report=report,
        reference_date=reference_date,
        clean_csv_path=clean_csv_path,
        analysis_csv_path=analysis_csv_path,
    )
