# InmoAI-lt

A reproducible cleaning pipeline for `aruodas.lt` Vilnius real-estate listings
(apartments and houses, sale). It turns the raw scraper output in
`real_estate/data/processed/` into an analysis-ready CSV/Parquet pair plus a full
audit trail (`cleaning_report.json` / `.md`), without ever mutating the source data.

## Relationship to InmoAI

This project is a Lithuanian sibling of the Chilean **InmoAI** pre-processing pipeline,
not a fork of it. `docs/SOURCE_ANALYSIS.md` records the full reuse analysis; in short:

- **Reused (concept)**: a staged pipeline with an explicit order and a persisted report
  per run; comma/dot decimal + thousands-separator parsing; `to_snake_case` column
  normalisation (without stripping diacritics from *values*); drop-rows-with-no-price as
  a fatal rule; a two-tier duplicate strategy; bounds-based outlier flags calibrated
  per property type; age-from-construction-year using a fixed reference date instead of
  the wall clock.
  - **Adapted**: Spanish `comuna`/`barrio` extraction → Lithuanian `district` collapse;
  InmoAI's census/metro/barrio joins → deferred to `enrichment/` (no equivalent Lithuanian
  datasets are bundled here).
- **Excluded**: InmoAI's 7-day rolling price index (only 4 distinct scrape days exist
  here — not enough signal), and all of InmoAI's Santiago-specific census/subway/barrio
  join logic (no Lithuanian equivalent dataset was provided).

No thresholds, vocabularies or column names are copied from InmoAI's Chilean data —
every bound in `config/cleaning.yaml` is calibrated against the measured Vilnius
distribution in `docs/DATA_PROFILE.md`.

## Scope

- **In scope**: apartments for sale (3105 rows), apartment rentals (1641 rows), houses for
  sale (834 rows) and house rentals (96 rows) in Vilnius — 5676 rows total.
- Each market is cleaned and reported as its own **segment**
  (`<property_type>_<listing_type>`) and never pooled: rent is priced in EUR/month and
  sale in EUR, so shared thresholds or a combined distribution would be meaningless.
- The house rental sample is small (96 rows). It is carried through with its own bounds and
  labelled as low-n — in the analysis report and again by the modelling layer, which sets
  `low_confidence` on anything derived from it — rather than being dropped or presented as
  if it were as solid as the other three segments.
- Spatial/socio-economic enrichment (census, POI distances, district geometry) is
  deferred — see `src/inmoai_lt/enrichment/README.md`.

## Expected input

Four CSVs with an identical 102-column schema (`utf-8-sig`, one row per listing),
produced by the `real_estate` scraper and never modified by this project:

```
real_estate/data/processed/apartments_sale_vilnius.csv   (3105 rows)
real_estate/data/processed/apartments_rent_vilnius.csv   (1641 rows)
real_estate/data/processed/houses_sale_vilnius.csv        (834 rows)
real_estate/data/processed/houses_rent_vilnius.csv         (96 rows)
```

The exact schema is enforced by `inmoai_lt.schema.EXPECTED_RAW_COLUMNS` /
`assert_raw_schema` and fails loudly on drift. Full column-by-column profiling lives in
`docs/DATA_PROFILE.md`.

## Install

```bash
python -m venv .venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```
## Install AI tool (dbx-llm + Databricks CLI)

One-time setup:

```powershell
# 1. Python package
python -m pip install --upgrade --force-reinstall --no-cache-dir "dbx-llm[ui] @ git+https://github.com/tomdevdareurex/dbx-llm.git"

# 2. Databricks CLI — winget adds it to your user PATH automatically
winget install Databricks.DatabricksCLI

# 3. Open a NEW terminal so PATH refreshes, then confirm it resolves
where.exe databricks
```

Every time auth expires — this is the only command normally needed:

```powershell
databricks auth login --profile DEFAULT
python -m dbx_llm --gui
```

The token is written to `%USERPROFILE%\.databrickscfg` and survives restarts.

### Troubleshooting: `databricks` is not recognized

winget does **not** create a shim in `WinGet\Links`; it appends the package folder to your
**user** PATH. Running processes keep their old copy of PATH, so a fresh install is invisible
to any terminal that was already open.

1. Quit **all** VS Code windows and reopen. A new terminal tab is not enough — integrated
   terminals inherit VS Code's process environment.
2. Re-check with `where.exe databricks`.

Only if it is still not found is the PATH entry genuinely missing. Reinstall, then restore
the entry permanently:

```powershell
winget install Databricks.DatabricksCLI

$dir = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Databricks.DatabricksCLI*\databricks.exe").Directory.FullName
$raw = (Get-Item 'HKCU:\Environment').GetValue('Path', $null, 'DoNotExpandEnvironmentNames')
if (($raw -split ';') -notcontains $dir) {
  Set-ItemProperty 'HKCU:\Environment' -Name Path -Value "$raw;$dir" -Type ExpandString
}
```

Then open a new terminal. Two details matter: `-Type ExpandString` preserves the
`REG_EXPAND_SZ` registry type (`[Environment]::SetEnvironmentVariable` silently downgrades it
to `REG_SZ`), and the `if` guard stops repeated runs from stacking duplicate entries.

Do **not** use `$env:Path += "..."` as the fix. It lasts only for that one window, and
`python -m dbx_llm` will still fail: the profile uses `auth_type = databricks-cli`, which
makes the Python SDK spawn an executable named `databricks` resolved from the PATH it
inherited at startup.

## How to run

```bash
# 1. Copy the source CSVs into data/raw/ (never writes to real_estate/)
python scripts/ingest_raw.py --source "<path-to-real_estate>/data/processed"

# 2. Run the full cleaning pipeline
python -m inmoai_lt clean
# or with explicit paths:
python -m inmoai_lt clean --config config/cleaning.yaml --raw-dir data/raw --out-dir data/processed

# 3. Optional: print a schema/missingness summary of the cleaned output
python -m inmoai_lt profile
```

Or via the `Makefile`: `make install`, `make ingest`, `make clean-data`, `make test`,
`make lint`.

## Outputs (in `data/processed/`)

| File | Contents |
|---|---|
| `vilnius_listings_clean.csv` (+ `.parquet`) | All 5676 retained rows, with every `flag_*` column, `is_valid`, `is_duplicate` |
| `vilnius_listings_analysis.csv` (+ `.parquet`) | `is_valid & ~is_duplicate` subset (5575 rows) — ready for modelling |
| `segments/<segment>_analysis.csv` (+ `.parquet`) | The analysis subset partitioned by `segment` (`apartment_sale` 3036, `apartment_rent` 1629, `house_sale` 814, `house_rent` 96). The parts sum exactly to the analysis file with no overlap |
| `analysis_report.html` | Per-segment distributional analysis: 4 Plotly figures per segment plus percentile, spread and cross-cut tables. Self-contained — `plotly.js` is inlined, no network access needed |
| `cleaning_report.json` | Machine-readable run log: source hashes, per-stage row counts, dropped/renamed columns, recovery counts, unmapped values, flag counts, duplicate groups |
| `cleaning_report.md` / `.html` | Human-readable summary of the same report |
| `unmapped_attributes.csv` | Any `raw_attributes_json` label not recovered or already promoted (empty on this run) |
| `logs/cleaning_<reference_date>.log` | Full run log (UTF-8; console falls back to `backslashreplace` on non-UTF-8 Windows code pages) |

All CSVs are written `encoding="utf-8-sig"`, `index=False`, `lineterminator="\n"`,
sorted by `(property_type, listing_id)`. Two runs on the same input produce
byte-identical files (verified in `tests/test_pipeline.py`).

## Modelling

`src/inmoai_lt/modeling/` trains one price model per segment on the cleaned segment files.
The point of having all four is **cross-prediction**: score a for-sale listing with the
*rental* model of the same property type to estimate the rent it could achieve, then turn
that into a gross cap rate. Adapted from InmoAI's
`models/MAIN_Tomas_feature_selection_2.3._neighbours_percentages_departamento.ipynb`.

Full methodology, design reasoning and deviations from the reference notebook:
**[`docs/MODELS.md`](docs/MODELS.md)**.

The estimator is a `StackingRegressor` whose base learner is a haversine KNN over
`latitude`/`longitude` predicting local **price per sqm**, and whose final estimator is
CatBoost seeing that estimate alongside the raw features. Stacking cross-fits the base
learner, which is what keeps the neighbour feature free of target leakage. Categoricals are
target-encoded against price per sqm, so a district full of large flats is not mistaken for
an expensive one.

Two notebooks drive it; all the logic sits in Python modules behind them:

| Notebook | What it does |
|---|---|
| `notebooks/01_train_segment.ipynb` | Set `SEGMENT` in the first cell, run top to bottom: inspect → train → held-out metrics + predicted-vs-actual plot → save. Run once per segment |
| `notebooks/02_cap_rate.ipynb` | Set `PROPERTY_TYPE`, load the sale+rent model pair, cross-predict rent, rank districts by yield |

```python
from inmoai_lt.modeling import SegmentModel, estimate_cap_rate, load_segment

model = SegmentModel.train("apartment_sale")     # train + score a held-out split
model.save()                                     # -> models/apartment_sale.joblib

rent_model = SegmentModel.load("apartment_rent")
sale = load_segment("apartment_sale")
cap_rates = estimate_cap_rate(sale, rent_model, sale_model=model)
```

`config/modeling.yaml` holds the CatBoost hyperparameters, the neighbour count (with a
smaller `house_rent` override) and `target`, which selects what the estimator regresses on:
`price`, `price_per_sqm` or `log_price`. `predict()` always inverts back to EUR, so the
three modes are directly comparable on the same held-out split.

Held-out performance on the current data (target `price`, EUR — EUR/month for rent):

| Segment | Train rows | MAPE | MedAE | R² |
|---|---|---|---|---|
| `apartment_sale` | 2428 | 16.3% | 17 812 | 0.887 |
| `apartment_rent` | 1303 | 13.1% | 64 | 0.823 |
| `house_sale` | 651 | 39.1% | 65 818 | 0.714 |
| `house_rent` | 76 | 50.3% | 469 | 0.392 |

`house_rent` is **low-n** and is flagged as such: `SegmentModel.low_n` is set, and every
cap rate derived from it carries `low_confidence=True`. Its metrics will swing between
seeds — that is a data-volume limit, and the honest fix is a larger rent scrape upstream.

Cap rates are **gross**: they ignore vacancy, management, maintenance and tax, so they rank
listings rather than underwrite them. `low_confidence` is also set when a listing's district
was never seen by the rent model, because target encoding then falls back to the global mean
and the rent estimate carries no local signal.

## Assumptions

1. `raw_attributes_json` is the authoritative source for attributes the scraper did not
   promote to their own column; recovering from it is preferred over re-scraping.
2. `Metai`'s `statyba`/`renovacija` split means construction / renovation year. Verified
   against 355 recovered rows; the recovered `construction_year` matches the scraper's
   own value everywhere both exist.
3. Absence of a feature key in `all_features_json` means "not advertised", treated as
   `False` only when that feature is captured at all for the property type (tri-state
   rule) — never fabricated for a feature the source doesn't track for that type.
4. Bounds in `config/cleaning.yaml` are calibrated envelopes around the observed Vilnius
   distribution and only set flags — they never delete rows.
5. `reference_date` comes from the data's own max `scrape_timestamp_utc`, so output does
   not change with the wall clock.
6. Lithuanian diacritics are semantically meaningful and are preserved everywhere in
   output; a separate `fold_key()` helper folds them only for internal lookup keys.
7. Rent and sale are different price regimes, so quality bounds are keyed on
   `segment` (`<property_type>_<listing_type>`), never on `property_type` alone. The
   `house_rent` sample is small (96 rows) and is labelled as such in the report rather
   than being pooled with the other segments or dropped.
8. A missing coordinate is a gap in the record, not grounds for deletion: `latitude` /
   `longitude` are not in `quality.fatal`, and `flag_missing_coordinates` is advisory and
   distinct from `flag_coords_outside_vilnius`. All four current sources are 100%
   populated, so nothing is flagged today — the rule matters for future scrapes.
9. `image_count` is a scraper capture artefact (4 for ~99.5% of rows), not a listing
   attribute; retained but not intended as a model feature.

## Deferred functionality

- **Enrichment** (census/socio-economic join, nearest-POI distances, district geometry)
  — see `src/inmoai_lt/enrichment/README.md`. `enrichment.enrich()` raises
  `NotImplementedError`; no enrichment logic exists yet.
- **Rolling price index** (InmoAI's `price_uf_MA_7D` equivalent) — only 7 distinct scrape
  days exist in the current data, so a rolling window would be noise, not signal.
- **Geocoding** — no geocoding step exists in this project. Every current source is fully
  geocoded by the scraper; a future gap would be flagged, not imputed.

## Known data-quality issues

- 39 columns are structurally empty in the current scrape (`bedrooms`, `bathrooms`,
  `living_area_sqm`, `usable_area_sqm`, `ownership_type`, `seller_type`, `agency_name`,
  price-change fields, `basement_area_sqm`, `garage_area_sqm`, …). These are scraper
  gaps, not cleaning gaps — fixing them belongs in `real_estate`, and this pipeline will
  pick them up automatically once populated. (`docs/DATA_PROFILE.md` documents 37 of
  these as "all-null in both files"; `basement_area_sqm` and `garage_area_sqm` are
  additionally measured as 100% empty for houses too in the currently ingested data,
  despite being listed there as "populated for houses" — a minor discrepancy between
  that document and the actual scrape on disk today.)
- `lift` is never captured for apartments *or* houses in the current scrape — a notable
  omission for price modelling, and a concrete feature request for the scraper.
- `full_address` lacks a house number; `Namo numeris` (recovered as `house_number`)
  covers only 72% of apartments and 54% of houses, so the content-based duplicate key is
  imperfect for the remainder (rows with a missing key part are never grouped, per the
  "never fabricate a match" rule).
- `heating_type`/`water_supply` token casing is inconsistent in the source
  (`"Centrinis, dujinis"`); handled here via case-insensitive mapping, but worth fixing
  upstream.
- `image_count` is capped at 4 for 5640/5676 rows — a scraper capture limit, not a
  listing property.
- `house_rent` has only 96 rows. Distributional statistics for that segment are indicative
  at best, and models trained on it are flagged low-n; the fix is a larger scrape upstream,
  not more cleaning logic.
- `description_lt` contains `[REDACTED_PHONE]` / `[REDACTED_EMAIL]` markers the scraper
  already applied (707 apartment rows, 183 house rows); this pipeline does not and
  cannot attempt to reverse the redaction.
- Only 7 distinct scrape days exist, so no temporal/price-trend analysis is possible yet.

## Development

```bash
pytest --cov=src/inmoai_lt --cov-report=term-missing   # tests + coverage
ruff check src tests                                     # lint
```

Coverage on `src/inmoai_lt/cleaning/` is ≥ 80% (target from `docs/IMPLEMENTATION_PLAN.md`
§5); see the latest `pytest --cov` output for exact per-module numbers.
