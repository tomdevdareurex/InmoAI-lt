"""Tests for the per-segment analysis report.

The two properties that matter most here are reproducibility (plotly randomises figure
container ids unless `div_id` is passed) and self-containment (the report must render
with no network access).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from inmoai_lt.analysis_report import write_analysis_report

_REFERENCE_DATE = pd.Timestamp("2026-08-25", tz="UTC")

_PLOT_KEYS = ["scatter_price_area", "scatter_ppsqm_area", "dist_price", "dist_ppsqm"]

_ALL_KEY = "__all__"


def _segment_frame(
    segment: str,
    listing_type: str,
    n: int,
    price: float,
    seed: int,
    districts: list[str] | None = None,
) -> pd.DataFrame:
    """`n` synthetic listings. `districts` assigns them row-by-row instead of at random."""
    rng = np.random.default_rng(seed)
    area = rng.uniform(25, 120, n)
    # A mild size discount plus noise, so the fitted slope is defined rather than degenerate.
    price_per_sqm = (price / 50) * (1 - 0.002 * (area - 50)) * rng.normal(1.0, 0.05, n)
    return pd.DataFrame(
        {
            "listing_id": [f"{segment}-{i}" for i in range(n)],
            "segment": segment,
            "listing_type": listing_type,
            "property_type": segment.split("_")[0],
            "district": (
                rng.choice(["Žirmūnai", "Naujamiestis", "Pilaitė"], n)
                if districts is None
                else districts
            ),
            "price_eur": price_per_sqm * area,
            "total_area_sqm": area,
            "price_per_sqm_eur": price_per_sqm,
            "rooms": rng.integers(1, 5, n),
            "construction_year": rng.integers(1960, 2020, n),
            "condition": rng.choice(["fully_finished", "partial_finish"], n),
        }
    )


@pytest.fixture
def analysis_df() -> pd.DataFrame:
    """One comfortably-sized sale segment and one deliberately tiny rent segment."""
    return pd.concat(
        [
            _segment_frame("apartment_sale", "sale", 200, 150000.0, seed=1),
            _segment_frame("apartment_rent", "rent", 12, 700.0, seed=2),
        ],
        ignore_index=True,
    )


def _write(df: pd.DataFrame, path) -> str:
    write_analysis_report(df, _REFERENCE_DATE, "test-hash", path)
    return path.read_text(encoding="utf-8")


def test_report_is_byte_identical_across_runs(tmp_path, analysis_df):
    """Guards the explicit `div_id` on every figure.

    Without it plotly generates a fresh UUID per container on each render and the file
    differs every run, which would silently break the pipeline reproducibility test.
    """
    first = tmp_path / "a.html"
    second = tmp_path / "b.html"
    write_analysis_report(analysis_df, _REFERENCE_DATE, "test-hash", first)
    write_analysis_report(analysis_df, _REFERENCE_DATE, "test-hash", second)
    assert first.read_bytes() == second.read_bytes()


def test_every_segment_gets_four_figures(tmp_path, analysis_df):
    html = _write(analysis_df, tmp_path / "r.html")
    for segment in ("apartment_sale", "apartment_rent"):
        for key in _PLOT_KEYS:
            assert f'id="{segment}_{key}"' in html


def test_no_external_resources_are_referenced(tmp_path, analysis_df):
    """The report must render offline: plotly.js is inlined, not fetched.

    Asserted at tag level rather than as a raw substring search, because plotly's own
    bundle contains an `https://unpkg.com/maki@...` string inside its Mapbox icon loader
    -- a code path this report never reaches, since it renders only Scattergl and
    Histogram traces.
    """
    html = _write(analysis_df, tmp_path / "r.html")
    assert not re.search(r"<script[^>]+\bsrc\s*=", html)
    assert not re.search(r'<link[^>]+href\s*=\s*["\']https?:', html)


def test_small_segment_shows_a_banner_and_suppresses_breakdowns(tmp_path, analysis_df):
    html = _write(analysis_df, tmp_path / "r.html")
    rent_section = html.split("<h2>apartment / rent</h2>")[1]
    assert "Small sample: 12 listings" in rent_section
    assert "suppressed" in rent_section
    # The healthy sale segment must still get its district table.
    sale_section = html.split("<h2>apartment / sale</h2>")[1].split("<h2>")[0]
    assert "Median price per sqm by district" in sale_section
    assert "suppressed" not in sale_section


def test_rent_axes_are_labelled_as_monthly_rent(tmp_path, analysis_df):
    html = _write(analysis_df, tmp_path / "r.html")
    assert "Monthly rent (EUR)" in html
    assert "Price (EUR)" in html


def test_empty_frame_renders_a_page_rather_than_raising(tmp_path):
    html = _write(pd.DataFrame(), tmp_path / "r.html")
    assert "<h1>InmoAI-lt Analysis Report</h1>" in html
    assert "no priced segments" in html


def test_segment_with_no_usable_numbers_renders_a_placeholder(tmp_path):
    df = pd.DataFrame(
        {
            "listing_id": ["1", "2"],
            "segment": ["apartment_sale"] * 2,
            "listing_type": ["sale"] * 2,
            "price_eur": [None, None],
            "total_area_sqm": [None, None],
            "price_per_sqm_eur": [None, None],
        }
    )
    html = _write(df, tmp_path / "r.html")
    assert "not enough data to plot" in html


def _side(
    property_type: str,
    listing_type: str,
    districts: list[str],
    price: float,
    area: float = 50.0,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "segment": f"{property_type}_{listing_type}",
            "property_type": property_type,
            "listing_type": listing_type,
            "district": districts,
            "price_eur": price,
            "total_area_sqm": area,
            "price_per_sqm_eur": price / area,
        }
    )


def _yield_frame(district_rent_counts: dict[str, int]) -> pd.DataFrame:
    """6 apartment sale listings per district at EUR 120,000, plus the requested rent counts."""
    sale_districts = [d for d in district_rent_counts for _ in range(6)]
    rent_districts = [d for d, c in district_rent_counts.items() for _ in range(c)]
    return pd.concat(
        [
            _side("apartment", "sale", sale_districts, 120000.0),
            _side("apartment", "rent", rent_districts, 600.0),
        ],
        ignore_index=True,
    )


def _yield_section(html: str) -> str:
    return html.split("<h2>Gross rental yield by district</h2>")[1]


def test_yield_is_computed_within_a_property_type_not_across(tmp_path):
    """Houses are ~4x the price of apartments here, so pooling would halve the apartment yield.

    A house's rent divided by an apartment's sale price is not a yield, so each property
    type must be paired only with itself.
    """
    districts = ["Žirmūnai"] * 6
    df = pd.concat(
        [
            _side("apartment", "sale", districts, 120000.0),
            _side("apartment", "rent", districts, 600.0),   # 600*12/120000  = 6.00%
            _side("house", "sale", districts, 480000.0),
            _side("house", "rent", districts, 1600.0),      # 1600*12/480000 = 4.00%
        ],
        ignore_index=True,
    )
    section = _yield_section(_write(df, tmp_path / "r.html"))
    apartment_block, house_block = section.split("<h3>house</h3>")

    assert "6.00" in apartment_block and "4.00" not in apartment_block
    assert "4.00" in house_block and "6.00" not in house_block


def test_property_type_with_no_rent_side_is_reported_as_such(tmp_path):
    """There is no house-rent source today; that must be stated, not silently omitted."""
    districts = ["Žirmūnai"] * 6
    df = pd.concat(
        [
            _side("apartment", "sale", districts, 120000.0),
            _side("apartment", "rent", districts, 600.0),
            _side("house", "sale", districts, 480000.0),
        ],
        ignore_index=True,
    )
    section = _yield_section(_write(df, tmp_path / "r.html"))
    assert "no rent listings for this property type" in section.split("<h3>house</h3>")[1]


def test_every_yield_cell_carries_its_sale_and_rent_counts(tmp_path):
    section = _yield_section(_write(_yield_frame({"Žirmūnai": 6}), tmp_path / "r.html"))
    # 600 * 12 / 120000 = 6%, from 6 sale and 6 rent listings, all of them 50 sqm.
    assert "Žirmūnai" in section
    assert "6.00 (6/6)" in section


def test_thin_rent_side_is_shown_with_its_counts_rather_than_withheld(tmp_path):
    """No threshold: two rent listings still produce a row, and the counts disclose that."""
    section = _yield_section(_write(_yield_frame({"Žirmūnai": 2}), tmp_path / "r.html"))
    assert "6.00 (6/2)" in section


def test_the_unfiltered_table_ends_with_a_pooled_market_row(tmp_path):
    frame = _yield_frame({"Žirmūnai": 6, "Naujamiestis": 6})
    section = _yield_section(_write(frame, tmp_path / "r.html"))
    assert "ALL (segment)" in section


def test_a_band_no_listing_reaches_still_gets_its_column(tmp_path):
    """Every 50 sqm listing sits in 50-80, but the shape of the table must not vary."""
    section = _yield_section(_write(_yield_frame({"Žirmūnai": 6}), tmp_path / "r.html"))
    assert "80\u2013120 sqm" in section
    assert "\u2013 (0/0)" in section


def test_listings_are_split_across_bands_by_floor_area(tmp_path):
    districts = ["Žirmūnai"] * 4
    df = pd.concat(
        [
            _side("apartment", "sale", districts, 120000.0, area=30.0),
            _side("apartment", "rent", districts, 600.0, area=30.0),
            _side("apartment", "sale", districts, 240000.0, area=100.0),
            _side("apartment", "rent", districts, 800.0, area=100.0),
        ],
        ignore_index=True,
    )
    section = _yield_section(_write(df, tmp_path / "r.html"))
    assert "6.00 (4/4)" in section  # 20-50: 600*12/120000
    assert "4.00 (4/4)" in section  # 80-120: 800*12/240000
    assert "\u2013 (0/0)" in section  # 50-80 holds nothing


# --- district filter -------------------------------------------------------------------

# 175 sale listings: three districts clear the 10-row minimum, Antakalnis does not.
# Pilaite clears it but stays under 30, which is where cross-cuts get suppressed.
_SALE_DISTRICTS = (
    ["Žirmūnai"] * 100 + ["Naujamiestis"] * 60 + ["Pilaitė"] * 12 + ["Antakalnis"] * 3
)


@pytest.fixture
def filtered_df() -> pd.DataFrame:
    """A sale segment spanning four districts, and a rent segment present in only one."""
    return pd.concat(
        [
            _segment_frame(
                "apartment_sale", "sale", len(_SALE_DISTRICTS), 150000.0, 1, _SALE_DISTRICTS
            ),
            _segment_frame("apartment_rent", "rent", 12, 700.0, 2, ["Žirmūnai"] * 12),
        ],
        ignore_index=True,
    )


def _options(html: str) -> list[str]:
    """The `<option>` values, in document order."""
    select = html.split('<select id="district-select">')[1].split("</select>")[0]
    return re.findall(r'<option value="([^"]*)"', select)


def _payload(html: str) -> dict:
    """The embedded view data.

    Terminating the match at the first `</script>` is safe precisely because
    `district_filter` escapes every `<` in the blob, which the injection test pins down.
    """
    match = re.search(
        r'<script type="application/json" id="district-views">(.*?)</script>', html, re.DOTALL
    )
    assert match is not None
    return json.loads(match.group(1))


def _table_rows(markup: str) -> list[str]:
    """Rows of the first `<table>` in `markup`, header included."""
    table = markup.split("<table>")[1].split("</table>")[0]
    return re.findall(r"<tr>(.*?)</tr>", table, re.DOTALL)


def test_dropdown_offers_only_districts_clearing_the_minimum(tmp_path, filtered_df):
    html = _write(filtered_df, tmp_path / "r.html")
    assert "Antakalnis" not in _options(html)


def test_options_are_sorted_with_diacritics_folded(tmp_path, filtered_df):
    """Code-point order would push `Žirmūnai` (U+017D) past every ASCII name."""
    html = _write(filtered_df, tmp_path / "r.html")
    assert _options(html) == [_ALL_KEY, "Naujamiestis", "Pilaitė", "Žirmūnai"]


def test_filter_is_additive_and_leaves_the_default_view_intact(tmp_path, filtered_df):
    """The page must still paint its unfiltered form with JavaScript disabled."""
    html = _write(filtered_df, tmp_path / "r.html")
    assert f'<option value="{_ALL_KEY}" selected>' in html
    for segment in ("apartment_sale", "apartment_rent"):
        for key in _PLOT_KEYS:
            assert f'id="{segment}_{key}"' in html


def test_payload_covers_every_offered_district(tmp_path, filtered_df):
    html = _write(filtered_df, tmp_path / "r.html")
    assert set(_payload(html)["views"]) == set(_options(html))


def test_no_external_resources_are_referenced_with_the_filter_present(tmp_path, filtered_df):
    html = _write(filtered_df, tmp_path / "r.html")
    assert _options(html)[1:]  # the filter really is in this page
    assert not re.search(r"<script[^>]+\bsrc\s*=", html)
    assert not re.search(r'<link[^>]+href\s*=\s*["\']https?:', html)


def test_a_district_name_cannot_break_out_of_the_payload(tmp_path):
    """District names are scraped, so one could carry markup.

    The blob sits in a `<script>` element, which is raw text: HTML-escaping would survive
    `JSON.parse` literally, so `district_filter` escapes `<`/`>`/`&` as JSON `\\uXXXX`
    instead. That keeps the name unrepresentable to the HTML tokenizer while still
    decoding to the original characters.
    """
    hostile = "</script><img src=x onerror=alert(1)>"
    df = _segment_frame(
        "apartment_sale", "sale", 120, 150000.0, 3, ["Žirmūnai"] * 100 + [hostile] * 20
    )
    html = _write(df, tmp_path / "r.html")

    assert hostile not in html
    assert "<img src=x" not in html
    assert "\\u003c/script\\u003e" in html

    parsed = _payload(html)
    assert hostile in parsed["views"]


def test_figure_specs_carry_no_template_and_the_shared_one_is_emitted_once(tmp_path, filtered_df):
    """Inlining `plotly_white` in every spec costs ~7 KB a figure; it is hoisted instead."""
    payload = _payload(_write(filtered_df, tmp_path / "r.html"))
    assert payload["template"]["layout"]

    specs = [
        spec
        for view in payload["views"].values()
        for segment in view["segments"].values()
        for spec in segment["figures"].values()
    ]
    assert specs
    assert all("template" not in spec["layout"] for spec in specs)


def test_filtered_district_table_compares_the_district_against_the_segment(tmp_path, filtered_df):
    view = _payload(_write(filtered_df, tmp_path / "r.html"))["views"]["Žirmūnai"]
    tables = view["segments"]["apartment_sale"]["tables"]
    ranking = tables.split("Median price per sqm, selected district vs segment")[1]

    header, *rows = _table_rows(ranking)
    assert "district" in header
    assert len(rows) == 2
    assert "Žirmūnai" in rows[0]
    assert "ALL (segment)" in rows[1]


def test_district_absent_from_a_segment_reports_zero_rows(tmp_path, filtered_df):
    """Rent exists only in Žirmūnai here; the other districts must say so, not render empty."""
    view = _payload(_write(filtered_df, tmp_path / "r.html"))["views"]["Naujamiestis"]
    rent = view["segments"]["apartment_rent"]
    assert rent["rows"] == 0
    assert "No listings in this segment for Naujamiestis." in rent["banner"]
    assert rent["tables"] == ""


def test_thin_district_keeps_its_comparison_but_loses_cross_cuts(tmp_path, filtered_df):
    """12 listings support a median against the segment, but not a median per room count."""
    view = _payload(_write(filtered_df, tmp_path / "r.html"))["views"]["Pilaitė"]
    segment = view["segments"]["apartment_sale"]
    assert segment["rows"] == 12
    assert "Cross-cut breakdowns are suppressed below 30 listings." in segment["banner"]
    assert "below the 30-row minimum" in segment["tables"]
    assert "Median price per sqm, selected district vs segment" in segment["tables"]


def test_filtered_yield_body_shows_the_district_above_the_market_row(tmp_path, filtered_df):
    rows = _table_rows(_payload(_write(filtered_df, tmp_path / "r.html"))["views"]["Žirmūnai"]["yield_html"])
    assert len(rows) == 3  # header, the district, the market
    assert "Žirmūnai" in rows[1]
    assert "ALL (segment)" in rows[2]


def test_empty_frame_omits_the_filter_entirely(tmp_path):
    html = _write(pd.DataFrame(), tmp_path / "r.html")
    assert "district-select" not in html
    assert "district-views" not in html


_HASH_SCRIPT = """
import hashlib, sys
from pathlib import Path
import pandas as pd
from inmoai_lt.analysis_report import write_analysis_report

out = Path(sys.argv[2])
write_analysis_report(
    pd.read_csv(sys.argv[1]), pd.Timestamp("2026-08-25", tz="UTC"), "test-hash", out
)
print(hashlib.sha256(out.read_bytes()).hexdigest())
"""


def _report_hash(csv: Path, out: Path, hash_seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONIOENCODING": "utf-8"}
    src = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = os.pathsep.join([str(src), env.get("PYTHONPATH", "")])
    result = subprocess.run(
        [sys.executable, "-c", _HASH_SCRIPT, str(csv), str(out)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return result.stdout.strip()


def test_output_is_identical_under_different_hash_seeds(tmp_path, filtered_df):
    """The district set must be sorted before it reaches the page.

    Python salts string hashing per process, so iterating the raw `set` behind
    `eligible_districts` would reorder the dropdown and the payload keys between runs.
    The same-process byte-identity test cannot see this, because one process has one salt.
    """
    csv = tmp_path / "analysis.csv"
    filtered_df.to_csv(csv, index=False, encoding="utf-8")
    first = _report_hash(csv, tmp_path / "a.html", "0")
    second = _report_hash(csv, tmp_path / "b.html", "1")
    assert first == second
    assert len(first) == 64
