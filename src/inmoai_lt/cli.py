"""Command-line entry points: `python -m inmoai_lt clean` and `... profile`.

Uses only the standard library `argparse` (no extra CLI dependency is listed in
requirements.txt).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from inmoai_lt.config import REPO_ROOT, PipelineConfig, load_config
from inmoai_lt.io import compute_reference_date, load_sources
from inmoai_lt.logging_config import configure_logging
from inmoai_lt.pipeline import run_pipeline

logger = logging.getLogger("inmoai_lt")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="inmoai_lt", description="InmoAI-lt data cleaning pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    clean_parser = subparsers.add_parser("clean", help="Run the full cleaning pipeline.")
    clean_parser.add_argument("--config", type=Path, default=None, help="Path to cleaning.yaml.")
    clean_parser.add_argument("--mappings", type=Path, default=None, help="Path to mappings_lt_en.yaml.")
    clean_parser.add_argument("--raw-dir", type=Path, default=None, help="Directory containing raw source CSVs.")
    clean_parser.add_argument("--out-dir", type=Path, default=None, help="Directory to write outputs to.")

    profile_parser = subparsers.add_parser(
        "profile", help="Print a schema/missingness summary of the cleaned output."
    )
    profile_parser.add_argument("--out-dir", type=Path, default=None, help="Directory containing pipeline outputs.")
    profile_parser.add_argument("--config", type=Path, default=None, help="Path to cleaning.yaml.")
    profile_parser.add_argument("--mappings", type=Path, default=None, help="Path to mappings_lt_en.yaml.")

    return parser


def _load_ctx(args: argparse.Namespace) -> PipelineConfig:
    # `profile` never reads raw sources, so its subparser has no `--raw-dir` flag.
    return load_config(
        config_path=args.config,
        mappings_path=args.mappings,
        raw_dir=getattr(args, "raw_dir", None),
        out_dir=args.out_dir,
    )


def cmd_clean(args: argparse.Namespace) -> int:
    ctx = _load_ctx(args)

    # The log filename is dated by `reference_date` (max scrape_timestamp_utc in the
    # data, never the wall clock), so logging must be configured before `run_pipeline`
    # -- do a cheap source read up front purely to learn that date.
    input_cfg = ctx.cleaning["input"]
    preview_df = load_sources(ctx.raw_dir, input_cfg["sources"], input_cfg["encoding"])
    reference_date = compute_reference_date(preview_df)
    configure_logging(REPO_ROOT / "logs", reference_date.date().isoformat())

    result = run_pipeline(ctx)
    logger.info("reference_date = %s", result.reference_date.isoformat())
    logger.info("clean rows = %d, clean cols = %d", len(result.clean_df), len(result.clean_df.columns))
    logger.info("clean csv = %s", result.clean_csv_path)
    logger.info("analysis csv = %s", result.analysis_csv_path)
    for segment, path in result.segment_csv_paths.items():
        logger.info("segment %s csv = %s", segment, path)
    logger.info("html report = %s", result.html_report_path)
    logger.info("analysis report = %s", result.analysis_report_path)
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    ctx = _load_ctx(args)
    clean_basename = ctx.cleaning["output"]["clean_basename"]
    clean_csv_path = ctx.output_dir / f"{clean_basename}.csv"
    if not clean_csv_path.exists():
        print(f"No cleaned output found at {clean_csv_path}. Run `inmoai_lt clean` first.")
        return 1

    df = pd.read_csv(clean_csv_path, encoding="utf-8-sig")
    print(f"rows: {len(df)}")
    print(f"columns: {len(df.columns)}")
    if "segment" in df.columns:
        print()
        print("segment                              rows")
        print("-" * 60)
        for segment, count in df["segment"].value_counts().sort_index().items():
            print(f"{segment:<35} {count:>8}")
    print()
    print("column                              non-null   dtype")
    print("-" * 60)
    for col in df.columns:
        non_null = int(df[col].notna().sum())
        print(f"{col:<35} {non_null:>8}   {df[col].dtype}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "clean":
        return cmd_clean(args)
    if args.command == "profile":
        return cmd_profile(args)

    parser.print_help()
    return 1
