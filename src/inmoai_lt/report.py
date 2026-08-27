"""Cleaning-run report accumulator: an ordered event log serialised to JSON + Markdown."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CleaningReport:
    """Accumulates events during a pipeline run. All `record_*` methods are additive
    and never mutate previously recorded state in place -- they append to internal
    dict/list structures owned by this object (not shared mutable state passed around).
    """

    def __init__(self) -> None:
        self.reference_date: str | None = None
        self.config_hash: str | None = None
        self.source_files: list[dict[str, Any]] = []
        self.stage_row_counts: list[dict[str, Any]] = []
        self.dropped_columns: list[dict[str, Any]] = []
        self.renamed_columns: dict[str, str] = {}
        self.constant_columns: dict[str, Any] = {}
        self.district_collapse: dict[str, Any] = {}
        self.missing_before: dict[str, Any] = {}
        self.missing_after: dict[str, Any] = {}
        self.identity_duplicates: dict[str, Any] = {}
        self.content_duplicates: dict[str, Any] = {}
        self.quality_flag_counts: dict[str, int] = {}
        self.fatal_removals: dict[str, Any] = {}
        self.attribute_recovery: dict[str, Any] = {}
        self.unmapped_category_values: dict[str, dict[str, int]] = {}
        self.unmapped_attributes: dict[str, Any] = {}
        self.feature_coverage: dict[str, Any] = {}
        self.geo_flags: dict[str, int] = {}
        self.derived_summary: dict[str, Any] = {}
        self.final_counts: dict[str, Any] = {}

    # -- recorders -----------------------------------------------------------------
    def record_source_file(self, name: str, rows: int, sha256: str) -> None:
        self.source_files.append({"file": name, "rows": rows, "sha256": sha256})

    def record_stage(self, stage: str, rows_in: int, rows_out: int) -> None:
        self.stage_row_counts.append(
            {"stage": stage, "rows_in": rows_in, "rows_out": rows_out, "delta": rows_out - rows_in}
        )

    def record_dropped_columns(self, cols, reason: str) -> None:
        for col in cols:
            self.dropped_columns.append({"column": col, "reason": reason})

    def record_renames(self, renames: dict[str, str]) -> None:
        self.renamed_columns.update(renames)

    def record_constant_columns(self, values: dict[str, Any]) -> None:
        self.constant_columns.update(values)

    def record_district_collapse(self, differing_listing_ids, dropped_columns) -> None:
        self.district_collapse = {
            "differing_listing_ids": list(differing_listing_ids),
            "dropped_columns": list(dropped_columns),
        }

    def record_missingness(self, when: str, missing: dict[str, Any]) -> None:
        if when == "before":
            self.missing_before = missing
        else:
            self.missing_after = missing

    def record_identity_duplicates(self, count: int, listing_ids) -> None:
        self.identity_duplicates = {"count": count, "listing_ids": list(listing_ids)}

    def record_content_duplicates(self, group_count: int, duplicate_row_count: int, groups) -> None:
        self.content_duplicates = {
            "group_count": group_count,
            "duplicate_row_count": duplicate_row_count,
            "groups": list(groups),
        }

    def record_quality_flags(self, counts: dict[str, int]) -> None:
        self.quality_flag_counts.update(counts)

    def record_fatal_removals(self, count: int, removals) -> None:
        self.fatal_removals = {"count": count, "removals": list(removals)}

    def record_attribute_recovery(self, counts: dict[str, int], construction_year_mismatches) -> None:
        self.attribute_recovery = {
            "counts": counts,
            "construction_year_mismatches": list(construction_year_mismatches),
        }

    def record_unmapped_category_values(self, unmapped: dict[str, dict[str, int]]) -> None:
        for col, values in unmapped.items():
            self.unmapped_category_values.setdefault(col, {}).update(values)

    def record_unmapped_attributes(self, tally: dict[str, Any]) -> None:
        self.unmapped_attributes.update(tally)

    def record_feature_coverage(self, coverage: dict[str, Any]) -> None:
        self.feature_coverage.update(coverage)

    def record_geo_flags(self, counts: dict[str, int]) -> None:
        self.geo_flags.update(counts)

    def record_derived_summary(self, summary: dict[str, Any]) -> None:
        self.derived_summary.update(summary)

    def record_final_counts(self, clean_rows: int, clean_cols: int, analysis_rows: int, analysis_cols: int) -> None:
        self.final_counts = {
            "clean_rows": clean_rows,
            "clean_cols": clean_cols,
            "analysis_rows": analysis_rows,
            "analysis_cols": analysis_cols,
        }

    # -- serialisation ---------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_date": self.reference_date,
            "config_hash": self.config_hash,
            "source_files": self.source_files,
            "stage_row_counts": self.stage_row_counts,
            "columns": {
                "dropped": self.dropped_columns,
                "renamed": self.renamed_columns,
                "constants": self.constant_columns,
                "district_collapse": self.district_collapse,
            },
            "missingness": {"before": self.missing_before, "after": self.missing_after},
            "duplicates": {
                "identity": self.identity_duplicates,
                "content": self.content_duplicates,
            },
            "quality_flag_counts": self.quality_flag_counts,
            "fatal_removals": self.fatal_removals,
            "attribute_recovery": self.attribute_recovery,
            "unmapped_category_values": self.unmapped_category_values,
            "unmapped_attributes": self.unmapped_attributes,
            "feature_coverage": self.feature_coverage,
            "geo_flags": self.geo_flags,
            "derived_summary": self.derived_summary,
            "final_counts": self.final_counts,
        }

    def write_json(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.to_dict(), sort_keys=True, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_markdown(self, path: Path) -> None:
        lines = [
            "# InmoAI-lt Cleaning Report",
            "",
            f"- reference_date: `{self.reference_date}`",
            f"- config_hash: `{self.config_hash}`",
            "",
            "## Source files",
            "",
        ]
        for src in self.source_files:
            lines.append(f"- `{src['file']}`: {src['rows']} rows, sha256=`{src['sha256']}`")

        lines += ["", "## Stage row counts", "", "| Stage | In | Out | Delta |", "|---|---|---|---|"]
        for s in self.stage_row_counts:
            lines.append(f"| {s['stage']} | {s['rows_in']} | {s['rows_out']} | {s['delta']} |")

        lines += ["", "## Columns dropped", "", "| Column | Reason |", "|---|---|"]
        for d in self.dropped_columns:
            lines.append(f"| {d['column']} | {d['reason']} |")

        lines += ["", "## Attribute recovery", ""]
        for k, v in self.attribute_recovery.get("counts", {}).items():
            lines.append(f"- {k}: {v}")

        lines += ["", "## Quality flag counts", ""]
        for k, v in sorted(self.quality_flag_counts.items()):
            lines.append(f"- flag_{k}: {v}")

        lines += ["", "## Fatal removals", ""]
        lines.append(f"- count: {self.fatal_removals.get('count', 0)}")

        lines += ["", "## Duplicates", ""]
        lines.append(f"- identity duplicates dropped: {self.identity_duplicates.get('count', 0)}")
        lines.append(f"- content duplicate groups: {self.content_duplicates.get('group_count', 0)}")
        lines.append(f"- content duplicate rows (non-primary): {self.content_duplicates.get('duplicate_row_count', 0)}")

        lines += ["", "## Unmapped category values", ""]
        if self.unmapped_category_values:
            for col, values in self.unmapped_category_values.items():
                for value, count in values.items():
                    lines.append(f"- {col}: `{value}` x{count}")
        else:
            lines.append("- none")

        lines += ["", "## Unmapped raw attribute labels", ""]
        if self.unmapped_attributes:
            for label, info in self.unmapped_attributes.items():
                lines.append(f"- {label}: count={info['count']}, sample=`{info['sample_value']}`")
        else:
            lines.append("- none")

        lines += ["", "## Feature coverage", ""]
        for ptype, features in self.feature_coverage.items():
            captured = [k for k, v in features.items() if v]
            absent = [k for k, v in features.items() if not v]
            lines.append(f"- {ptype}: captured={captured}, structurally absent={absent}")

        lines += ["", "## Final counts", ""]
        for k, v in self.final_counts.items():
            lines.append(f"- {k}: {v}")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
