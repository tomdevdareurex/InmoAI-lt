"""Tests for the self-contained HTML cleaning report."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from inmoai_lt.config import PipelineConfig
from inmoai_lt.html_report import _bar_chart_html, write_html_report
from inmoai_lt.pipeline import run_pipeline
from inmoai_lt.report import CleaningReport


def _run(raw_dir: Path, out_dir: Path, cleaning: dict, mappings: dict):
    ctx = PipelineConfig(
        cleaning=cleaning,
        mappings=mappings,
        config_hash="test-hash",
        raw_dir=raw_dir,
        output_dir=out_dir,
    )
    return run_pipeline(ctx)


def test_bar_chart_helper_handles_empty_and_zero_data():
    # Arrange / Act
    empty_html = _bar_chart_html({})
    zero_html = _bar_chart_html({"a": 0, "b": 0})

    # Assert
    assert "none recorded" in empty_html
    assert "width:0.0%" in zero_html or "width:0%" in zero_html


def test_write_html_report_handles_all_empty_optional_sections(tmp_path, synthetic_cleaning_config):
    # Arrange
    report = CleaningReport()
    report.reference_date = "2026-01-01"
    report.config_hash = "abc123"
    report.record_final_counts(clean_rows=1, clean_cols=1, analysis_rows=1, analysis_cols=1)
    sample_df = pd.DataFrame({"listing_id": ["1"], "district": ["Senamiestis"]})
    out_path = tmp_path / "cleaning_report.html"

    # Act
    write_html_report(report, sample_df, synthetic_cleaning_config, out_path)

    # Assert
    html = out_path.read_text(encoding="utf-8")
    assert "none recorded" in html
    assert "not measured in this run" in html
    assert "<!DOCTYPE html>" in html


def test_write_html_report_via_full_pipeline_run(tmp_path, synthetic_raw_dir, synthetic_cleaning_config, mappings):
    # Arrange
    out_dir = tmp_path / "out"

    # Act
    result = _run(synthetic_raw_dir, out_dir, synthetic_cleaning_config, mappings)

    # Assert
    html_path = out_dir / "cleaning_report.html"
    assert html_path.exists()
    assert html_path == result.html_report_path
    html = html_path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert '<link rel="stylesheet" href="http' not in html
    assert '<script src="http' not in html
    assert "@import url(http" not in html


def test_sample_table_row_cap_and_columns(tmp_path, synthetic_cleaning_config):
    # Arrange
    report = CleaningReport()
    report.reference_date = "2026-01-01"
    report.config_hash = "abc123"
    report.record_final_counts(clean_rows=20, clean_cols=1, analysis_rows=20, analysis_cols=1)
    sample_df = pd.DataFrame(
        {
            "listing_id": [str(i) for i in range(20)],
            "district": ["Senamiestis"] * 20,
            "price_eur": [100000] * 20,
        }
    )
    out_path = tmp_path / "cleaning_report.html"

    # Act
    write_html_report(report, sample_df, synthetic_cleaning_config, out_path)

    # Assert
    html = out_path.read_text(encoding="utf-8")
    assert html.count("<tr>") - 1 <= 15  # minus the header row
    assert "price_eur" in html
    assert "district" in html


def test_html_escapes_lithuanian_text_and_special_characters(tmp_path, synthetic_raw_dir, synthetic_cleaning_config, mappings):
    # Arrange
    out_dir = tmp_path / "out"

    # Act
    _run(synthetic_raw_dir, out_dir, synthetic_cleaning_config, mappings)

    # Assert
    html = (out_dir / "cleaning_report.html").read_text(encoding="utf-8")
    assert "Žirmūnai" in html

    # Arrange (unit-level escaping check)
    report = CleaningReport()
    report.reference_date = "2026-01-01"
    report.config_hash = "abc123"
    report.record_final_counts(clean_rows=1, clean_cols=1, analysis_rows=1, analysis_cols=1)
    sample_df = pd.DataFrame({"listing_id": ["<script>&"], "district": ["<b>x</b>"]})
    out_path = tmp_path / "unit_report.html"

    # Act
    write_html_report(report, sample_df, synthetic_cleaning_config, out_path)

    # Assert
    unit_html = out_path.read_text(encoding="utf-8")
    assert "<script>&" not in unit_html
    assert "&lt;script&gt;&amp;" in unit_html
