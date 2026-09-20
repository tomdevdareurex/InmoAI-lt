"""Self-contained per-segment distributional analysis, written as `analysis_report.html`.

Separate from `cleaning_report.html` on purpose: that one documents what the pipeline did
to the data, this one documents what the data says. Keeping them apart also keeps the
4.8 MB embedded `plotly.js` out of the cleaning report.

Each segment (`apartment_sale`, `house_sale`, `apartment_rent`, ...) gets four figures --
two scatters and two distributions -- plus percentile, spread and cross-cut tables.
Everything is inlined; there are no network references.
"""

from __future__ import annotations

import html as html_lib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.offline as plotly_offline

from inmoai_lt import district_filter, figures, stats
from inmoai_lt.stats import LinearFit

# Below this a segment gets its figures but not its district table or cross-cuts: those
# slice an already-small sample into groups where the median is not a stable statistic.
_MIN_SEGMENT_N = 100
_MIN_DISTRICT_N = 10

# Applied only to a district-filtered view. `_MIN_SEGMENT_N` stays a judgement about the
# segment as a whole -- if the full segment cannot support subgroup medians then no slice
# of it can either -- so these govern what a filtered slice additionally gives up.
_MIN_FILTERED_N = 30
_MIN_FILTERED_CROSS_CUT_N = 10

# Figure order within a segment. Fixed here because it is also the payload key order.
_PLOT_KEYS = ("scatter_price_area", "scatter_ppsqm_area", "dist_price", "dist_ppsqm")

_PRICE_LABELS = {
    "sale": ("Price (EUR)", "Price per sqm (EUR)"),
    "rent": ("Monthly rent (EUR)", "Monthly rent per sqm (EUR)"),
}

_STYLE = """
body { font-family: -apple-system, "Segoe UI", Arial, sans-serif; margin: 0; padding: 0;
       background: #f7f7f9; color: #1a1a1a; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 32px 64px; }
h1 { font-size: 1.6rem; margin-bottom: 4px; }
h2 { font-size: 1.3rem; margin-top: 48px; border-bottom: 2px solid #ddd; padding-bottom: 6px; }
h3 { font-size: 1rem; margin-top: 24px; }
p.lede { color: #555; margin-top: 0; }
p.meta { color: #777; font-size: 0.85rem; }
p.note { color: #333; background: #fff; border-left: 3px solid #6a7fdb; padding: 8px 12px;
         margin: 8px 0; }
p.warn { color: #7a3b39; background: #fdf1f0; border-left: 3px solid #d9534f;
         padding: 8px 12px; margin: 8px 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 0.86rem;
        background: #fff; }
th, td { text-align: right; padding: 4px 8px; border-bottom: 1px solid #e3e3e3; }
th:first-child, td:first-child { text-align: left; }
th { background: #eef0f7; }
.fallback { color: #888; font-style: italic; }
.stat-grid { display: flex; gap: 16px; flex-wrap: wrap; margin: 12px 0; }
.stat-card { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 10px 16px;
             min-width: 130px; }
.stat-card .n { font-size: 1.3rem; font-weight: 600; }
.stat-card .l { color: #777; font-size: 0.8rem; }
.figure { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 8px;
          margin: 12px 0; }
.filter-bar { position: sticky; top: 0; z-index: 5; display: flex; align-items: center;
              gap: 10px; flex-wrap: wrap; background: #fff; border: 1px solid #ddd;
              border-radius: 6px; padding: 10px 14px; margin: 16px 0; }
.filter-bar label { font-weight: 600; font-size: 0.9rem; }
.filter-bar select { font: inherit; padding: 5px 8px; border: 1px solid #bbb;
                     border-radius: 4px; background: #fff; min-width: 240px; }
.filter-hint { color: #777; font-size: 0.8rem; }
footer { color: #999; font-size: 0.8rem; margin-top: 48px; }
"""


def write_analysis_report(
    analysis_df: pd.DataFrame,
    reference_date: pd.Timestamp,
    config_hash: str,
    path: Path,
) -> None:
    """Render the per-segment analysis of `analysis_df` to a self-contained HTML file.

    The page is written in its unfiltered form, exactly as it renders without the filter.
    The district views are appended as data alongside it, so the default view needs no
    JavaScript to paint and the filter is purely additive.
    """
    segments = _split_segments(analysis_df)
    districts = district_filter.eligible_districts(segments, min_n=_MIN_DISTRICT_N)

    control, payload = "", ""
    if districts:
        totals = district_filter.district_totals(segments, districts)
        control = district_filter.render_control(districts, totals, len(analysis_df))
        payload = district_filter.render_payload(
            _build_views(segments, districts), district_filter.shared_template()
        ) + district_filter.render_script()

    body = "".join(
        [
            _render_header(reference_date, config_hash, segments),
            control,
            _render_methodology(),
            "".join(_render_segment(name, frame) for name, frame in segments.items()),
            _render_yield(segments),
            payload,
            _render_footer(),
        ]
    )
    path.write_text(_page_shell("InmoAI-lt Analysis Report", body), encoding="utf-8")


def _district_rows(frame: pd.DataFrame, district: str | None) -> pd.DataFrame:
    """Rows for one district, or the whole frame when unfiltered."""
    if district is None:
        return frame
    if frame.empty or "district" not in frame.columns:
        return frame.iloc[0:0]
    return frame.loc[frame["district"] == district]


def _build_views(
    segments: dict[str, pd.DataFrame], districts: list[str]
) -> dict[str, object]:
    """Every selectable view, precomputed.

    `ALL_KEY` is included even though it is what the page already shows statically, so
    that switching back to it goes through the same code path as switching away.
    """
    labels = {
        name: _segment_labels(frame) for name, frame in segments.items() if not frame.empty
    }
    views: dict[str, object] = {}
    for key in [district_filter.ALL_KEY, *districts]:
        district = None if key == district_filter.ALL_KEY else key
        views[key] = {
            "cards": _render_cards(
                {
                    name: len(_district_rows(frame, district))
                    for name, frame in segments.items()
                }
            ),
            "yield_html": _render_yield_body(segments, district),
            "segments": {
                name: _build_segment_view(segments[name], labels[name], district)
                for name in labels
            },
        }
    return views


def _build_segment_view(
    segment_frame: pd.DataFrame, labels: _SegmentLabels, district: str | None
) -> dict[str, object]:
    frame = _district_rows(segment_frame, district)
    built, price_fit, ppsqm_fit = _segment_figures(frame, labels)
    tables = (
        ""
        if frame.empty
        else _render_segment_tables(
            frame, segment_frame, labels, price_fit, ppsqm_fit, district
        )
    )
    return {
        "rows": len(frame),
        "banner": _render_banner(len(frame), len(segment_frame), district),
        "tables": tables,
        "figures": {key: district_filter.figure_spec(built[key]) for key in _PLOT_KEYS},
    }


def _split_segments(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Segment name -> rows, sorted so the report is deterministic."""
    if df.empty or "segment" not in df.columns:
        return {}
    return {
        str(name): df.loc[df["segment"] == name].reset_index(drop=True)
        for name in sorted(df["segment"].dropna().unique())
    }


def _page_shell(title: str, body_html: str) -> str:
    # plotly.js is embedded once here rather than per figure; every figure div then
    # renders with include_plotlyjs=False. No CDN, no network access required.
    plotly_js = plotly_offline.get_plotlyjs()
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html_lib.escape(title)}</title>\n<style>{_STYLE}</style>\n"
        f"<script>{plotly_js}</script>\n"
        f"</head>\n<body>\n<main>\n{body_html}\n</main>\n</body>\n</html>\n"
    )


def _fmt(value: object, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "&ndash;"
    if isinstance(value, (int, float)):
        return f"{value:,.{decimals}f}"
    return html_lib.escape(str(value))


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<p class="fallback">not enough data</p>'
    head = "".join(f"<th>{html_lib.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _is_count_column(name: object) -> bool:
    """`n`, `n_sale`, `n_rent`, ... are listing counts and must render without decimals."""
    return str(name) == "n" or str(name).startswith("n_")


def _frame_table(df: pd.DataFrame, decimals: int = 1) -> str:
    if df.empty:
        return '<p class="fallback">not enough data</p>'
    rows = [
        [_fmt(v, 0 if _is_count_column(c) else decimals) for c, v in zip(df.columns, row)]
        for row in df.itertuples(index=False)
    ]
    return _table([str(c) for c in df.columns], rows)


def _render_cards(counts: dict[str, int]) -> str:
    return "".join(
        f'<div class="stat-card"><div class="n">{count:,}</div>'
        f'<div class="l">{html_lib.escape(name)}</div></div>'
        for name, count in counts.items()
    )


def _render_header(
    reference_date: pd.Timestamp, config_hash: str, segments: dict[str, pd.DataFrame]
) -> str:
    cards = _render_cards({name: len(frame) for name, frame in segments.items()})
    return (
        "<h1>InmoAI-lt Analysis Report</h1>"
        '<p class="lede">Price and area distributions per market segment '
        "(listing type &times; property type).</p>"
        f'<p class="meta">reference_date: <code>{html_lib.escape(str(reference_date))}</code> '
        f'&middot; config_hash: <code>{html_lib.escape(config_hash[:12])}</code></p>'
        f'<div class="stat-grid" id="stat-cards">{cards}</div>'
    )


def _render_methodology() -> str:
    return (
        "<h2>How to read this</h2>"
        '<p class="note"><strong>Segments are never pooled.</strong> Rent is priced in '
        "EUR/month and sale in EUR, so a combined distribution would be meaningless. Each "
        "segment below is analysed only against itself.</p>"
        '<p class="note"><strong>Rows are the analysis subset</strong> &mdash; valid, '
        "non-duplicate listings only. Rows carrying a blocking quality flag are excluded "
        "upstream, so the distributions here are not skewed by known-bad records.</p>"
        '<p class="note"><strong>Median over mean.</strong> Property prices are '
        "right-skewed, so the median and the p25&ndash;p75 band describe the typical market "
        "better than the mean. The skewness and excess kurtosis figures quantify how far "
        "apart those two answers are.</p>"
        '<p class="note"><strong>The price-per-sqm slope is the headline number.</strong> '
        "On the second scatter of each segment, a negative slope is the size discount: how "
        "many euros per square metre the unit price falls for each extra square metre of "
        "floor area. R&sup2; says how much of the variation that explains; Spearman rho "
        "says whether the relationship is monotonic even where it is not straight.</p>"
    )


@dataclass(frozen=True)
class _SegmentLabels:
    """Axis and row labels for one segment. Fixed by listing type, not by any filter."""

    price: str
    ppsqm: str
    area: str = "Total area (sqm)"


def _segment_labels(frame: pd.DataFrame) -> _SegmentLabels:
    listing_type = str(frame["listing_type"].iloc[0]) if "listing_type" in frame.columns else "sale"
    price_label, ppsqm_label = _PRICE_LABELS.get(listing_type, _PRICE_LABELS["sale"])
    return _SegmentLabels(price=price_label, ppsqm=ppsqm_label)


def _segment_figures(
    frame: pd.DataFrame, labels: _SegmentLabels
) -> tuple[dict[str, go.Figure], LinearFit | None, LinearFit | None]:
    """The four figures for a frame, keyed by `_PLOT_KEYS`, plus both fits.

    An empty frame is not special-cased: `scatter_with_fit` and `distribution` already
    degrade to a "not enough data to plot" placeholder, which keeps one code path for
    districts that are absent from a segment.
    """
    price_scatter, price_fit = figures.scatter_with_fit(
        frame, "total_area_sqm", "price_eur",
        f"{labels.price} vs area", labels.area, labels.price,
    )
    ppsqm_scatter, ppsqm_fit = figures.scatter_with_fit(
        frame, "total_area_sqm", "price_per_sqm_eur",
        f"{labels.ppsqm} vs area", labels.area, labels.ppsqm,
    )
    built = {
        "scatter_price_area": price_scatter,
        "scatter_ppsqm_area": ppsqm_scatter,
        "dist_price": figures.distribution(
            frame.get("price_eur", pd.Series(dtype=float)),
            f"{labels.price} distribution", labels.price,
        ),
        "dist_ppsqm": figures.distribution(
            frame.get("price_per_sqm_eur", pd.Series(dtype=float)),
            f"{labels.ppsqm} distribution", labels.ppsqm,
        ),
    }
    return built, price_fit, ppsqm_fit


def _render_banner(n: int, segment_n: int, district: str | None) -> str:
    """The caveat above a segment's figures, if it needs one."""
    if district is None:
        if segment_n >= _MIN_SEGMENT_N:
            return ""
        return (
            f'<p class="warn"><strong>Small sample: {n} listings.</strong> The figures below '
            "are shown for completeness, but percentiles and any fitted slope are unstable at "
            "this size. District and cross-cut breakdowns are suppressed rather than shown as "
            "if they were reliable.</p>"
        )

    name = html_lib.escape(district)
    if n == 0:
        return f'<p class="warn"><strong>No listings in this segment for {name}.</strong></p>'

    extra = (
        f" Cross-cut breakdowns are suppressed below {_MIN_FILTERED_N} listings."
        if n < _MIN_FILTERED_N
        else ""
    )
    return (
        f'<p class="warn"><strong>Filtered to {name}: {n} of {segment_n:,} listings in this '
        "segment.</strong> Percentiles and fitted slopes from a slice this size are "
        f"indicative, not market rates.{extra}</p>"
    )


def _render_segment_tables(
    frame: pd.DataFrame,
    segment_frame: pd.DataFrame,
    labels: _SegmentLabels,
    price_fit: LinearFit | None,
    ppsqm_fit: LinearFit | None,
    district: str | None,
) -> str:
    return "".join(
        [
            _render_fits(price_fit, ppsqm_fit, labels.ppsqm),
            _render_percentiles(frame, labels),
            _render_spread(frame, labels),
            _render_breakdowns(frame, segment_frame, district),
        ]
    )


def _render_segment(name: str, frame: pd.DataFrame) -> str:
    """The unfiltered rendering of one segment.

    The banner and tables sit in addressable wrappers because the district filter swaps
    their contents; the figure divs keep their existing `{segment}_{key}` ids and are
    re-rendered in place.
    """
    heading = f'<h2>{html_lib.escape(name.replace("_", " / "))}</h2>'
    if frame.empty:
        return heading + '<p class="fallback">no rows in this segment</p>'

    labels = _segment_labels(frame)
    built, price_fit, ppsqm_fit = _segment_figures(frame, labels)
    plots = "".join(
        f'<div class="figure">{figures.to_div(built[key], f"{name}_{key}")}</div>'
        for key in _PLOT_KEYS
    )

    return "".join(
        [
            heading,
            f'<div id="banner-{name}">{_render_banner(len(frame), len(frame), None)}</div>',
            plots,
            f'<div id="tables-{name}">',
            _render_segment_tables(frame, frame, labels, price_fit, ppsqm_fit, None),
            "</div>",
        ]
    )


def _render_fits(price_fit, ppsqm_fit, ppsqm_label: str) -> str:
    rows = []
    for label, fit in (("price vs area", price_fit), (f"{ppsqm_label} vs area", ppsqm_fit)):
        if fit is None:
            rows.append([html_lib.escape(label), "&ndash;", "&ndash;", "&ndash;", "&ndash;", "0"])
            continue
        rows.append(
            [
                html_lib.escape(label),
                _fmt(fit.slope, 2),
                _fmt(fit.intercept, 2),
                _fmt(fit.r_squared, 3),
                _fmt(fit.spearman_rho, 3),
                _fmt(fit.n, 0),
            ]
        )
    table = _table(["Relationship", "Slope", "Intercept", "R&sup2;", "Spearman rho", "n"], rows)

    reading = ""
    if ppsqm_fit is not None:
        direction = "falls" if ppsqm_fit.slope < 0 else "rises"
        reading = (
            f'<p class="note">Each additional square metre of floor area is associated with '
            f"a unit price that {direction} by "
            f"<strong>{abs(ppsqm_fit.slope):,.2f}</strong> EUR/sqm "
            f"(R&sup2; {ppsqm_fit.r_squared:.3f}, Spearman rho {ppsqm_fit.spearman_rho:.3f}, "
            f"n={ppsqm_fit.n:,}).</p>"
        )
    return f"<h3>Fitted relationships</h3>{table}{reading}"


def _variable_columns(labels: _SegmentLabels) -> tuple[tuple[str, str], ...]:
    return (
        (labels.price, "price_eur"),
        (labels.ppsqm, "price_per_sqm_eur"),
        (labels.area, "total_area_sqm"),
    )


def _render_percentiles(frame: pd.DataFrame, labels: _SegmentLabels) -> str:
    rows = []
    for label, col in _variable_columns(labels):
        table = stats.percentile_table(frame.get(col, pd.Series(dtype=float)))
        if not table:
            continue
        rows.append([html_lib.escape(label)] + [_fmt(table[f"p{p}"], 1) for p in stats.PERCENTILES])
    headers = ["Variable"] + [f"p{p}" for p in stats.PERCENTILES]
    return f"<h3>Percentiles</h3>{_table(headers, rows)}"


def _render_spread(frame: pd.DataFrame, labels: _SegmentLabels) -> str:
    keys = [
        ("n", 0), ("missing_pct", 2), ("mean", 1), ("median", 1), ("std", 1),
        ("iqr", 1), ("mad", 1), ("cv", 3), ("skewness", 3), ("excess_kurtosis", 3),
        ("outliers_p1_p99", 0),
    ]
    rows = []
    for label, col in _variable_columns(labels):
        summary = stats.robust_summary(frame.get(col, pd.Series(dtype=float)))
        if not summary:
            continue
        rows.append([html_lib.escape(label)] + [_fmt(summary.get(k), d) for k, d in keys])
    headers = ["Variable", "n", "missing %", "mean", "median", "std", "IQR", "MAD", "CV",
               "skew", "ex. kurtosis", "outliers p1/p99"]
    return f"<h3>Spread and shape</h3>{_table(headers, rows)}"


def _render_breakdowns(
    frame: pd.DataFrame, segment_frame: pd.DataFrame, district: str | None = None
) -> str:
    """District ranking and cross-cuts, or their filtered equivalents.

    The `_MIN_SEGMENT_N` gate is deliberately measured on the whole segment rather than
    on `frame`: it expresses "this segment is too small to slice at all", which does not
    stop being true because the user narrowed it further.
    """
    segment_n = len(segment_frame)
    if segment_n < _MIN_SEGMENT_N:
        return (
            "<h3>District and cross-cut breakdowns</h3>"
            f'<p class="fallback">suppressed: segment has {segment_n} listings, below the '
            f"{_MIN_SEGMENT_N}-row minimum for subgroup medians</p>"
        )

    if district is None:
        ranking = _frame_table(stats.district_table(frame, min_n=_MIN_DISTRICT_N))
        cuts = stats.cross_cuts(frame)
        heading = "Median price per sqm by district"
    else:
        # The comparison needs the whole segment: one row for the district, one pooled.
        ranking = _frame_table(stats.district_comparison(segment_frame, district))
        heading = "Median price per sqm, selected district vs segment"
        if len(frame) < _MIN_FILTERED_N:
            return (
                f"<h3>{heading}</h3>{ranking}<h3>Cross-cut breakdowns</h3>"
                f'<p class="fallback">suppressed: {len(frame)} listings in this district, '
                f"below the {_MIN_FILTERED_N}-row minimum for subgroup medians</p>"
            )
        cuts = stats.cross_cuts(frame, min_n=_MIN_FILTERED_CROSS_CUT_N)

    rendered = "".join(
        f"<h3>Median price per sqm by {html_lib.escape(label)}</h3>{_frame_table(table)}"
        for label, table in cuts.items()
    )
    return f"<h3>{heading}</h3>{ranking}{rendered}"


def _render_yield(segments: dict[str, pd.DataFrame], district: str | None = None) -> str:
    """Yield per property type, never across.

    An apartment's rent must be divided by an apartment's sale price. Pooling houses and
    apartments into one district median would divide one product's rent by another
    product's price, which is not a yield at all.
    """
    heading = "<h2>Gross rental yield by district</h2>"
    explainer = (
        '<p class="note">(median monthly rent &times; 12) / median sale price, per district '
        "and <strong>within a single property type</strong> &mdash; a house&rsquo;s rent is "
        "never divided by an apartment&rsquo;s price. This is a <strong>gross</strong> "
        "figure: it ignores vacancy, tax, management and maintenance, so read it as a "
        "relative ranking between districts rather than an achievable return. Every yield "
        "is followed by <strong>(sale listings / rent listings)</strong>: no minimum is "
        "applied, so a figure resting on a single listing is shown rather than hidden, and "
        "the counts are what tell you whether to trust it. The size bands are "
        "<strong>half-open</strong> &mdash; a 50 sqm flat falls in 50&ndash;80 &mdash; and "
        "flats under 20 or over 120 sqm appear only in the all-sizes column.</p>"
    )
    body = _render_yield_body(segments, district)
    return f'{heading}{explainer}<div id="yield-body">{body}</div>'


def _yield_sides(segments: dict[str, pd.DataFrame]) -> dict[str, dict[str, pd.DataFrame]]:
    sides: dict[str, dict[str, pd.DataFrame]] = {}
    for name, frame in segments.items():
        property_type, _, listing_type = name.rpartition("_")
        if property_type and listing_type in ("sale", "rent"):
            sides.setdefault(property_type, {})[listing_type] = frame
    return sides


def _yield_cell(yield_pct: object, n_sale: object, n_rent: object) -> str:
    figure = "\u2013" if pd.isna(yield_pct) else f"{float(yield_pct):.2f}"
    return f"{figure} ({int(n_sale)}/{int(n_rent)})"


def _render_yield_table(frame: pd.DataFrame) -> str:
    """Collapse each (yield, n_sale, n_rent) triple into one `5.47 (198/7)` cell.

    Done here rather than in `stats` so the ranking happens on numbers, and so the values
    that reach the embedded payload are already escaped HTML strings rather than floats
    that `allow_nan=False` would reject.
    """
    display = frame[["district", "median_sale_eur", "median_rent_eur"]].copy()
    for suffix, label in [("", "all sizes")] + [
        (f"_{name}", f"{name.replace('_', '\u2013')} sqm") for name, _, _ in stats.SIZE_BANDS
    ]:
        display[f"yield % {label}"] = [
            _yield_cell(*values)
            for values in zip(
                frame[f"gross_yield_pct{suffix}"],
                frame[f"n_sale{suffix}"],
                frame[f"n_rent{suffix}"],
            )
        ]
    return _frame_table(display, decimals=0)


def _render_yield_body(
    segments: dict[str, pd.DataFrame], district: str | None = None
) -> str:
    """The per-property-type yield blocks, without the heading and explainer.

    Split out because the district filter replaces this and leaves the surrounding prose
    in place.
    """
    sides = _yield_sides(segments)
    if not sides:
        return '<p class="fallback">no priced segments</p>'

    blocks = []
    for property_type in sorted(sides):
        sub = f'<h3>{html_lib.escape(property_type.replace("_", " "))}</h3>'
        sale, rent = sides[property_type].get("sale"), sides[property_type].get("rent")
        if sale is None or rent is None:
            missing = "sale" if sale is None else "rent"
            blocks.append(
                sub + f'<p class="fallback">no {missing} listings for this property type, '
                "so no yield can be computed</p>"
            )
            continue
        table = (
            stats.yield_with_market_row(sale, rent)
            if district is None
            else stats.yield_comparison(sale, rent, district)
        )
        if table.empty:
            blocks.append(
                sub + '<p class="fallback">no district has listings on both the sale '
                "and the rent side, so no yield can be computed</p>"
            )
            continue
        blocks.append(sub + _render_yield_table(table))
    return "".join(blocks)


def _render_footer() -> str:
    return (
        "<footer>Generated by the InmoAI-lt cleaning pipeline alongside "
        "<code>cleaning_report.html</code>. Per-segment source data is written to "
        "<code>data/processed/segments/</code>.</footer>"
    )
