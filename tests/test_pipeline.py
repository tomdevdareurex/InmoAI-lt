"""End-to-end pipeline tests: reproducibility and Lithuanian text round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from inmoai_lt.config import PipelineConfig
from inmoai_lt.pipeline import run_pipeline


def _run(raw_dir: Path, out_dir: Path, cleaning: dict, mappings: dict) -> None:
    ctx = PipelineConfig(
        cleaning=cleaning,
        mappings=mappings,
        config_hash="test-hash",
        raw_dir=raw_dir,
        output_dir=out_dir,
    )
    run_pipeline(ctx)


def _strip_timestamps(report: dict) -> dict:
    """Drop the one genuinely time-varying field (`reference_date` is deterministic --
    derived from the fixture's own `scrape_timestamp_utc` -- so nothing needs stripping
    today, but this keeps the comparison robust if a wall-clock field is ever added).
    """
    report = dict(report)
    report.pop("generated_at", None)
    return report


def test_pipeline_is_reproducible(tmp_path, synthetic_raw_dir, synthetic_cleaning_config, mappings):
    out_dir_1 = tmp_path / "out1"
    out_dir_2 = tmp_path / "out2"

    _run(synthetic_raw_dir, out_dir_1, synthetic_cleaning_config, mappings)
    _run(synthetic_raw_dir, out_dir_2, synthetic_cleaning_config, mappings)

    clean_basename = synthetic_cleaning_config["output"]["clean_basename"]
    analysis_basename = synthetic_cleaning_config["output"]["analysis_basename"]

    clean_1 = (out_dir_1 / f"{clean_basename}.csv").read_bytes()
    clean_2 = (out_dir_2 / f"{clean_basename}.csv").read_bytes()
    assert clean_1 == clean_2

    analysis_1 = (out_dir_1 / f"{analysis_basename}.csv").read_bytes()
    analysis_2 = (out_dir_2 / f"{analysis_basename}.csv").read_bytes()
    assert analysis_1 == analysis_2

    report_1 = _strip_timestamps(json.loads((out_dir_1 / "cleaning_report.json").read_text(encoding="utf-8")))
    report_2 = _strip_timestamps(json.loads((out_dir_2 / "cleaning_report.json").read_text(encoding="utf-8")))
    assert report_1 == report_2


def test_lithuanian_text_survives_round_trip(tmp_path, synthetic_raw_dir, synthetic_cleaning_config, mappings):
    out_dir = tmp_path / "out"
    _run(synthetic_raw_dir, out_dir, synthetic_cleaning_config, mappings)

    clean_basename = synthetic_cleaning_config["output"]["clean_basename"]
    result = pd.read_csv(out_dir / f"{clean_basename}.csv", encoding="utf-8-sig")

    assert (result["district"] == "Žirmūnai").any()
    assert result["title_lt"].str.contains("ąčęėįšųūž", na=False).any()
    # Window orientation tokens are casefolded, mapped and sorted alphabetically;
    # "Šiaurė, pietūs" (north, south -- unsorted in the source) must come out as
    # "north,south" and both direction booleans must be True.
    row = result.loc[result["district"] == "Žirmūnai"].iloc[0]
    assert row["window_orientation"] == "north,south"
    assert bool(row["orientation_north"]) is True
    assert bool(row["orientation_south"]) is True


def test_fatal_filter_and_dedup_flags_present(tmp_path, synthetic_raw_dir, synthetic_cleaning_config, mappings):
    out_dir = tmp_path / "out"
    _run(synthetic_raw_dir, out_dir, synthetic_cleaning_config, mappings)

    clean_basename = synthetic_cleaning_config["output"]["clean_basename"]
    result = pd.read_csv(out_dir / f"{clean_basename}.csv", encoding="utf-8-sig")

    # All 4 synthetic rows satisfy the fatal-filter requirements -- none should be removed.
    assert len(result) == 4

    # Rows 2-0000002 / 2-0000003 share a content key; the earlier-updated, lower-views
    # listing (2-0000002) must be flagged as the non-primary duplicate.
    dup_row = result.loc[result["listing_id"] == "2-0000002"].iloc[0]
    primary_row = result.loc[result["listing_id"] == "2-0000003"].iloc[0]
    assert bool(dup_row["is_duplicate"]) is True
    assert bool(primary_row["is_duplicate"]) is False
