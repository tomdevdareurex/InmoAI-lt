"""Distributional measures for the per-segment analysis report.

Pure functions over a segment DataFrame: every one returns plain dicts/DataFrames and
renders nothing, so each measure is testable without touching HTML. Skewness and kurtosis
come from pandas, the OLS fit from `numpy.polyfit`, and Spearman rho from pandas'
`.corr(method="spearman")`, which pulls in scipy under the hood.

Every function tolerates empty or tiny inputs by returning `None`/empty rather than
raising, because the rent segment is genuinely small and must degrade to "not enough
data" instead of crashing the report or emitting a fabricated number.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PERCENTILES: list[int] = [1, 5, 10, 25, 50, 75, 90, 95, 99]

# Below this a fit is arithmetically defined but meaningless; report "not enough data".
_MIN_FIT_N = 3

# Row label for the pooled segment in the `*_comparison` tables.
_ALL_LABEL = "ALL (segment)"


def _clean_numeric(series: pd.Series) -> pd.Series:
    """Finite numeric values only -- inf would silently poison mean/std/percentiles."""
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric[np.isfinite(numeric)]


def percentile_table(series: pd.Series) -> dict[str, float]:
    """p1..p99 of `series`, keyed `"p1"`, `"p5"`, ... Empty input gives an empty dict."""
    values = _clean_numeric(series)
    if values.empty:
        return {}
    return {f"p{p}": float(values.quantile(p / 100)) for p in PERCENTILES}


def robust_summary(series: pd.Series) -> dict[str, float]:
    """Location, spread and shape for one variable.

    Reports median/IQR/MAD alongside mean/std because property prices are right-skewed:
    the mean of a segment with a few 7-figure listings is not a typical price. `skewness`
    and `excess_kurtosis` quantify exactly how misleading the mean is, and
    `outliers_p1_p99` counts how many rows drive it.
    """
    numeric = pd.to_numeric(series, errors="coerce")
    values = _clean_numeric(series)
    n = int(len(values))
    summary: dict[str, float] = {
        "n": n,
        "missing_pct": round(float(numeric.isna().mean() * 100), 2) if len(numeric) else 0.0,
    }
    if n == 0:
        return summary

    q1 = float(values.quantile(0.25))
    q3 = float(values.quantile(0.75))
    median = float(values.median())
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if n > 1 else 0.0
    p1 = float(values.quantile(0.01))
    p99 = float(values.quantile(0.99))

    summary.update(
        {
            "mean": mean,
            "median": median,
            "std": std,
            "min": float(values.min()),
            "max": float(values.max()),
            "iqr": q3 - q1,
            # Median absolute deviation: spread that a handful of extreme listings cannot move.
            "mad": float((values - median).abs().median()),
            "cv": (std / mean) if mean else float("nan"),
            "skewness": float(values.skew()) if n > 2 else float("nan"),
            "excess_kurtosis": float(values.kurt()) if n > 3 else float("nan"),
            "outliers_p1_p99": int(((values < p1) | (values > p99)).sum()),
        }
    )
    return summary


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    r_squared: float
    spearman_rho: float
    n: int

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.slope * x + self.intercept


def linear_fit(x: pd.Series, y: pd.Series) -> LinearFit | None:
    """OLS fit of `y` on `x`, plus Spearman rho. `None` when there is too little data.

    Spearman is reported next to R^2 because these relationships are monotonic but not
    linear: a high rho with a low R^2 means "the relationship is real but curved", which
    is a different conclusion from "there is no relationship".
    """
    frame = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")})
    frame = frame[np.isfinite(frame["x"]) & np.isfinite(frame["y"])]
    if len(frame) < _MIN_FIT_N or frame["x"].nunique() < 2:
        return None

    slope, intercept = np.polyfit(frame["x"], frame["y"], 1)
    predicted = slope * frame["x"] + intercept
    total_ss = float(((frame["y"] - frame["y"].mean()) ** 2).sum())
    residual_ss = float(((frame["y"] - predicted) ** 2).sum())
    r_squared = 1 - residual_ss / total_ss if total_ss else float("nan")
    rho = frame["x"].corr(frame["y"], method="spearman")

    return LinearFit(
        slope=float(slope),
        intercept=float(intercept),
        r_squared=float(r_squared),
        spearman_rho=float(rho) if pd.notna(rho) else float("nan"),
        n=int(len(frame)),
    )


def district_table(df: pd.DataFrame, min_n: int = 10) -> pd.DataFrame:
    """Median EUR/sqm per district, ranked descending, with n and the p25-p75 spread.

    Districts below `min_n` are collapsed into a single "other" row rather than dropped,
    so the row counts still reconcile with the segment total and a thin district cannot
    masquerade as a real price signal.
    """
    if df.empty or "district" not in df.columns or "price_per_sqm_eur" not in df.columns:
        return pd.DataFrame(columns=["district", "n", "median_eur_sqm", "p25", "p75", "iqr"])

    frame = df[["district", "price_per_sqm_eur"]].copy()
    frame["price_per_sqm_eur"] = pd.to_numeric(frame["price_per_sqm_eur"], errors="coerce")
    frame = frame[np.isfinite(frame["price_per_sqm_eur"]) & frame["district"].notna()]
    if frame.empty:
        return pd.DataFrame(columns=["district", "n", "median_eur_sqm", "p25", "p75", "iqr"])

    counts = frame["district"].value_counts()
    frame["district"] = frame["district"].where(
        frame["district"].map(counts) >= min_n, f"other (n<{min_n} per district)"
    )

    grouped = frame.groupby("district")["price_per_sqm_eur"]
    table = pd.DataFrame(
        {
            "n": grouped.size(),
            "median_eur_sqm": grouped.median(),
            "p25": grouped.quantile(0.25),
            "p75": grouped.quantile(0.75),
        }
    )
    table["iqr"] = table["p75"] - table["p25"]
    table = table.reset_index().sort_values(
        ["median_eur_sqm", "district"], ascending=[False, True], kind="mergesort"
    )
    return table.reset_index(drop=True)


def _rows_for_district(df: pd.DataFrame, district: str) -> pd.DataFrame:
    if df.empty or "district" not in df.columns:
        return df.iloc[0:0]
    return df.loc[df["district"] == district]


def _stack(selected: pd.DataFrame, pooled: pd.DataFrame) -> pd.DataFrame:
    """Selected row above the pooled row, dropping empties.

    Empty frames are excluded rather than concatenated: pandas warns that it will stop
    inferring dtypes from all-NA columns, and an empty side here is the normal
    "district did not clear the minimum" case, not an error.
    """
    parts = [frame for frame in (selected, pooled) if not frame.empty]
    if not parts:
        return selected
    return pd.concat(parts, ignore_index=True)


def district_comparison(
    df: pd.DataFrame, district: str, all_label: str = _ALL_LABEL
) -> pd.DataFrame:
    """`district_table` for one district, with the pooled segment beneath it.

    Built by relabelling rather than by a second implementation: the pooled row is
    `district_table` over a frame whose district column has been overwritten with a
    single label, so both rows come from the same tested aggregation.

    `min_n=1` throughout -- the caller has already chosen this district, so collapsing it
    into an "other" row would defeat the point.
    """
    selected = district_table(_rows_for_district(df, district), min_n=1)
    pooled = district_table(df.assign(district=all_label), min_n=1)
    return _stack(selected, pooled)


def cross_cuts(df: pd.DataFrame, min_n: int = 5) -> dict[str, pd.DataFrame]:
    """Median EUR/sqm by rooms, construction decade, and condition.

    These are the three dimensions that move price per square metre independently of
    location, so they separate "this district is expensive" from "this district is full
    of new-build studios".
    """
    result: dict[str, pd.DataFrame] = {}
    if df.empty or "price_per_sqm_eur" not in df.columns:
        return result

    frame = df.copy()
    frame["price_per_sqm_eur"] = pd.to_numeric(frame["price_per_sqm_eur"], errors="coerce")
    frame = frame[np.isfinite(frame["price_per_sqm_eur"])]
    if frame.empty:
        return result

    if "construction_year" in frame.columns:
        year = pd.to_numeric(frame["construction_year"], errors="coerce")
        frame["construction_decade"] = (year // 10 * 10).astype("Int64").astype("string") + "s"

    if "rooms" in frame.columns:
        frame["rooms"] = pd.to_numeric(frame["rooms"], errors="coerce").astype("Int64")

    for key, label in (("rooms", "rooms"), ("construction_decade", "construction decade"), ("condition", "condition")):
        if key not in frame.columns:
            continue
        subset = frame[frame[key].notna()]
        if subset.empty:
            continue
        grouped = subset.groupby(key, observed=True)["price_per_sqm_eur"]
        table = pd.DataFrame({"n": grouped.size(), "median_eur_sqm": grouped.median()})
        table = table[table["n"] >= min_n].reset_index()
        if table.empty:
            continue
        table.columns = [label, "n", "median_eur_sqm"]
        result[label] = table

    return result


def gross_rental_yield(
    sale_df: pd.DataFrame, rent_df: pd.DataFrame, min_n: int = 5
) -> pd.DataFrame:
    """Gross yield per district: (median monthly rent x 12) / median sale price.

    Gross, not net -- it ignores vacancy, tax, management and maintenance, so treat it as
    a relative ranking between districts rather than an achievable return. Emitted only
    for districts clearing `min_n` on BOTH sides, since a yield built on two rent
    listings is noise dressed up as a number.
    """
    empty = pd.DataFrame(
        columns=["district", "n_sale", "n_rent", "median_sale_eur", "median_rent_eur", "gross_yield_pct"]
    )
    required = {"district", "price_eur"}
    if sale_df.empty or rent_df.empty or not required.issubset(sale_df.columns) or not required.issubset(rent_df.columns):
        return empty

    def _medians(df: pd.DataFrame, suffix: str) -> pd.DataFrame:
        frame = df[["district", "price_eur"]].copy()
        frame["price_eur"] = pd.to_numeric(frame["price_eur"], errors="coerce")
        frame = frame[np.isfinite(frame["price_eur"]) & frame["district"].notna()]
        grouped = frame.groupby("district")["price_eur"]
        return pd.DataFrame({f"n_{suffix}": grouped.size(), f"median_{suffix}_eur": grouped.median()})

    joined = _medians(sale_df, "sale").join(_medians(rent_df, "rent"), how="inner")
    joined = joined[(joined["n_sale"] >= min_n) & (joined["n_rent"] >= min_n)]
    if joined.empty:
        return empty

    # A non-positive sale median would make the quotient inf, which sorts to the top of
    # the table and renders as a literal. Reachable now that one listing can set a median.
    denominator = joined["median_sale_eur"].where(joined["median_sale_eur"] > 0)
    joined["gross_yield_pct"] = joined["median_rent_eur"] * 12 / denominator * 100
    joined = joined.reset_index().sort_values(
        ["gross_yield_pct", "district"], ascending=[False, True], kind="mergesort"
    )
    return joined[empty.columns].reset_index(drop=True)


SIZE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("20_50", 20.0, 50.0),
    ("50_80", 50.0, 80.0),
    ("80_120", 80.0, 120.0),
)


def _in_band(df: pd.DataFrame, lo: float, hi: float) -> pd.DataFrame:
    """Rows whose floor area falls in `[lo, hi)`.

    Half-open so a listing sitting exactly on a boundary is counted once. The bands do
    not partition the data: anything under the first `lo` or over the last `hi` appears
    only in the all-sizes column.
    """
    if df.empty or "total_area_sqm" not in df.columns:
        return df.iloc[0:0]
    area = pd.to_numeric(df["total_area_sqm"], errors="coerce")
    return df.loc[np.isfinite(area) & (area >= lo) & (area < hi)]


def yield_by_size_band(
    sale_df: pd.DataFrame,
    rent_df: pd.DataFrame,
    bands: tuple[tuple[str, float, float], ...] = SIZE_BANDS,
) -> pd.DataFrame:
    """`gross_rental_yield` per district, plus one yield per size band beside it.

    No minimum listing count is applied anywhere: a band holding a single rent listing
    reports its yield, and the `n_sale_*` / `n_rent_*` columns tell the reader how much
    to trust it. Band columns always exist, so the table's shape does not vary with the
    data; a district with no listings in a band gets zero counts and a NaN yield.
    """
    frame = gross_rental_yield(sale_df, rent_df, min_n=1).set_index("district")
    for name, lo, hi in bands:
        band = gross_rental_yield(
            _in_band(sale_df, lo, hi), _in_band(rent_df, lo, hi), min_n=1
        )
        columns = ["n_sale", "n_rent", "gross_yield_pct"]
        frame = frame.join(band.set_index("district")[columns].add_suffix(f"_{name}"), how="left")
        for count in ("n_sale", "n_rent"):
            frame[f"{count}_{name}"] = (
                pd.to_numeric(frame[f"{count}_{name}"], errors="coerce").fillna(0).astype("int64")
            )
        frame[f"gross_yield_pct_{name}"] = pd.to_numeric(
            frame[f"gross_yield_pct_{name}"], errors="coerce"
        )
    return frame.reset_index()


def _pooled_bands(
    sale_df: pd.DataFrame,
    rent_df: pd.DataFrame,
    all_label: str,
    bands: tuple[tuple[str, float, float], ...],
) -> pd.DataFrame:
    """The whole segment as a single district, so the pooled row shares one code path.

    The pooled yield is `median(all rents) x 12 / median(all sales)` -- the market-wide
    figure, not the mean of the per-district yields. Those two differ whenever districts
    carry unequal listing counts.
    """
    return yield_by_size_band(
        sale_df.assign(district=all_label), rent_df.assign(district=all_label), bands=bands
    )


def yield_with_market_row(
    sale_df: pd.DataFrame,
    rent_df: pd.DataFrame,
    all_label: str = _ALL_LABEL,
    bands: tuple[tuple[str, float, float], ...] = SIZE_BANDS,
) -> pd.DataFrame:
    """Every district, ranked by all-sizes yield, with the pooled market row beneath."""
    return _stack(
        yield_by_size_band(sale_df, rent_df, bands=bands),
        _pooled_bands(sale_df, rent_df, all_label, bands),
    )


def yield_comparison(
    sale_df: pd.DataFrame,
    rent_df: pd.DataFrame,
    district: str,
    all_label: str = _ALL_LABEL,
    bands: tuple[tuple[str, float, float], ...] = SIZE_BANDS,
) -> pd.DataFrame:
    """`yield_by_size_band` for one district, with the pooled market beneath it."""
    return _stack(
        yield_by_size_band(
            _rows_for_district(sale_df, district),
            _rows_for_district(rent_df, district),
            bands=bands,
        ),
        _pooled_bands(sale_df, rent_df, all_label, bands),
    )
