# AGENTS.md
_Last reconciled: 2026-08-30_

## Overview
- Reproducible cleaning pipeline for aruodas.lt Vilnius real-estate listings (apartment/house × sale/rent = 4 segments); turns raw scraper CSVs into analysis-ready CSV/Parquet plus a full audit trail, never mutating source data.
- On top of it, a modelling layer (`src/inmoai_lt/modeling/`, driven from `notebooks/`) trains one price model per segment and cross-predicts rent onto sale listings to estimate gross cap rates.
- Lithuanian sibling of the Chilean **InmoAI** pipeline (concept reuse, not a fork); no thresholds/vocab/column names copied — all bounds calibrated to Vilnius (`docs/DATA_PROFILE.md`).

## Architecture
- Package `src/inmoai_lt` (src layout, package name `inmoai-lt`). Entry: `python -m inmoai_lt {clean,profile}` → `__main__.py` → `cli.py`.
- `pipeline.run_pipeline(ctx)` runs 10 ordered stages; every stage returns a NEW DataFrame (no `inplace=True`).
- Stages: load → column normalisation (`cleaning/columns.py`) → attribute recovery (`cleaning/attributes.py`) → type/value normalisation (`_normalize_types_and_categories`, `cleaning/categorical.py`+`parsers.py`) → boolean features (`cleaning/features.py`) → geography (`cleaning/geo.py`) → duplicates (`cleaning/dedup.py`) → quality flags + fatal filter (`cleaning/quality.py`) → derived features (`cleaning/derive.py`) → output (`io.py`).
- `config.py`: `load_config()` reads `config/cleaning.yaml` + `config/mappings_lt_en.yaml` into frozen `PipelineConfig`; `config_hash` = first 16 hex of sha256 over both YAMLs.
- `schema.py`: `EXPECTED_RAW_COLUMNS` (102 cols, asserted) via `assert_raw_schema`; `FINAL_COLUMN_ORDER` enforced at write by `enforce_final_column_order` (raises on unlisted produced columns).
- `report.py` (`CleaningReport`) accumulates run log → `cleaning_report.{json,md,html}`. HTML via `html_report.py`; per-segment distribution report `analysis_report.html` via `analysis_report.py` (uses `figures.py`, `stats.py`, `district_filter.py`, inlined plotly.js).
- `enrichment/` is a deferred hook: `enrich()` raises `NotImplementedError`, never called by the pipeline.
- `scripts/ingest_raw.py` copies the scraper CSVs into `data/raw/` (read-only source, never writes back).
- `modeling/` (separate from the pipeline; reads `segments/*_analysis.csv`, writes `models/*.joblib`; methodology and reasoning in `docs/MODELS.md`): `config.py` (`ModelConfig` from `config/modeling.yaml`) → `features.py` (feature lists keyed by **property_type**, not listing_type) → `dataset.py` → `transformers.py` + `estimator.py` (`StackingRegressor`: haversine-KNN neighbour price-per-sqm base learner under a `CatBoostRegressor`, `passthrough=True`) → `model.py` (`SegmentModel.train/predict/evaluate/save/load`, `train_all`) → `investment.py` (`estimate_cap_rate`). Ported from `InmoAI/models/pipeline_classes.py`.

## Build & run
- Install: `pip install -r requirements.txt` (or `make install`). Deps: pandas>=2, numpy, scipy, pyyaml, pyarrow, plotly, pytest, pytest-cov; modelling adds scikit-learn>=1.9, catboost, joblib, ipykernel. Python >=3.9. CLI is stdlib argparse only.
- Ingest: `python scripts/ingest_raw.py --source "<real_estate>/data/processed"` (or `make ingest`).
- Run: `python -m inmoai_lt clean [--config --mappings --raw-dir --out-dir]` (or `make clean-data`); summary: `python -m inmoai_lt profile` (fails gracefully if no prior clean output).
- Test/lint: `pytest --cov=src/inmoai_lt --cov-report=term-missing` (or `make test`); `ruff check src tests` (or `make lint`). ruff line-length 100, target py39, rules E/F/I/UP.

## Conventions
- Segment = `<property_type>_<listing_type>`: `apartment_sale` (3036 analysis rows), `apartment_rent` (1629), `house_sale` (814), `house_rent` (96). ALL price/area/EUR-per-sqm bounds keyed by segment, never `property_type` alone (rent is EUR/month regime).
- "Flag, don't delete": only `quality.fatal` rules remove rows (null listing_id/property_type/price_eur/total_area_sqm, or non-positive price/area). All `flag_*` columns are advisory. `blocking_flags` in config drive `is_valid`.
- Outputs in `data/processed/`: `vilnius_listings_clean.{csv,parquet}` (all retained + flags), `vilnius_listings_analysis.{csv,parquet}` (`is_valid & ~is_duplicate`), `segments/<segment>_analysis.{csv,parquet}` (partition the analysis file exactly). Plus `cleaning_report.{json,md,html}`, `analysis_report.html`, `unmapped_attributes.csv`, `logs/cleaning_<reference_date>.log`.
- All CSVs: `utf-8-sig`, `index=False`, `lineterminator="\n"`, sorted by `(property_type, listing_id)` → byte-identical across runs (asserted in `tests/test_pipeline.py`).
- `reference_date` = max `scrape_timestamp_utc` in data, NEVER wall clock; drives log filename and construction-year/age bounds. cli configures logging with this before running the pipeline (does a cheap preview load to learn the date).
- Lithuanian diacritics preserved in all output values; `parsers.fold_key()` folds them only for internal lookup keys. `to_snake_case` normalises column names only.
- Config bounds are calibrated envelopes around observed Vilnius distribution.
- Tests use synthetic fixtures + `_FakeReport`; each cleaning module has a matching `tests/test_*.py`, and the modelling layer has `tests/test_modeling_*.py` (synthetic segment frames from the `make_segment_frame` / `fast_config` fixtures — never trains on the real data).

## Gotchas / notes
- `write_unmapped_attributes` always writes (header-only when empty) so future scrapes surface new labels automatically.
- `security_features` kept verbatim in Lithuanian (no controlled vocab) — translating would violate the "don't fabricate" rule; `security_feature_count` added in derive.
- Water-supply canonical tokens are `city_water`/`local_water` but boolean columns are `water_city`/`water_local` via `_WATER_SUPPLY_TOKEN_SUFFIXES` remap in pipeline.
- Known scrape gaps (source-side, not cleaning bugs): 39 structurally-empty columns; `lift` never captured; `description_lt` has scraper-applied `[REDACTED_PHONE/EMAIL]`; only 7 distinct scrape days (no rolling price index); `house_rent` has just 96 rows, so its model is flagged `low_n` and anything derived from it carries `low_confidence`.
- All four sources are 100% geocoded today; `flag_missing_coordinates` is advisory and currently fires on nothing.
- Modelling deviations from the reference notebook, all deliberate: `Lasso(alpha=10.394)` feature selection dropped (alpha was fitted on Chilean UF prices, and CatBoost selects internally); no `StandardScaler` (trees are scale-invariant); stock `StackingRegressor` instead of `PandasStackingRegressor` (the matrix is fully numeric after target encoding).
- Deferred: enrichment (census/POI/geometry), rolling price index, geocoding.
- README documents a `dbx-llm`/Databricks CLI AI-tool setup unrelated to the pipeline; the `databricks-cli` auth requires the `databricks` exe on the PATH the Python process inherited at startup.
