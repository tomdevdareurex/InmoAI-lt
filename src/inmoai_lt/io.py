"""Stage 1 (load) and Stage 10 (write) I/O for the pipeline."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from inmoai_lt import schema

logger = logging.getLogger("inmoai_lt")


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_sources(
    raw_dir: Path,
    sources_cfg: list[dict[str, Any]],
    encoding: str,
    report: Any = None,
) -> pd.DataFrame:
    """Load each enabled source CSV, validate its schema, tag it, and concatenate.

    Fails loudly on a schema mismatch (see `schema.assert_raw_schema`).
    """
    frames = []
    for source in sources_cfg:
        if not source.get("enabled", False):
            logger.info("skipping disabled source %s", source["file"])
            continue
        path = raw_dir / source["file"]
        df = pd.read_csv(path, encoding=encoding, dtype=str)
        schema.assert_raw_schema(df.columns, source_name=source["file"])

        df = df.copy()
        df["source_file"] = source["file"]
        # `property_type`/`listing_type` are already present and correct in every raw
        # source CSV (measured -- see docs/DATA_PROFILE.md); the config's per-source
        # `property_type`/`listing_type` fields describe/enable the source rather than
        # overwrite verified data, so real values from the file are never overwritten.
        frames.append(df)

        if report is not None:
            report.record_source_file(
                name=source["file"], rows=len(df), sha256=_sha256_of_file(path)
            )
        logger.info("loaded %s: %d rows", source["file"], len(df))

    if not frames:
        raise ValueError("No enabled sources produced any data.")

    combined = pd.concat(frames, axis=0, ignore_index=True)
    logger.info("combined input: %d rows", len(combined))
    return combined


def compute_reference_date(df: pd.DataFrame) -> pd.Timestamp:
    """`reference_date` = max `scrape_timestamp_utc` across all rows.

    Never `datetime.now()` -- this is what makes reruns reproducible.
    """
    timestamps = pd.to_datetime(df["scrape_timestamp_utc"], errors="coerce", utc=True)
    reference_date = timestamps.max()
    if pd.isna(reference_date):
        raise ValueError("Could not compute reference_date: all scrape_timestamp_utc values are invalid.")
    return reference_date


@dataclass(frozen=True)
class OutputPaths:
    clean_csv: Path
    analysis_csv: Path
    segment_csvs: dict[str, Path]


def write_outputs(
    clean_df: pd.DataFrame,
    output_dir: Path,
    clean_basename: str,
    analysis_basename: str,
    float_round: int,
    write_parquet: bool,
    segment_dir: str = "segments",
) -> OutputPaths:
    """Enforce final column order, round floats, sort, and write clean + analysis outputs.

    The analysis frame is additionally partitioned by `segment` into one file each, so a
    rent apartment and a sale house are never pooled into a single distribution.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    ordered_cols = schema.enforce_final_column_order(clean_df.columns)
    result = clean_df[ordered_cols].copy()

    float_cols = result.select_dtypes(include=["float64", "float32"]).columns
    for col in float_cols:
        result[col] = result[col].round(float_round)

    sort_cols = [c for c in ("property_type", "listing_id") if c in result.columns]
    if sort_cols:
        result = result.sort_values(by=sort_cols, kind="mergesort").reset_index(drop=True)

    clean_csv_path = output_dir / f"{clean_basename}.csv"
    _write_csv(result, clean_csv_path)

    is_valid_mask = result["is_valid"].fillna(False) if "is_valid" in result.columns else pd.Series(True, index=result.index)
    is_duplicate_mask = result["is_duplicate"].fillna(False) if "is_duplicate" in result.columns else pd.Series(False, index=result.index)
    analysis_df = result.loc[is_valid_mask & ~is_duplicate_mask].reset_index(drop=True)

    analysis_csv_path = output_dir / f"{analysis_basename}.csv"
    _write_csv(analysis_df, analysis_csv_path)

    if write_parquet:
        result.to_parquet(output_dir / f"{clean_basename}.parquet", index=False)
        analysis_df.to_parquet(output_dir / f"{analysis_basename}.parquet", index=False)

    segment_csvs = _write_segment_outputs(
        analysis_df, output_dir / segment_dir, write_parquet
    )

    return OutputPaths(
        clean_csv=clean_csv_path,
        analysis_csv=analysis_csv_path,
        segment_csvs=segment_csvs,
    )


def _write_segment_outputs(
    analysis_df: pd.DataFrame, segment_dir: Path, write_parquet: bool
) -> dict[str, Path]:
    """Split `analysis_df` by `segment` into one file per segment.

    Segments come from the values actually present (sorted, so output is deterministic),
    which is what lets a future `house_rent` source appear with no code change.
    """
    if "segment" not in analysis_df.columns:
        return {}

    segment_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for segment in sorted(analysis_df["segment"].dropna().unique()):
        subset = analysis_df.loc[analysis_df["segment"] == segment].reset_index(drop=True)
        path = segment_dir / f"{segment}_analysis.csv"
        _write_csv(subset, path)
        if write_parquet:
            subset.to_parquet(segment_dir / f"{segment}_analysis.parquet", index=False)
        paths[str(segment)] = path
        logger.info("wrote segment %s: %d rows", segment, len(subset))
    return paths


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, encoding="utf-8-sig", index=False, lineterminator="\n")


def write_unmapped_attributes(unmapped: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "unmapped_attributes.csv"
    rows = [
        {
            "label": label,
            "count": info["count"],
            "sample_value": info["sample_value"],
            "sample_url": info["sample_url"],
        }
        for label, info in unmapped.items()
    ]
    df = pd.DataFrame(rows, columns=["label", "count", "sample_value", "sample_url"])
    _write_csv(df, path)
    return path
