"""Self-contained HTML rendering of a `CleaningReport`: methodology + measured results.

Written once per `clean` run, alongside `cleaning_report.json`/`.md`. No external
network calls (no CDN fonts/CSS/JS) and no new dependency beyond pandas -- charts are
plain CSS bars, tables are `pandas.DataFrame.to_html()` or hand-built strings.
"""

from __future__ import annotations

import html as html_lib
from pathlib import Path
from typing import Any

import pandas as pd

from inmoai_lt.report import CleaningReport

# Curated preview columns, one or two per FINAL_COLUMN_ORDER group (schema.py). Filtered
# to columns actually present before rendering -- never assume one exists.
_SAMPLE_COLUMNS: list[str] = [
    "listing_id", "property_type", "district", "price_eur", "price_per_sqm_eur",
    "rooms", "total_area_sqm", "floor", "total_floors", "condition",
    "quality_flags", "is_valid", "is_duplicate",
]

_SAMPLE_ROW_LIMIT = 15
_DUPLICATE_GROUP_PREVIEW_LIMIT = 10

_STYLE = """
body { font-family: -apple-system, "Segoe UI", Arial, sans-serif; margin: 0; padding: 0;
       background: #f7f7f9; color: #1a1a1a; }
main { max-width: 960px; margin: 0 auto; padding: 24px 32px 64px; }
h1 { font-size: 1.6rem; margin-bottom: 4px; }
h2 { font-size: 1.2rem; margin-top: 40px; border-bottom: 2px solid #ddd; padding-bottom: 6px; }
h3 { font-size: 1rem; margin-top: 20px; }
p.lede { color: #555; margin-top: 0; }
p.meta { color: #777; font-size: 0.85rem; }
p.methodology { color: #333; background: #fff; border-left: 3px solid #6a7fdb;
                padding: 8px 12px; margin: 8px 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 0.88rem; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #e3e3e3; }
th { background: #eef0f7; }
.fallback { color: #888; font-style: italic; }
.bar-row { display: flex; align-items: center; gap: 8px; margin: 3px 0; font-size: 0.85rem; }
.bar-label { flex: 0 0 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { flex: 1 1 auto; background: #e6e6ec; border-radius: 3px; height: 14px; }
.bar-fill { background: #6a7fdb; height: 100%; border-radius: 3px; }
.bar-fill.blocking { background: #d9534f; }
.bar-value { flex: 0 0 60px; text-align: right; color: #444; }
.stat-grid { display: flex; gap: 16px; flex-wrap: wrap; }
.stat-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 10px 16px;
             min-width: 140px; }
.stat-card .n { font-size: 1.4rem; font-weight: 600; }
.stat-card .l { color: #777; font-size: 0.8rem; }
footer { color: #999; font-size: 0.8rem; margin-top: 48px; }
"""


def write_html_report(
    report: CleaningReport,
    sample_df: pd.DataFrame,
    cleaning_cfg: dict[str, Any],
    path: Path,
) -> None:
    """Render `report` + a sample of `sample_df` to a self-contained HTML file at `path`."""
    body = "".join(
        [
            _render_header(report),
            _render_source_files(report),
            _render_methodology(cleaning_cfg),
            _render_stage_funnel(report),
            _render_columns(report),
            _render_missingness(report),
            _render_duplicates(report),
            _render_quality_flags(report, cleaning_cfg),
            _render_fatal_removals(report, cleaning_cfg),
            _render_attribute_recovery(report),
            _render_unmapped_values(report),
            _render_feature_coverage(report),
            _render_derived_summary(report),
            _render_sample_preview(sample_df),
            _render_final_counts(report),
            _render_footer(),
        ]
    )
    path.write_text(_page_shell("InmoAI-lt Cleaning Report", body), encoding="utf-8")


def _page_shell(title: str, body_html: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{html_lib.escape(title)}</title>\n<style>{_STYLE}</style>\n"
        f"</head>\n<body>\n<main>\n{body_html}\n</main>\n</body>\n</html>\n"
    )


def _bar_chart_html(items: dict[str, int], *, max_value: int | None = None, blocking: set[str] | None = None) -> str:
    """Render `items` (label -> count) as CSS-only horizontal bars.

    `blocking` (optional) is a set of labels rendered with the "blocking" bar colour,
    used to visually distinguish blocking quality flags from advisory ones.
    """
    if not items:
        return '<p class="fallback">none recorded</p>'
    blocking = blocking or set()
    computed_max = max_value if max_value is not None else max(items.values())
    computed_max = max(computed_max, 1)
    rows = []
    for label, count in items.items():
        pct = round(min(count, computed_max) / computed_max * 100, 1)
        fill_class = "bar-fill blocking" if label in blocking else "bar-fill"
        rows.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{html_lib.escape(str(label))}</span>'
            f'<div class="bar-track"><div class="{fill_class}" style="width:{pct}%"></div></div>'
            f'<span class="bar-value">{count}</span>'
            "</div>"
        )
    return "".join(rows)


def _render_header(report: CleaningReport) -> str:
    config_hash = report.config_hash or ""
    short_hash = config_hash[:12]
    return (
        "<h1>InmoAI-lt Cleaning Report</h1>"
        '<p class="lede">Methodology and measured results for this cleaning run.</p>'
        f'<p class="meta">reference_date: <code>{html_lib.escape(str(report.reference_date))}</code> '
        f'&middot; config_hash: <code title="{html_lib.escape(config_hash)}">{html_lib.escape(short_hash)}</code></p>'
    )


def _render_source_files(report: CleaningReport) -> str:
    if not report.source_files:
        return '<h2>Source files</h2><p class="fallback">none recorded</p>'
    rows = "".join(
        f"<tr><td>{html_lib.escape(src['file'])}</td><td>{src['rows']}</td>"
        f"<td><code title=\"{html_lib.escape(src['sha256'])}\">{html_lib.escape(src['sha256'][:12])}</code></td></tr>"
        for src in report.source_files
    )
    return (
        "<h2>Source files</h2>"
        f"<table><tr><th>File</th><th>Rows</th><th>SHA-256</th></tr>{rows}</table>"
    )


def _render_methodology(cleaning_cfg: dict[str, Any]) -> str:
    fatal = cleaning_cfg.get("quality", {}).get("fatal", {})
    dedup = cleaning_cfg.get("dedup", {})
    blocking = cleaning_cfg.get("quality", {}).get("blocking_flags", [])
    vilnius_bbox = cleaning_cfg.get("quality", {}).get("vilnius_bbox", {})
    lithuania_bbox = cleaning_cfg.get("quality", {}).get("lithuania_bbox", {})

    paragraphs = [
        ("Load", "Raw source CSVs (enabled entries under <code>input.sources</code>) are "
         "concatenated as-is; the pipeline never mutates raw files on disk."),
        ("Column normalisation", "Column names are normalised, all-null columns are dropped, "
         "redundant/constant columns are collapsed. Nothing here changes row count."),
        ("Attribute recovery", "Values embedded in free-text <code>raw_attributes_json</code> "
         "labels are recovered into structured columns using the controlled Lithuanian&rarr;English "
         "vocabulary in <code>mappings_lt_en.yaml</code>; labels with no vocabulary match are logged "
         "to <code>unmapped_attributes.csv</code> rather than guessed."),
        ("Type &amp; value normalisation", "Numeric/date coercion, categorical mapping, and "
         "multi-value (heating/water) tokenisation into tri-state boolean columns."),
        ("Boolean features", "Feature flags are tri-state: <code>False</code> only when a feature "
         "key was actually captured for that property type; otherwise left NA (never fabricated)."),
        ("Geography", f"Coordinates are flagged (not removed) as outside Vilnius "
         f"(lat {vilnius_bbox.get('lat_min')}&ndash;{vilnius_bbox.get('lat_max')}, "
         f"lon {vilnius_bbox.get('lon_min')}&ndash;{vilnius_bbox.get('lon_max')}) or outside "
         f"Lithuania (lat {lithuania_bbox.get('lat_min')}&ndash;{lithuania_bbox.get('lat_max')}, "
         f"lon {lithuania_bbox.get('lon_min')}&ndash;{lithuania_bbox.get('lon_max')})."),
        ("Duplicates", f"Identity duplicates (exact <code>listing_id</code> repeats) are dropped. "
         f"Content duplicates share a key of {dedup.get('content_key', [])} "
         f"(area rounded to {dedup.get('area_round_dp')} dp); only the non-primary rows are flagged "
         f"(kept: {dedup.get('keep')}), never deleted."),
        ("Quality flags &amp; fatal filter", f"Rows are only <strong>removed</strong> if they fail "
         f"the fatal rule: any of {fatal.get('require_non_null', [])} is null, or "
         f"<code>price_eur</code> &le; {fatal.get('price_eur_min_exclusive')}, or "
         f"<code>total_area_sqm</code> &le; {fatal.get('total_area_sqm_min_exclusive')}. "
         f"Every other quality issue only sets a flag column; flags in {blocking} additionally "
         f"set <code>is_valid=False</code> for the analysis output, without removing the row."),
        ("Derived features", "Reproducible derived columns (building age, floor ratios, etc.) "
         "computed from <code>reference_date</code>, never wall-clock time."),
        ("Output", "Final columns are reordered via a fixed schema (<code>schema.py</code>); "
         "clean CSV (all retained rows) and analysis CSV (valid, non-duplicate rows only) are "
         "both written, plus this report."),
    ]
    items = "".join(f'<p class="methodology"><strong>{name}</strong> &mdash; {text}</p>' for name, text in paragraphs)
    return f"<h2>Methodology</h2>{items}"


def _render_stage_funnel(report: CleaningReport) -> str:
    if not report.stage_row_counts:
        return '<h2>Stage row counts</h2><p class="fallback">none recorded</p>'
    chart_items = {s["stage"]: s["rows_out"] for s in report.stage_row_counts}
    max_value = report.stage_row_counts[0]["rows_in"] if report.stage_row_counts else None
    chart = _bar_chart_html(chart_items, max_value=max_value)
    rows = "".join(
        f"<tr><td>{html_lib.escape(s['stage'])}</td><td>{s['rows_in']}</td>"
        f"<td>{s['rows_out']}</td><td>{s['delta']}</td></tr>"
        for s in report.stage_row_counts
    )
    table = f"<table><tr><th>Stage</th><th>In</th><th>Out</th><th>Delta</th></tr>{rows}</table>"
    return f"<h2>Stage row counts</h2>{chart}{table}"


def _render_columns(report: CleaningReport) -> str:
    if report.dropped_columns:
        dropped_rows = "".join(
            f"<tr><td>{html_lib.escape(d['column'])}</td><td>{html_lib.escape(d['reason'])}</td></tr>"
            for d in report.dropped_columns
        )
        dropped = f"<table><tr><th>Column</th><th>Reason</th></tr>{dropped_rows}</table>"
    else:
        dropped = '<p class="fallback">none recorded</p>'

    if report.renamed_columns:
        renamed_rows = "".join(
            f"<tr><td>{html_lib.escape(k)}</td><td>{html_lib.escape(v)}</td></tr>"
            for k, v in sorted(report.renamed_columns.items())
        )
        renamed = f"<table><tr><th>From</th><th>To</th></tr>{renamed_rows}</table>"
    else:
        renamed = '<p class="fallback">none recorded</p>'

    if report.constant_columns:
        const_rows = "".join(
            f"<tr><td>{html_lib.escape(str(k))}</td><td>{html_lib.escape(str(v))}</td></tr>"
            for k, v in sorted(report.constant_columns.items())
        )
        constants = f"<table><tr><th>Column</th><th>Constant value</th></tr>{const_rows}</table>"
    else:
        constants = '<p class="fallback">none recorded</p>'

    district_note = ""
    if report.district_collapse:
        n = len(report.district_collapse.get("differing_listing_ids", []))
        district_note = f'<p>District collapse: {n} listing(s) with differing district values.</p>'

    return (
        "<h2>Columns</h2>"
        f"<h3>Dropped</h3>{dropped}"
        f"<h3>Renamed</h3>{renamed}"
        f"<h3>Collapsed to constants</h3>{constants}"
        f"{district_note}"
    )


def _render_missingness(report: CleaningReport) -> str:
    if not report.missing_before and not report.missing_after:
        return '<h2>Missingness</h2><p class="fallback">not measured in this run</p>'
    before = _bar_chart_html({k: int(v) for k, v in sorted(report.missing_before.items())})
    after = _bar_chart_html({k: int(v) for k, v in sorted(report.missing_after.items())})
    return f"<h2>Missingness</h2><h3>Before</h3>{before}<h3>After</h3>{after}"


def _render_duplicates(report: CleaningReport) -> str:
    identity_count = report.identity_duplicates.get("count", 0)
    content = report.content_duplicates
    group_count = content.get("group_count", 0)
    dup_row_count = content.get("duplicate_row_count", 0)
    groups = content.get("groups", [])

    groups_html = ""
    if groups:
        shown = groups[:_DUPLICATE_GROUP_PREVIEW_LIMIT]
        rows = "".join(f"<tr><td colspan=\"1\">{html_lib.escape(str(g))}</td></tr>" for g in shown)
        note = ""
        if len(groups) > _DUPLICATE_GROUP_PREVIEW_LIMIT:
            note = f'<p class="meta">showing {_DUPLICATE_GROUP_PREVIEW_LIMIT} of {len(groups)} groups</p>'
        groups_html = f"<table><tr><th>Group</th></tr>{rows}</table>{note}"

    return (
        "<h2>Duplicates</h2>"
        f"<p>Identity duplicates dropped: {identity_count}</p>"
        f"<p>Content duplicate groups: {group_count} ({dup_row_count} non-primary rows flagged)</p>"
        f"{groups_html}"
    )


def _render_quality_flags(report: CleaningReport, cleaning_cfg: dict[str, Any]) -> str:
    if not report.quality_flag_counts:
        return '<h2>Quality flags</h2><p class="fallback">none recorded</p>'
    blocking_names = set(cleaning_cfg.get("quality", {}).get("blocking_flags", []))
    ordered = dict(sorted(report.quality_flag_counts.items(), key=lambda kv: -kv[1]))
    chart = _bar_chart_html(ordered, blocking=blocking_names)
    legend = '<p class="meta">Red bars are blocking flags (set <code>is_valid=False</code>); blue bars are advisory only.</p>'
    return f"<h2>Quality flags</h2>{legend}{chart}"


def _render_fatal_removals(report: CleaningReport, cleaning_cfg: dict[str, Any]) -> str:
    count = report.fatal_removals.get("count", 0)
    removals = report.fatal_removals.get("removals", [])
    if removals:
        rows = "".join(f"<tr><td>{html_lib.escape(str(r))}</td></tr>" for r in removals)
        table = f"<table><tr><th>Removal</th></tr>{rows}</table>"
        return f"<h2>Fatal removals</h2><p>{count} row(s) removed.</p>{table}"
    fatal_cfg = cleaning_cfg.get("quality", {}).get("fatal", {})
    explainer = (
        f"No rows were removed. A row is only removed if any of "
        f"{fatal_cfg.get('require_non_null', [])} is null, or "
        f"<code>price_eur</code> &le; {fatal_cfg.get('price_eur_min_exclusive')}, or "
        f"<code>total_area_sqm</code> &le; {fatal_cfg.get('total_area_sqm_min_exclusive')}."
    )
    return f"<h2>Fatal removals</h2><p>{explainer}</p>"


def _render_attribute_recovery(report: CleaningReport) -> str:
    counts = report.attribute_recovery.get("counts", {})
    if not counts:
        return '<h2>Attribute recovery</h2><p class="fallback">none recorded</p>'
    chart = _bar_chart_html(dict(sorted(counts.items(), key=lambda kv: -kv[1])))
    mismatches = report.attribute_recovery.get("construction_year_mismatches", [])
    mismatch_html = ""
    if mismatches:
        rows = "".join(f"<tr><td>{html_lib.escape(str(m))}</td></tr>" for m in mismatches)
        mismatch_html = f"<h3>Construction year mismatches</h3><table><tr><th>Mismatch</th></tr>{rows}</table>"
    return f"<h2>Attribute recovery</h2>{chart}{mismatch_html}"


def _render_unmapped_values(report: CleaningReport) -> str:
    if report.unmapped_category_values:
        rows = "".join(
            f"<tr><td>{html_lib.escape(col)}</td><td>{html_lib.escape(str(value))}</td><td>{count}</td></tr>"
            for col, values in report.unmapped_category_values.items()
            for value, count in values.items()
        )
        category_html = f"<table><tr><th>Column</th><th>Value</th><th>Count</th></tr>{rows}</table>"
    else:
        category_html = '<p class="fallback">none recorded</p>'

    if report.unmapped_attributes:
        rows = "".join(
            f"<tr><td>{html_lib.escape(label)}</td><td>{info.get('count', '')}</td>"
            f"<td>{html_lib.escape(str(info.get('sample_value', '')))}</td></tr>"
            for label, info in report.unmapped_attributes.items()
        )
        attributes_html = f"<table><tr><th>Label</th><th>Count</th><th>Sample</th></tr>{rows}</table>"
    else:
        attributes_html = '<p class="fallback">none recorded</p>'

    return (
        "<h2>Unmapped values</h2>"
        f"<h3>Unmapped category values</h3>{category_html}"
        f"<h3>Unmapped raw attribute labels</h3>{attributes_html}"
    )


def _render_feature_coverage(report: CleaningReport) -> str:
    if not report.feature_coverage:
        coverage_html = '<p class="fallback">none recorded</p>'
    else:
        all_features: list[str] = []
        for features in report.feature_coverage.values():
            for key in features:
                if key not in all_features:
                    all_features.append(key)
        header = "".join(f"<th>{html_lib.escape(k)}</th>" for k in all_features)
        rows = ""
        for ptype, features in sorted(report.feature_coverage.items()):
            cells = "".join("<td>&check;</td>" if features.get(k) else "<td>&mdash;</td>" for k in all_features)
            rows += f"<tr><td>{html_lib.escape(ptype)}</td>{cells}</tr>"
        coverage_html = f"<table><tr><th>Property type</th>{header}</tr>{rows}</table>"

    geo_chart = _bar_chart_html(dict(sorted(report.geo_flags.items(), key=lambda kv: -kv[1])))
    return f"<h2>Feature coverage</h2>{coverage_html}<h3>Geography flags</h3>{geo_chart}"


def _render_derived_summary(report: CleaningReport) -> str:
    if not report.derived_summary:
        return '<h2>Derived summary</h2><p class="fallback">none recorded</p>'
    items = "".join(
        f"<li>{html_lib.escape(str(k))}: {html_lib.escape(str(v))}</li>"
        for k, v in sorted(report.derived_summary.items())
    )
    return f"<h2>Derived summary</h2><ul>{items}</ul>"


def _render_sample_preview(sample_df: pd.DataFrame) -> str:
    present_cols = [c for c in _SAMPLE_COLUMNS if c in sample_df.columns]
    if not present_cols:
        return '<h2>Sample data preview</h2><p class="fallback">no columns available</p>'
    subset = sample_df[present_cols].head(_SAMPLE_ROW_LIMIT).astype("object")
    subset = subset.where(subset.notna(), "\u2013")
    table_html = subset.to_html(index=False, border=0, classes="sample-table", escape=True)
    return f"<h2>Sample data preview</h2>{table_html}"


def _render_final_counts(report: CleaningReport) -> str:
    if not report.final_counts:
        return '<h2>Final counts</h2><p class="fallback">none recorded</p>'
    cards = "".join(
        f'<div class="stat-card"><div class="n">{v}</div><div class="l">{html_lib.escape(str(k))}</div></div>'
        for k, v in report.final_counts.items()
    )
    return f'<h2>Final counts</h2><div class="stat-grid">{cards}</div>'


def _render_footer() -> str:
    return (
        "<footer>Machine-readable versions of this report are written alongside it as "
        "<code>cleaning_report.json</code> and <code>cleaning_report.md</code>.</footer>"
    )
