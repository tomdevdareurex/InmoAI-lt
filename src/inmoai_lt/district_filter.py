"""In-page district filter for the analysis report.

Every view is computed in Python and embedded in the page, so `stats.py` stays the only
implementation of every measure -- the browser re-renders precomputed figures and swaps
precomputed table HTML, it never recomputes a median.

Three constraints shape this module:

*Reproducibility.* The pipeline guarantees byte-identical output. The district union is
therefore `sorted()` before it leaves this module (Python salts string hashing per
process, so iterating the raw set would differ between runs) and the payload is dumped
with `sort_keys=True`.

*Size.* The `plotly_white` template is ~7 KB and would repeat in every figure spec, which
on the real dataset is 4.39 MB of duplication. It is emitted once at the top of the
payload and re-attached in the browser, which brings the same payload down to 0.84 MB.

*Escaping.* District names come from scraped listings, and the payload sits inside a
`<script>` element, which is raw text rather than parsed markup. See
`_escape_json_for_html`.
"""

from __future__ import annotations

import html as html_lib
import json
import unicodedata

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

# Payload key and `<option>` value for the unfiltered view.
ALL_KEY = "__all__"

# Must match the config `figures.to_div` passes, so a re-rendered figure behaves exactly
# like the one the page was served with.
_PLOT_CONFIG = {"displaylogo": False, "responsive": True}


def _sort_key(name: str) -> tuple[str, str]:
    """Diacritic-folded sort key, so `Žirmūnai` files under Z rather than after it.

    A plain `sorted()` is deterministic but orders by code point, which pushes every
    Lithuanian name carrying a diacritic (Ž = U+017D, well above Z = U+005A) to the end
    of the dropdown. Folding to ASCII for the primary key fixes the ordering without
    depending on a system locale; the raw name breaks ties so the order stays total.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return (folded.casefold(), name)


def eligible_districts(segments: dict[str, pd.DataFrame], min_n: int = 10) -> list[str]:
    """Districts worth offering: at least `min_n` rows in at least one segment.

    "At least one" rather than "every": a district can be well covered for apartment
    sales and absent from rentals, and that is still worth looking at. Segments where it
    is thin render their own "not enough data" fallbacks.
    """
    found: set[str] = set()
    for frame in segments.values():
        if "district" not in frame.columns:
            continue
        counts = frame["district"].dropna().value_counts()
        found |= {str(name) for name in counts[counts >= min_n].index}
    return sorted(found, key=_sort_key)


def district_totals(segments: dict[str, pd.DataFrame], districts: list[str]) -> dict[str, int]:
    """Row count per district summed across all segments.

    Summed rather than per-segment because one dropdown drives the whole page: a count
    that described only the sale segment would misrepresent what the user is selecting.
    """
    totals = dict.fromkeys(districts, 0)
    for frame in segments.values():
        if "district" not in frame.columns:
            continue
        counts = frame["district"].dropna().value_counts()
        for name, count in counts.items():
            key = str(name)
            if key in totals:
                totals[key] += int(count)
    return totals


def render_control(districts: list[str], totals: dict[str, int], all_total: int) -> str:
    """The dropdown. `<option>` text and value are both HTML-escaped."""
    options = [
        f'<option value="{ALL_KEY}" selected>All districts ({all_total:,})</option>'
    ]
    for name in districts:
        label = f"{name} ({totals.get(name, 0):,})"
        options.append(
            f'<option value="{html_lib.escape(name, quote=True)}">'
            f"{html_lib.escape(label)}</option>"
        )
    return (
        '<div class="filter-bar">'
        '<label for="district-select">District</label>'
        f'<select id="district-select">{"".join(options)}</select>'
        '<span class="filter-hint">every plot and table below follows this selection</span>'
        "</div>"
    )


def shared_template() -> dict[str, object]:
    """The `plotly_white` template, hoisted out of the individual figure specs.

    Derived from a real `go.Figure` rather than from `pio.templates` so it is byte-
    identical to the template the statically-rendered default figures already carry.
    """
    figure = go.Figure()
    figure.update_layout(template="plotly_white")
    return json.loads(pio.to_json(figure))["layout"]["template"]


def figure_spec(figure: go.Figure) -> dict[str, object]:
    """Serialize a figure to a plain dict with the shared template removed.

    Round-tripped through `plotly.io.to_json` rather than dumped from
    `figure.to_plotly_json()`: plotly picks its JSON engine at import time (orjson when
    available, which encodes numpy arrays as compact base64), and going through the same
    entry point keeps these specs consistent with the statically-rendered figures in the
    same page.
    """
    spec = json.loads(pio.to_json(figure))
    layout = spec.get("layout", {})
    layout.pop("template", None)
    return {"data": spec.get("data", []), "layout": layout}


def _escape_json_for_html(blob: str) -> str:
    """Make a JSON string safe to inline in a `<script>` element.

    HTML-escaping would be wrong here: `<script>` content is raw text, so `&lt;` would
    survive `JSON.parse` as those four literal characters. What actually matters is that
    the HTML tokenizer ends the element at `</script`, and enters a different state at
    `<!--`. Escaping the three characters as JSON `\\uXXXX` sequences makes both
    unrepresentable while `JSON.parse` still yields the original text, so a district
    named `</script><img src=x onerror=...>` round-trips as data instead of markup.

    This runs on the serialized string, after any `json.loads` round-trip -- decoding
    JSON turns plotly's own escaping back into raw `<`.
    """
    return blob.replace("&", r"\u0026").replace("<", r"\u003c").replace(">", r"\u003e")


def render_payload(views: dict[str, object], template: dict[str, object]) -> str:
    """The embedded JSON blob holding every precomputed view.

    `sort_keys` keeps the output byte-stable across runs. `allow_nan=False` is deliberate:
    Python would otherwise emit a bare `NaN`, which is not valid JSON and would make
    `JSON.parse` throw in the browser. If it raises, a non-finite value has leaked past
    the `stats` helpers and that is a bug to fix rather than a flag to relax.
    """
    blob = json.dumps(
        {"template": template, "views": views},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (
        '<script type="application/json" id="district-views">'
        f"{_escape_json_for_html(blob)}"
        "</script>"
    )


# Read via `.textContent`, never `innerHTML`: the payload is data, and textContent
# returns it without the browser re-parsing entities out of it.
_SCRIPT = """
(function () {
  var node = document.getElementById("district-views");
  var select = document.getElementById("district-select");
  if (!node || !select || typeof Plotly === "undefined") { return; }

  var payload = JSON.parse(node.textContent);
  var config = %(config)s;

  function setHtml(id, markup) {
    var el = document.getElementById(id);
    if (el) { el.innerHTML = markup; }
  }

  function apply(key) {
    var view = payload.views[key];
    if (!view) { return; }
    setHtml("stat-cards", view.cards);
    setHtml("yield-body", view.yield_html);
    Object.keys(view.segments).forEach(function (name) {
      var segment = view.segments[name];
      setHtml("banner-" + name, segment.banner);
      setHtml("tables-" + name, segment.tables);
      Object.keys(segment.figures).forEach(function (figureKey) {
        var spec = segment.figures[figureKey];
        var layout = Object.assign({}, spec.layout, { template: payload.template });
        Plotly.react(name + "_" + figureKey, spec.data, layout, config);
      });
    });
  }

  select.addEventListener("change", function () { apply(select.value); });
})();
"""


def render_script() -> str:
    """The dropdown handler.

    Deliberately contains no literal closing-script sequence, so it cannot terminate its
    own element early.
    """
    body = _SCRIPT % {"config": json.dumps(_PLOT_CONFIG, sort_keys=True)}
    return f"<script>{body}</script>"
