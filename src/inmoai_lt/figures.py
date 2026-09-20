"""Plotly figure builders for the analysis report.

Every figure is rendered with an explicit `div_id`. This is not cosmetic: plotly derives
a random UUID for the container when one is not supplied, which makes the output HTML
differ on every run and breaks the pipeline's byte-reproducibility guarantee.

`plotly.js` is embedded once by `analysis_report.py`, so every figure here renders with
`include_plotlyjs=False` -- there is no CDN reference anywhere in the output.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from inmoai_lt.stats import LinearFit, linear_fit

_MARKER_COLOR = "#6a7fdb"
_OUTLIER_COLOR = "#d9534f"
_FIT_COLOR = "#1a1a1a"
_PERCENTILE_COLOR = "#d9534f"
_MEDIAN_COLOR = "#1a1a1a"

# Marked on both distribution plots. p50 is drawn separately, in a heavier style.
_MARKED_PERCENTILES = [5, 25, 75, 95]

_LAYOUT = {
    "template": "plotly_white",
    "height": 420,
    "margin": {"l": 70, "r": 30, "t": 50, "b": 60},
    "font": {"family": 'system-ui, -apple-system, "Segoe UI", Arial, sans-serif', "size": 12},
}


def _finite_pair(x: pd.Series, y: pd.Series) -> pd.DataFrame:
    frame = pd.DataFrame(
        {"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}
    )
    return frame[np.isfinite(frame["x"]) & np.isfinite(frame["y"])]


def _empty_figure(title: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text="not enough data to plot", showarrow=False, font={"size": 14, "color": "#888"}
    )
    figure.update_layout(title=title, xaxis={"visible": False}, yaxis={"visible": False}, **_LAYOUT)
    return figure


def scatter_with_fit(
    df: pd.DataFrame, x_col: str, y_col: str, title: str, x_label: str, y_label: str
) -> tuple[go.Figure, LinearFit | None]:
    """Scatter of `y_col` against `x_col` with an OLS trend line.

    Points outside the p1/p99 band of either axis are drawn in a contrasting colour: they
    stay visible (they are real listings, not errors) but are visually separable from the
    bulk that the fit actually describes.
    """
    frame = _finite_pair(df.get(x_col, pd.Series(dtype=float)), df.get(y_col, pd.Series(dtype=float)))
    if frame.empty:
        return _empty_figure(title), None

    is_outlier = pd.Series(False, index=frame.index)
    for col in ("x", "y"):
        low, high = frame[col].quantile(0.01), frame[col].quantile(0.99)
        is_outlier |= (frame[col] < low) | (frame[col] > high)

    figure = go.Figure()
    for mask, name, color in (
        (~is_outlier, "listings (p1-p99)", _MARKER_COLOR),
        (is_outlier, "outside p1-p99", _OUTLIER_COLOR),
    ):
        subset = frame[mask]
        if subset.empty:
            continue
        figure.add_trace(
            go.Scattergl(
                x=subset["x"],
                y=subset["y"],
                mode="markers",
                name=name,
                marker={"size": 5, "opacity": 0.55, "color": color},
                hovertemplate=f"{x_label}: %{{x:,.1f}}<br>{y_label}: %{{y:,.0f}}<extra></extra>",
            )
        )

    fit = linear_fit(frame["x"], frame["y"])
    if fit is not None:
        line_x = np.array([frame["x"].min(), frame["x"].max()])
        figure.add_trace(
            go.Scatter(
                x=line_x,
                y=fit.predict(line_x),
                mode="lines",
                name=f"OLS fit (R^2={fit.r_squared:.3f})",
                line={"color": _FIT_COLOR, "width": 2, "dash": "dash"},
                hoverinfo="skip",
            )
        )

    figure.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        **_LAYOUT,
    )
    return figure, fit


def distribution(series: pd.Series, title: str, x_label: str) -> go.Figure:
    """Histogram with p5/p25/median/p75/p95 marked directly on the axis.

    The percentile lines are the point of the plot: a bare histogram shows the shape but
    makes you guess where the middle half of the market actually sits.
    """
    values = pd.to_numeric(series, errors="coerce")
    values = values[np.isfinite(values)]
    if values.empty:
        return _empty_figure(title)

    figure = go.Figure(
        go.Histogram(
            x=values,
            nbinsx=60,
            marker={"color": _MARKER_COLOR, "line": {"width": 0}},
            name="listings",
            hovertemplate=f"{x_label}: %{{x}}<br>count: %{{y}}<extra></extra>",
        )
    )

    for percentile in _MARKED_PERCENTILES:
        value = float(values.quantile(percentile / 100))
        figure.add_vline(
            x=value,
            line={"color": _PERCENTILE_COLOR, "width": 1, "dash": "dot"},
            annotation_text=f"p{percentile}",
            annotation_position="top",
            annotation_font_size=10,
        )
    figure.add_vline(
        x=float(values.median()),
        line={"color": _MEDIAN_COLOR, "width": 2},
        annotation_text="median",
        annotation_position="top",
        annotation_font_size=10,
    )

    figure.update_layout(
        title=title, xaxis_title=x_label, yaxis_title="listings", showlegend=False, **_LAYOUT
    )
    return figure


def to_div(figure: go.Figure, div_id: str) -> str:
    """Render `figure` as a standalone div. `div_id` MUST be stable across runs."""
    return figure.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config={"displaylogo": False, "responsive": True},
    )
