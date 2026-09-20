"""Unit tests for the analysis measures.

Every expected value here is hand-computed from a small series rather than compared
against another pandas call, so the tests would catch a wrong-but-plausible formula
(population vs sample std, quartile interpolation, kurtosis convention).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from inmoai_lt.stats import (
    cross_cuts,
    district_comparison,
    district_table,
    gross_rental_yield,
    linear_fit,
    percentile_table,
    robust_summary,
    yield_by_size_band,
    yield_comparison,
    yield_with_market_row,
)

_ALL = "ALL (segment)"


class TestPercentileTable:
    def test_median_of_one_to_hundred(self):
        table = percentile_table(pd.Series(range(1, 101)))
        assert table["p50"] == 50.5
        assert table["p25"] == 25.75
        assert table["p75"] == 75.25

    def test_empty_series_gives_empty_dict(self):
        assert percentile_table(pd.Series(dtype=float)) == {}

    def test_non_numeric_values_are_ignored(self):
        table = percentile_table(pd.Series(["10", "20", "30", "not a number"]))
        assert table["p50"] == 20.0


class TestRobustSummary:
    def test_hand_computed_location_and_spread(self):
        # 1..9: mean 5, median 5, q1 3, q3 7, so IQR 4 and MAD 2.
        summary = robust_summary(pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9]))
        assert summary["n"] == 9
        assert summary["mean"] == 5.0
        assert summary["median"] == 5.0
        assert summary["iqr"] == 4.0
        assert summary["mad"] == 2.0
        # Sample std (ddof=1) of 1..9 is sqrt(60/8) = 2.7386...; population std is 2.582.
        assert abs(summary["std"] - np.sqrt(7.5)) < 1e-9
        assert abs(summary["cv"] - np.sqrt(7.5) / 5.0) < 1e-9

    def test_missing_pct_counts_non_numeric_as_missing(self):
        summary = robust_summary(pd.Series([1.0, 2.0, None, None]))
        assert summary["n"] == 2
        assert summary["missing_pct"] == 50.0

    def test_infinities_do_not_poison_the_mean(self):
        summary = robust_summary(pd.Series([1.0, 2.0, 3.0, np.inf]))
        assert summary["n"] == 3
        assert summary["mean"] == 2.0
        assert summary["max"] == 3.0

    def test_right_skew_is_positive(self):
        summary = robust_summary(pd.Series([1, 1, 1, 1, 2, 2, 3, 50]))
        assert summary["skewness"] > 0
        assert summary["median"] < summary["mean"]

    def test_empty_series_reports_zero_n_without_raising(self):
        summary = robust_summary(pd.Series(dtype=float))
        assert summary["n"] == 0
        assert "mean" not in summary


class TestLinearFit:
    def test_recovers_a_known_slope_exactly(self):
        x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        fit = linear_fit(x, 3 * x + 7)
        assert fit is not None
        assert abs(fit.slope - 3.0) < 1e-9
        assert abs(fit.intercept - 7.0) < 1e-9
        assert abs(fit.r_squared - 1.0) < 1e-9
        assert abs(fit.spearman_rho - 1.0) < 1e-9
        assert fit.n == 5

    def test_returns_none_below_three_points(self):
        assert linear_fit(pd.Series([1.0, 2.0]), pd.Series([2.0, 4.0])) is None

    def test_returns_none_when_x_has_no_variation(self):
        assert linear_fit(pd.Series([2.0, 2.0, 2.0]), pd.Series([1.0, 5.0, 9.0])) is None

    def test_ignores_rows_where_either_axis_is_missing(self):
        x = pd.Series([1.0, 2.0, 3.0, 4.0, np.nan])
        y = pd.Series([2.0, 4.0, 6.0, np.nan, 10.0])
        fit = linear_fit(x, y)
        assert fit is not None
        assert fit.n == 3
        assert abs(fit.slope - 2.0) < 1e-9

    def test_monotonic_but_curved_gives_high_rho_and_lower_r_squared(self):
        x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        fit = linear_fit(x, x**3)
        assert fit is not None
        assert abs(fit.spearman_rho - 1.0) < 1e-9
        assert fit.r_squared < 1.0

    def test_predict_matches_the_fitted_line(self):
        x = pd.Series([1.0, 2.0, 3.0])
        fit = linear_fit(x, 2 * x + 1)
        assert fit is not None
        assert np.allclose(fit.predict(np.array([0.0, 10.0])), [1.0, 21.0])


class TestDistrictTable:
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "district": ["A"] * 4 + ["B"] * 4 + ["C"],
                "price_per_sqm_eur": [1000, 1100, 1200, 1300, 2000, 2100, 2200, 2300, 500],
            }
        )

    def test_ranked_by_median_descending(self):
        table = district_table(self._frame(), min_n=4)
        assert list(table["district"])[0] == "B"
        assert table.loc[0, "median_eur_sqm"] == 2150.0

    def test_thin_districts_are_collapsed_not_dropped(self):
        table = district_table(self._frame(), min_n=4)
        assert table["n"].sum() == 9
        assert any("other" in d for d in table["district"])

    def test_empty_frame_gives_empty_table_with_columns(self):
        table = district_table(pd.DataFrame())
        assert table.empty
        assert "median_eur_sqm" in table.columns


class TestCrossCuts:
    def test_groups_by_rooms_and_construction_decade(self):
        df = pd.DataFrame(
            {
                "price_per_sqm_eur": [1000.0] * 5 + [2000.0] * 5,
                "rooms": [1] * 5 + [2] * 5,
                "construction_year": [1995] * 5 + [2015] * 5,
            }
        )
        cuts = cross_cuts(df, min_n=5)
        assert set(cuts["rooms"]["rooms"]) == {1, 2}
        assert set(cuts["construction decade"]["construction decade"]) == {"1990s", "2010s"}

    def test_groups_below_min_n_are_suppressed(self):
        df = pd.DataFrame({"price_per_sqm_eur": [1000.0, 2000.0], "rooms": [1, 2]})
        assert cross_cuts(df, min_n=5) == {}


class TestGrossRentalYield:
    def test_computed_from_annualised_rent(self):
        sale = pd.DataFrame({"district": ["A"] * 5, "price_eur": [100000.0] * 5})
        rent = pd.DataFrame({"district": ["A"] * 5, "price_eur": [500.0] * 5})
        table = gross_rental_yield(sale, rent, min_n=5)
        # 500 * 12 / 100000 = 6%.
        assert abs(table.loc[0, "gross_yield_pct"] - 6.0) < 1e-9

    def test_districts_thin_on_either_side_are_excluded(self):
        sale = pd.DataFrame({"district": ["A"] * 5, "price_eur": [100000.0] * 5})
        rent = pd.DataFrame({"district": ["A"] * 2, "price_eur": [500.0] * 2})
        assert gross_rental_yield(sale, rent, min_n=5).empty

    def test_empty_inputs_do_not_raise(self):
        assert gross_rental_yield(pd.DataFrame(), pd.DataFrame()).empty


class TestDistrictComparison:
    def _frame(self) -> pd.DataFrame:
        # A: median 1150. B: median 2150. C: a single 500. Pooled median of all nine is 1300.
        return pd.DataFrame(
            {
                "district": ["A"] * 4 + ["B"] * 4 + ["C"],
                "price_per_sqm_eur": [1000, 1100, 1200, 1300, 2000, 2100, 2200, 2300, 500],
            }
        )

    def test_selected_district_sits_above_the_pooled_row(self):
        table = district_comparison(self._frame(), "A")
        assert list(table["district"]) == ["A", _ALL]
        assert table.loc[0, "median_eur_sqm"] == 1150.0

    def test_pooled_row_covers_the_whole_segment(self):
        table = district_comparison(self._frame(), "A")
        assert table.loc[1, "n"] == 9
        assert table.loc[1, "median_eur_sqm"] == 1300.0

    def test_a_thin_district_is_not_collapsed_into_other(self):
        """`district_table` would fold C into an `other` row; the caller asked for C by name."""
        table = district_comparison(self._frame(), "C")
        assert list(table["district"]) == ["C", _ALL]
        assert table.loc[0, "n"] == 1
        assert table.loc[0, "median_eur_sqm"] == 500.0

    def test_unknown_district_leaves_the_pooled_row_alone(self):
        table = district_comparison(self._frame(), "Nowhere")
        assert list(table["district"]) == [_ALL]

    def test_empty_frame_gives_empty_table_with_columns(self):
        table = district_comparison(pd.DataFrame(), "A")
        assert table.empty
        assert "median_eur_sqm" in table.columns


def _banded(
    sale_areas: list[float],
    sale_prices: list[float],
    rent_areas: list[float],
    rent_prices: list[float],
    districts: str = "A",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sale = pd.DataFrame(
        {
            "district": [districts] * len(sale_areas),
            "price_eur": sale_prices,
            "total_area_sqm": sale_areas,
        }
    )
    rent = pd.DataFrame(
        {
            "district": [districts] * len(rent_areas),
            "price_eur": rent_prices,
            "total_area_sqm": rent_areas,
        }
    )
    return sale, rent


class TestYieldBySizeBand:
    def test_every_band_gets_its_columns_even_when_no_listing_falls_in_one(self):
        sale, rent = _banded([30.0], [100000.0], [30.0], [500.0])
        table = yield_by_size_band(sale, rent)
        for band in ("20_50", "50_80", "80_120"):
            assert {f"n_sale_{band}", f"n_rent_{band}", f"gross_yield_pct_{band}"} <= set(
                table.columns
            )

    def test_a_single_rent_listing_still_produces_a_yield(self):
        """The no-threshold rule: disclosure via the counts, not suppression."""
        sale, rent = _banded([30.0], [100000.0], [30.0], [500.0])
        table = yield_by_size_band(sale, rent)
        # 500 * 12 / 100000 = 6%.
        assert abs(table.loc[0, "gross_yield_pct_20_50"] - 6.0) < 1e-9
        assert table.loc[0, "n_rent_20_50"] == 1

    def test_an_empty_band_reports_zero_counts_and_no_yield(self):
        sale, rent = _banded([30.0], [100000.0], [30.0], [500.0])
        table = yield_by_size_band(sale, rent)
        assert table.loc[0, "n_sale_80_120"] == 0
        assert table.loc[0, "n_rent_80_120"] == 0
        assert pd.isna(table.loc[0, "gross_yield_pct_80_120"])

    def test_bands_are_half_open_so_a_boundary_listing_is_counted_once(self):
        sale, rent = _banded([50.0], [100000.0], [50.0], [500.0])
        table = yield_by_size_band(sale, rent)
        assert table.loc[0, "n_sale_20_50"] == 0
        assert table.loc[0, "n_sale_50_80"] == 1

    def test_listings_outside_every_band_count_only_toward_the_all_sizes_yield(self):
        sale, rent = _banded(
            [15.0, 200.0, 30.0], [100000.0] * 3, [15.0, 200.0, 30.0], [500.0] * 3
        )
        table = yield_by_size_band(sale, rent)
        assert table.loc[0, "n_sale"] == 3
        assert table.loc[0, "n_sale_20_50"] == 1
        assert table[["n_sale_50_80", "n_sale_80_120"]].to_numpy().sum() == 0

    def test_a_zero_sale_price_gives_no_yield_rather_than_infinity(self):
        sale, rent = _banded([30.0], [0.0], [30.0], [500.0])
        table = yield_by_size_band(sale, rent)
        assert pd.isna(table.loc[0, "gross_yield_pct"])
        assert pd.isna(table.loc[0, "gross_yield_pct_20_50"])

    def test_missing_area_column_leaves_the_all_sizes_yield_intact(self):
        sale = pd.DataFrame({"district": ["A"], "price_eur": [100000.0]})
        rent = pd.DataFrame({"district": ["A"], "price_eur": [500.0]})
        table = yield_by_size_band(sale, rent)
        assert abs(table.loc[0, "gross_yield_pct"] - 6.0) < 1e-9
        assert table.loc[0, "n_sale_20_50"] == 0


class TestYieldWithMarketRow:
    def _sides(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        sale, rent = _banded([30.0] * 2, [100000.0] * 2, [30.0] * 2, [500.0] * 2)
        other_sale, other_rent = _banded([90.0], [300000.0], [90.0], [1000.0], districts="B")
        return (
            pd.concat([sale, other_sale], ignore_index=True),
            pd.concat([rent, other_rent], ignore_index=True),
        )

    def test_every_district_sits_above_a_single_pooled_row(self):
        table = yield_with_market_row(*self._sides())
        assert list(table["district"]) == ["A", "B", _ALL]

    def test_the_pooled_row_carries_market_wide_band_figures(self):
        table = yield_with_market_row(*self._sides())
        market = table.loc[2]
        assert market["n_sale"] == 3
        assert abs(market["gross_yield_pct_20_50"] - 6.0) < 1e-9
        # B is the only 80-120 listing: 1000 * 12 / 300000 = 4%.
        assert abs(market["gross_yield_pct_80_120"] - 4.0) < 1e-9
        assert market["n_rent_80_120"] == 1

    def test_empty_inputs_do_not_raise(self):
        assert yield_with_market_row(pd.DataFrame(), pd.DataFrame()).empty


class TestYieldComparison:
    def _sides(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        # A: 600*12/120000 = 6.00%. B: 500*12/200000 = 3.00%.
        sale = pd.DataFrame(
            {"district": ["A"] * 5 + ["B"] * 5, "price_eur": [120000.0] * 5 + [200000.0] * 5}
        )
        rent = pd.DataFrame(
            {"district": ["A"] * 5 + ["B"] * 2, "price_eur": [600.0] * 5 + [500.0] * 2}
        )
        return sale, rent

    def test_selected_district_sits_above_the_market_row(self):
        sale, rent = self._sides()
        table = yield_comparison(sale, rent, "A")
        assert list(table["district"]) == ["A", _ALL]
        assert abs(table.loc[0, "gross_yield_pct"] - 6.0) < 1e-9

    def test_market_row_is_the_pooled_yield_not_a_mean_of_districts(self):
        """Pooled: median rent 600, median sale 160000, so 600*12/160000 = 4.50%.

        Averaging the per-district yields would give 4.50% only by coincidence; it differs
        whenever the two sides carry unequal listing counts, as they do here.
        """
        sale, rent = self._sides()
        table = yield_comparison(sale, rent, "A")
        assert table.loc[1, "n_sale"] == 10
        assert table.loc[1, "n_rent"] == 7
        assert abs(table.loc[1, "gross_yield_pct"] - 4.5) < 1e-9

    def test_a_district_thin_on_the_rent_side_is_shown_with_its_counts(self):
        """B has two rent listings. It gets a row, and the counts say how thin it is."""
        sale, rent = self._sides()
        table = yield_comparison(sale, rent, "B")
        assert list(table["district"]) == ["B", _ALL]
        assert table.loc[0, "n_rent"] == 2
        assert abs(table.loc[0, "gross_yield_pct"] - 3.0) < 1e-9

    def test_columns_match_the_unfiltered_table(self):
        sale, rent = self._sides()
        assert list(yield_comparison(sale, rent, "A").columns) == list(
            yield_with_market_row(sale, rent).columns
        )
