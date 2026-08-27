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

- **In scope (v1)**: apartments for sale (3105 rows) and houses for sale (834 rows) in
  Vilnius — 3939 rows total.
- **Out of scope (v1)**: apartment *rentals* (`apartments_rent_vilnius.csv`, 50 rows) —
  disabled in `config/cleaning.yaml` because it's a partial scrape, too small to clean
  or validate meaningfully alongside the sale data. Re-enable the source entry once more
  rent rows exist.
- Spatial/socio-economic enrichment (census, POI distances, district geometry) is
  deferred — see `src/inmoai_lt/enrichment/README.md`.

## Expected input

Three CSVs with an identical 102-column schema (`utf-8-sig`, one row per listing),
produced by the `real_estate` scraper and never modified by this project:

```
real_estate/data/processed/apartments_sale_vilnius.csv   (3105 rows)
real_estate/data/processed/houses_sale_vilnius.csv        (834 rows)
real_estate/data/processed/apartments_rent_vilnius.csv    (50 rows, disabled)
```

The exact schema is enforced by `inmoai_lt.schema.EXPECTED_RAW_COLUMNS` /
`assert_raw_schema` and fails loudly on drift. Full column-by-column profiling lives in
`docs/DATA_PROFILE.md`.

## Install

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

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
| `vilnius_listings_clean.csv` (+ `.parquet`) | All 3939 retained rows, with every `flag_*` column, `is_valid`, `is_duplicate` |
| `vilnius_listings_analysis.csv` (+ `.parquet`) | `is_valid & ~is_duplicate` subset (3850 rows) — ready for modelling |
| `cleaning_report.json` | Machine-readable run log: source hashes, per-stage row counts, dropped/renamed columns, recovery counts, unmapped values, flag counts, duplicate groups |
| `cleaning_report.md` | Human-readable summary of the same report |
| `unmapped_attributes.csv` | Any `raw_attributes_json` label not recovered or already promoted (empty on this run) |
| `logs/cleaning_<reference_date>.log` | Full run log (UTF-8; console falls back to `backslashreplace` on non-UTF-8 Windows code pages) |

All CSVs are written `encoding="utf-8-sig"`, `index=False`, `lineterminator="\n"`,
sorted by `(property_type, listing_id)`. Two runs on the same input produce
byte-identical files (verified in `tests/test_pipeline.py`).

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
7. Rent listings are excluded from v1 because only 50 rows exist (a partial scrape).
8. `image_count` is a scraper capture artefact (4 for ~99.5% of rows), not a listing
   attribute; retained but not intended as a model feature.

## Deferred functionality

- **Enrichment** (census/socio-economic join, nearest-POI distances, district geometry)
  — see `src/inmoai_lt/enrichment/README.md`. `enrichment.enrich()` raises
  `NotImplementedError`; no enrichment logic exists yet.
- **Rolling price index** (InmoAI's `price_uf_MA_7D` equivalent) — only 4 distinct scrape
  days exist in the current data, so a rolling window would be noise, not signal.
- **Rent listings** — see "Scope" above.

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
- `image_count` is capped at 4 for 3918/3939 rows — a scraper capture limit, not a
  listing property.
- `description_lt` contains `[REDACTED_PHONE]` / `[REDACTED_EMAIL]` markers the scraper
  already applied (525 apartment rows, 172 house rows); this pipeline does not and
  cannot attempt to reverse the redaction.
- Only 4 distinct scrape days exist, so no temporal/price-trend analysis is possible yet.

## Development

```bash
pytest --cov=src/inmoai_lt --cov-report=term-missing   # tests + coverage
ruff check src tests                                     # lint
```

Coverage on `src/inmoai_lt/cleaning/` is ≥ 80% (target from `docs/IMPLEMENTATION_PLAN.md`
§5); see the latest `pytest --cov` output for exact per-module numbers.
