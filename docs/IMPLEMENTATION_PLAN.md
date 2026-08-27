# InmoAI-lt — Implementation Plan

**Status:** planning complete, ready to execute.
**Read first:** `docs/DATA_PROFILE.md` (measured facts about the Vilnius data) and
`docs/SOURCE_ANALYSIS.md` (what to reuse from InmoAI and what to avoid).

Every fact in `DATA_PROFILE.md` was measured from the real CSVs. **Do not re-derive or
contradict those numbers.** If an instruction here conflicts with what you observe when you
run the code, trust the data, fix the code, and record the discrepancy in the final report.

---

## 0. Goal and scope

Build `InmoAI-lt`: a reproducible cleaning pipeline that turns the aruodas.lt Vilnius
scraper output into an analysis-ready dataset.

**In scope (v1):** load → normalise columns → recover data stranded in
`raw_attributes_json` → normalise types/categories/text → handle missing values → detect
duplicates → flag quality problems → derive features → write cleaned outputs + a cleaning
report.

**Out of scope (v1), deferred with hooks:** census enrichment, POI/transport distances,
district geometry, market price index, rental listings, modelling.

**Guiding rule: flag, don't delete.** Only a small set of *fatal* conditions removes a row.
Everything else becomes a boolean flag column plus a counted entry in the report. This is
the "least destructive reasonable default" the brief asks for.

---

## 1. Repository layout

Create at `C:\Users\wn686\OneDrive - Deutsche Börse AG\Desktop\REPOs\InmoAI-lt`
(`docs/` already exists with the two analysis files).

```
InmoAI-lt/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── Makefile
├── config/
│   ├── cleaning.yaml            # sources, thresholds, dedup keys, feature switches
│   └── mappings_lt_en.yaml      # Lithuanian → English controlled vocabulary
├── data/
│   ├── raw/.gitkeep             # snapshot of scraper CSVs (gitignored contents)
│   └── processed/.gitkeep       # pipeline outputs (gitignored contents)
├── logs/.gitkeep
├── scripts/
│   └── ingest_raw.py            # copy scraper CSVs into data/raw/ without touching source
├── src/inmoai_lt/
│   ├── __init__.py
│   ├── __main__.py              # enables `python -m inmoai_lt`
│   ├── cli.py
│   ├── config.py
│   ├── logging_config.py
│   ├── schema.py
│   ├── report.py
│   ├── io.py
│   ├── pipeline.py
│   ├── cleaning/
│   │   ├── __init__.py
│   │   ├── parsers.py           # pure scalar parsers (numbers, areas, dates, years)
│   │   ├── columns.py           # rename / prune / collapse redundant columns
│   │   ├── attributes.py        # raw_attributes_json recovery
│   │   ├── categorical.py       # LT→EN vocabulary, multi-value fields
│   │   ├── features.py          # boolean tri-state from all_features_json
│   │   ├── geo.py               # coordinate validation
│   │   ├── dedup.py
│   │   ├── quality.py           # validity rules → flags + fatal filter
│   │   └── derive.py            # derived/engineered columns
│   └── enrichment/
│       ├── __init__.py          # deferred hooks, documented, not implemented
│       └── README.md
└── tests/
    ├── conftest.py
    ├── fixtures/synthetic_listings.csv
    ├── test_parsers.py
    ├── test_columns.py
    ├── test_attributes.py
    ├── test_categorical.py
    ├── test_features.py
    ├── test_dedup.py
    ├── test_quality.py
    ├── test_derive.py
    ├── test_schema.py
    └── test_pipeline.py
```

Keep every module under ~300 lines. If one grows past that, split it.

**Dependencies (keep minimal):** `pandas`, `pyyaml`, `pyarrow`, `pytest`, `pytest-cov`.
No Docker, no CI, no database, no API, no cloud. Python 3.9+ compatible typing
(`from __future__ import annotations`, `Optional[X]` over `X | None`) — the user's global
preference is 3.9+, and the local interpreter is 3.12, so annotations must not break either.

Use a `venv` and `requirements.txt` per the user's stated preference. `pyproject.toml` is
for package metadata and pytest/ruff config only.

---

## 2. Configuration

### `config/cleaning.yaml`

```yaml
project:
  reference_date_source: max_scrape_timestamp   # NEVER datetime.now() — reproducibility
  random_seed: 0

input:
  encoding: utf-8-sig
  raw_dir: data/raw
  sources:
    - file: apartments_sale_vilnius.csv
      property_type: apartment
      listing_type: sale
      enabled: true
    - file: houses_sale_vilnius.csv
      property_type: house
      listing_type: sale
      enabled: true
    - file: apartments_rent_vilnius.csv
      property_type: apartment
      listing_type: rent
      enabled: false        # only 50 rows, partial scrape — see DATA_PROFILE.md

output:
  dir: data/processed
  clean_basename: vilnius_listings_clean       # all retained rows, with flags
  analysis_basename: vilnius_listings_analysis # is_valid & not duplicate
  write_parquet: true
  float_round: 4

columns:
  drop_all_null: true          # drop only if null across the WHOLE combined dataset
  collapse_redundant: true

dedup:
  # listing_id is the primary key (0 dupes measured). This is the CONTENT key.
  content_key: [property_type, district, street, house_number, total_area_sqm_rounded, rooms, price_eur]
  area_round_dp: 1
  keep: latest_updated        # tie-break: higher views_count, then lower listing_id

quality:
  fatal:                       # these remove the row
    require_non_null: [listing_id, property_type, price_eur, total_area_sqm, latitude, longitude]
    price_eur_min_exclusive: 0
    total_area_sqm_min_exclusive: 0
  flags:                       # these only set a flag column
    price_eur:
      apartment: {min: 10000, max: 7500000}
      house:     {min: 15000, max: 7500000}
    total_area_sqm:
      apartment: {min: 15, max: 1400}
      house:     {min: 20, max: 3000}
    price_per_sqm_eur:
      apartment: {min: 400, max: 12000}
      house:     {min: 400, max: 12000}
    construction_year: {min: 1600, max_offset_from_reference_year: 5}
    rooms: {min: 1, max: 25}
    stale_listing_age_days: 730
    plot_area_sqm_min_exclusive: 0    # houses only
  vilnius_bbox: {lat_min: 54.50, lat_max: 54.90, lon_min: 24.95, lon_max: 25.55}
  lithuania_bbox: {lat_min: 53.8, lat_max: 56.5, lon_min: 20.8, lon_max: 26.9}

derive:
  enabled: true
```

Threshold provenance (state this as a comment in the YAML): every bound is a **loose
envelope around the measured Vilnius distribution** in `DATA_PROFILE.md`, chosen to catch
only the clear tail. None is copied from InmoAI. They set flags, never delete.

### `config/mappings_lt_en.yaml`

Controlled vocabulary. **Lookup must be case-insensitive and whitespace-trimmed**, because
the source lowercases second-and-later tokens in multi-value fields
(`"Centrinis, dujinis"`). English values must map to themselves (identity/passthrough),
because the scraper already translated some values — the columns are mixed-language.

```yaml
building_type:          # from `Pastato tipas`
  mūrinis: brick
  blokinis: concrete_block
  monolitinis: monolithic
  medinis: wood
  rąstinis: log
  karkasinis: frame
  skydinis: panel
  kita: other
  # passthrough of already-translated values
  brick: brick
  concrete_block: concrete_block
  monolithic: monolithic
  wood: wood

condition:              # from `Įrengimas`
  įrengtas: fully_finished
  "dalinė apdaila": partially_finished
  neįrengtas: unfinished
  "nebaigtas statyti": under_construction
  pamatai: foundation_only
  "reikalingas remontas": renovation_required
  kita: other
  fully_finished: fully_finished
  partially_finished: partially_finished
  unfinished: unfinished
  renovation_required: renovation_required

house_type:             # from `Namo tipas`
  "namas (gyvenamasis)": detached_house
  "sublokuotas namas": semi_detached
  "kotedžas": townhouse
  "sodo namas": garden_house
  "namo dalis": house_share
  "sodyba": homestead
  "kita (nukeliamas, projektas, kt.)": other
  detached_house: detached_house
  terraced_house: semi_detached      # scraper's label for `Sublokuotas namas`
  townhouse: townhouse

heating_type:           # from `Šildymas` — MULTI-VALUED, comma separated
  centrinis: central
  "centrinis kolektorinis": central_collector
  dujinis: gas
  elektra: electric
  aeroterminis: air_source_heat_pump
  geoterminis: geothermal
  "kietu kuru": solid_fuel
  "skystu kuru": liquid_fuel
  "saulės energija": solar
  krosninis: stove
  kita: other

water_supply:           # from `Vanduo` — MULTI-VALUED
  "miesto vandentiekis": city_water
  "vietinis vandentiekis": local_water
  "artezinis gręžinys": artesian_well
  "šulinys": well
  kita: other

water_body:             # from `Artimiausias vandens telkinys`
  "ežeras": lake
  "upė": river
  tvenkinys: pond
  "jūra": sea
  marios: lagoon

orientation:            # from `Langų orientacija` — MULTI-VALUED, order NOT canonical
  "šiaurė": north
  "pietūs": south
  rytai: east
  vakarai: west

object_type:            # from `Objektas` — non-standard objects
  "buto dalis": apartment_share
  "patalpa, poilsio paskirtis": recreational_premises
  "patalpa, viešbučių paskirtis": hotel_premises
```

`district`, `street`, `energy_class` are **not** translated. Lithuanian place names stay
verbatim.

**Unmapped values must never be silently dropped.** Any value not in the table is kept
as-is (with diacritics), and recorded in the report under `unmapped_category_values` with
its column, value and count.

---

## 3. Pipeline stages

`pipeline.py` runs these in order. Each stage takes `(df, ctx)` and returns a **new**
DataFrame; `ctx` carries config, the report accumulator and the logger. No `inplace=True`.

### Stage 1 — load (`io.py`)
- Read each enabled source with `encoding="utf-8-sig"`, `dtype=str` for the JSON columns.
- Add `source_file` column.
- Assert the 102-column schema matches `schema.EXPECTED_RAW_COLUMNS`; on mismatch, log the
  symmetric difference and fail loudly (this is a real schema drift signal, not noise).
- Concatenate apartments + houses into one long table. Record per-source row counts.
- Compute `reference_date` = max of `scrape_timestamp_utc` across all rows; store in the
  report. **All age/recency maths uses this, not the wall clock.**

### Stage 2 — column normalisation (`columns.py`)
- Column names are already snake_case; run `to_snake_case` anyway for idempotence and to
  guard against schema drift. Record any renames.
- **Drop all-null columns**, evaluated on the *combined* table so that
  `plot_area_sqm` (houses only) and `floor` (apartments only) survive. Record the dropped
  list. Expect ~36 drops — see `DATA_PROFILE.md`.
- **Collapse redundant columns** (record each):
  - `municipality` → drop (== `city`)
  - `local_area`, `neighbourhood` → drop, keep `district`. Before dropping, verify equality
    and log the 1–6 house rows where they differ; prefer `neighbourhood` when `district` is null.
  - `canonical_url` → drop (== `listing_url`)
  - `apartment_total_area_sqm`, `house_total_area_sqm` → drop (== `total_area_sqm`)
  - `number_of_floors` → drop (== `total_floors` for houses)
  - `plot_area_ares` → drop (== `plot_area_sqm / 100`)
- Drop single-valued constants but **keep the value in the report**: `country`,
  `currency`, `listing_status`, `record_source`, `coordinate_source`, `city`.
  Keep `property_type` and `listing_type` (they vary).

### Stage 3 — attribute recovery (`attributes.py`) — highest value
Parse `raw_attributes_json` per row and recover what the scraper stranded.

1. **`Metai` → construction + renovation year.**
   Format is either `"2013"` or `"1960 statyba, 2026 renovacija"`.
   Extract with a regex over labelled year tokens:
   - `(\d{4})\s*statyba` → `construction_year_recovered`
   - `(\d{4})\s*renovacija` → `renovation_year`
   - a bare `^\s*(\d{4})\s*$` → `construction_year_recovered`
   Set `construction_year` from the recovered value; **assert it equals the existing
   `construction_year` column** where both exist and log mismatches (expected: 0).
   Add `has_renovation` (bool). Expect **355 renovation years recovered** (277 apt + 78 house).
2. **`Langų orientacija` → orientation.**
   Split on `,`, casefold, strip, map via `orientation` vocabulary. Produce:
   - `orientation_north/south/east/west` (bool, NA when the label is absent)
   - `orientation_count` (int, NA when absent)
   - `window_orientation` (canonical, **sorted alphabetically**: `"east,north"` — this
     fixes the non-canonical token order measured in the data)
   Expect 1594 apartments populated, 0 houses.
3. **`Namo numeris` → `house_number`** (string, preserve `8A`, `9E`). Expect 2239 + 452.
4. **`Unikalus daikto numeris (RC numeris)` → `cadastral_id`** (string). Expect 140.
5. **`Objektas` → `object_type_lt` + `object_type`** (mapped) + flag
   `is_non_standard_object`. Expect 22 apartments.
6. **`Artimiausias vandens telkinys` → `water_body_lt` + `water_body`** (mapped, houses).
   Expect 157.
7. **`Iki vandens telkinio (m)` → `distance_to_water_m`** (float). **Must handle the space
   thousands separator** (`"1 000"`, `"3 800"`) and NBSP. Expect 120.
8. Any raw label **not** consumed above and **not** already a promoted column goes into
   `unmapped_attributes` in the report (label, count, sample value, sample URL) and is
   written to `data/processed/unmapped_attributes.csv`. This is the forward-compatibility
   hook: a future scrape with new labels surfaces here instead of being lost.
9. Drop `raw_attributes_json` from the output **only after** recovery, and record that the
   full blob is preserved in `data/raw/` (source is never modified).

### Stage 4 — type & value normalisation (`parsers.py`, `categorical.py`)
- **Numeric parser** (`parse_decimal`): handle `,` decimal separator, space / NBSP / thin
  space thousands separators, unit suffixes (`m²`, `a`, `ha`, `€`). Return `None` on
  failure — never fabricate `0`. This is the InmoAI `convert_to_numeric` idea, corrected.
  The scraper already parsed most numerics; this parser is for the recovered raw values and
  as a defensive re-parse.
- **Integer coercion**: `rooms`, `floor`, `total_floors`, `construction_year`,
  `renovation_year`, `views_count`, `saved_by_users_count`, `image_count`,
  `source_page_number`, `search_position`, `listing_age_days` → pandas nullable `Int64`
  (so missing values survive without becoming floats).
- **Dates**: `listing_created_date`, `listing_updated_date` → `datetime64[ns]` (date only).
  `scrape_timestamp_utc` → tz-aware UTC datetime.
- **Categoricals**: apply the vocabulary to `building_type`, `condition`, `house_type`,
  `object_type`, `water_body`. Case-insensitive lookup on a diacritic-preserving key.
  Keep the original in `<col>_raw` **only** where the mapping changed the value, so nothing
  is lost. Record unmapped values.
- **Multi-value fields** (`heating_type`, `water_supply`):
  - split on `,`, trim, casefold, map each token
  - `heating_types` = sorted, comma-joined English tokens (canonical)
  - `heating_type_count` (int)
  - one boolean per known token: `heating_central`, `heating_central_collector`,
    `heating_gas`, `heating_electric`, `heating_air_source_heat_pump`,
    `heating_geothermal`, `heating_solid_fuel`, `heating_liquid_fuel`, `heating_solar`,
    `heating_stove`, `heating_other`
  - same pattern → `water_supply_types`, `water_city`, `water_local`, `water_artesian_well`,
    `water_well`, `water_other`
  This collapses 43/58 pseudo-categories into usable features.
- **Text**: collapse whitespace, NBSP → space, strip, empty → NA, and apply
  **Unicode NFC** normalisation. **Never strip Lithuanian diacritics from stored values.**
  A separate `fold_key()` helper (NFKD + strip combining marks + casefold) exists *only*
  for building match keys and must not be written to output.
- **JSON columns**: parse `image_urls`, `security_features`, `diagnostic_warnings`,
  `all_features_json`. Replace `security_features` with the mapped English list and a count.

### Stage 5 — boolean features (`features.py`) — tri-state rule
`all_features_json` only ever contains `True`. Absence is ambiguous.

**Rule:** for each feature key and each `property_type`, if that key appears at least once
for that property type, then `NaN → False` (the feature is captured for this type, so
absence means "not present"). If the key **never** appears for that property type, leave
`NA` — the source does not capture it, and writing `False` would fabricate data.

Measured consequence (assert this in the pipeline and log it):
- apartment: `balcony, basement, storage, terrace, alarm, security_cameras` → filled False;
  `garage, lift, fenced_area, paved_access` → all NA
- house: `garage, basement, terrace, alarm, security_cameras, fenced_area, paved_access`
  → filled False; `balcony, storage, lift` → all NA

Emit `feature_coverage` in the report: per property_type, which features are captured vs
structurally absent. Add `dtype="boolean"` (pandas nullable) so NA survives.

### Stage 6 — geography (`geo.py`)
- Flag `coords_outside_lithuania` (bbox from config; expect 0).
- Flag `coords_outside_vilnius` (bbox from config; expect ~0 — measured range is
  54.574–54.823 / 25.052–25.466).
- Flag `coords_approximate` from `coordinate_precision == "approximate"` (expect 234 + 138),
  then drop `coordinate_precision`.
- Round `latitude`/`longitude` to 6 dp for determinism.
- Do **not** geocode, reverse-geocode, or join any external geography. That is deferred.

### Stage 7 — duplicates (`dedup.py`)
Two tiers, both counted, neither destructive in the main output.

- **Tier 1 — identity.** Duplicate `listing_id` → keep first, drop the rest (measured: 0;
  this is a defensive guard for future multi-run inputs). Report the count.
- **Tier 2 — content.** Build the key from config:
  `(property_type, district, street, house_number, round(total_area_sqm, 1), rooms, price_eur)`.
  Rows where any key part is NA are **never** grouped (NA never equals NA).
  For groups of size > 1: assign `duplicate_group_id`, mark exactly one row
  `is_duplicate_primary=True` (latest `listing_updated_date`; tie → higher `views_count`;
  tie → lower `listing_id`), the rest `is_duplicate=True`.
  **Keep all rows in the clean output.** The analysis output keeps only primaries.

Rationale to state in the README: `full_address` is street-level only, so an address-only
key would merge genuinely different flats. Including the recovered `house_number` plus area,
rooms and price makes the key defensible. Measured baseline for comparison: 48 apartment /
21 house exact `address+price+area+rooms` duplicates.

### Stage 8 — quality flags & fatal filter (`quality.py`)
Compute flags first, then apply the fatal filter, so the report can show what was removed.

Flag columns (all `boolean`, prefix `flag_`):

| Flag | Rule |
|---|---|
| `flag_price_out_of_range` | outside per-type price bounds |
| `flag_area_out_of_range` | outside per-type area bounds |
| `flag_price_per_sqm_out_of_range` | outside bounds |
| `flag_price_per_sqm_inconsistent` | `abs(price/area − price_per_sqm) > 1` (measured: 0) |
| `flag_construction_year_out_of_range` | `< 1600` or `> reference_year + 5` |
| `flag_rooms_out_of_range` | outside bounds |
| `flag_floor_gt_total_floors` | apartments (measured: 0) |
| `flag_plot_area_zero` | houses with `plot_area_sqm <= 0` (measured: 10, `"0 a"`) |
| `flag_non_standard_object` | `Objektas` present (measured: 22) |
| `flag_not_habitable` | `condition in {foundation_only, under_construction}` (measured: 10) |
| `flag_coords_outside_vilnius` / `flag_coords_outside_lithuania` | from Stage 6 |
| `flag_coords_approximate` | from Stage 6 |
| `flag_stale_listing` | `listing_age_days > 730` |
| `flag_description_redacted` | description contains `[REDACTED_` (measured: 525) |
| `flag_missing_description` | `description_lt` is NA (measured: 13 apt + 5 house) |
| `flag_duplicate` | from Stage 7 |

Then:
- `quality_flag_count` = number of true flags
- `quality_flags` = sorted comma-joined names of true flags (human-readable audit trail)
- `is_valid` = no flag in the configured `blocking_flags` set. Default blocking set:
  `{price_out_of_range, area_out_of_range, price_per_sqm_out_of_range,
  construction_year_out_of_range, coords_outside_vilnius, non_standard_object,
  not_habitable}`. Advisory flags (approximate coords, stale, redacted, duplicate) do
  **not** clear `is_valid`.

**Fatal filter** (the only rows actually removed): null `listing_id`, `property_type`,
`price_eur`, `total_area_sqm`, `latitude` or `longitude`; or `price_eur <= 0`; or
`total_area_sqm <= 0`. Expected removals: **0** on current data. Log each removal with its
`listing_id` and reason.

### Stage 9 — derived features (`derive.py`)
Generic, defensible, all reproducible from `reference_date`:

| Column | Formula |
|---|---|
| `price_per_sqm_eur` | keep source value (verified identical to `price/area`) |
| `building_age_years` | `reference_year − construction_year`, clipped at ≥ 0 (new builds dated ahead → 0) |
| `effective_year` | `max(construction_year, renovation_year)` |
| `years_since_renovation` | `reference_year − renovation_year` where present |
| `is_new_build` | `construction_year >= reference_year` |
| `floor_ratio` | `floor / total_floors` (apartments; NA when `total_floors` is 0/NA) |
| `is_ground_floor` | `floor == 0` |
| `is_top_floor` | `floor == total_floors` |
| `area_per_room` | `total_area_sqm / rooms` (NA when `rooms` is 0/NA) |
| `plot_to_building_ratio` | `plot_area_sqm / total_area_sqm` (houses, NA when plot ≤ 0) |
| `has_water_body_nearby` | `water_body` not NA |
| `days_since_update` | `reference_date − listing_updated_date` in days |
| `orientation_*` | from Stage 3 |
| `security_feature_count` | length of the mapped security list |

**Not implemented, documented as deferred:** rolling price index / relative price
(`price_uf_MA_7D` equivalent) — only 4 distinct scrape days exist, so it would be noise.

### Stage 10 — output (`io.py`, `schema.py`, `report.py`)
- Enforce the final column order from `schema.FINAL_COLUMN_ORDER` (explicit list, grouped:
  identity → location → price → property → condition/systems → features → flags → derived →
  provenance). Fail if a column is present but unlisted — this forces the schema to stay
  intentional.
- Round floats to `float_round`.
- **Sort by `(property_type, listing_id)`** for determinism.
- Write:
  - `data/processed/vilnius_listings_clean.csv` (+ `.parquet`) — all retained rows
  - `data/processed/vilnius_listings_analysis.csv` (+ `.parquet`) —
    `is_valid & ~is_duplicate`
  - `data/processed/cleaning_report.json` — `sort_keys=True`, stable
  - `data/processed/cleaning_report.md` — human-readable
  - `data/processed/unmapped_attributes.csv`
  - `logs/cleaning_<reference_date>.log`
- CSV: `encoding="utf-8-sig"`, `index=False`, `lineterminator="\n"`.

### Report contents (`report.py`)
An accumulator object with an ordered event log, serialised to JSON + Markdown:

- run metadata: reference_date, config hash, source files with row counts and SHA-256
- per-stage row counts in/out and the delta
- columns: dropped (with reason: all-null / redundant / constant), renamed, created
- missing values per column **before and after** cleaning (count and %)
- duplicates: tier 1 count, tier 2 group count, rows marked duplicate
- flags: count per flag rule
- fatal removals: count per reason, with `listing_id` list
- recovered attributes: count per recovered field
- unmapped category values: column → value → count
- unmapped raw attribute labels: label → count → sample
- feature coverage matrix per property type
- final row/column counts for both outputs

---

## 4. CLI

```bash
python -m inmoai_lt clean                        # uses config/cleaning.yaml
python -m inmoai_lt clean --config path.yaml --raw-dir data/raw --out-dir data/processed
python -m inmoai_lt profile                      # optional: print a schema/missingness summary
python scripts/ingest_raw.py --source "<real_estate>/data/processed"   # copy, never modify
```

`Makefile`: `install`, `ingest`, `clean-data`, `test`, `lint`.

---

## 5. Tests

Synthetic fixtures only — never write synthetic rows into `data/processed/`.
Target ≥ 80% coverage on `src/inmoai_lt/cleaning/`.

| File | Must cover |
|---|---|
| `test_parsers.py` | `"54,02 m²"→54.02`; `"1 000"→1000.0`; NBSP thousands; `"2,6 a"→2.6`; `"0 a"→0.0`; garbage → `None` (not 0); ISO date parse; `Int64` nullable coercion |
| `test_columns.py` | snake_case idempotence; all-null drop evaluated on the combined frame (a column null for apartments but populated for houses is **kept**); redundant collapse; every drop is recorded |
| `test_attributes.py` | `"1960 statyba, 2026 renovacija"` → (1960, 2026); `"2013"` → (2013, None); orientation `"Pietūs, šiaurė"` and `"Šiaurė, pietūs"` both → `"north,south"` with the same booleans; `house_number` `"8A"` stays a string; `"1 000"` distance; unknown label lands in `unmapped_attributes` |
| `test_categorical.py` | case-insensitive lookup (`"dujinis"` == `"Dujinis"`); English passthrough (`"brick"` → `"brick"`); unmapped value preserved verbatim **with diacritics** and recorded; multi-value split `"Centrinis, dujinis"` → `["central","gas"]`, canonical sorted string, correct booleans |
| `test_features.py` | tri-state: feature seen for the type → NaN becomes False; feature never seen for the type → stays NA; dtype is nullable `boolean` |
| `test_dedup.py` | exact content dupes grouped; NA in a key part prevents grouping; `keep=latest_updated` picks the right primary; tie-breaks by views then listing_id; no rows deleted from the clean output |
| `test_quality.py` | each flag fires on a crafted row and not on a clean one; `is_valid` ignores advisory flags; fatal filter removes a zero-price row and logs the reason; `quality_flags` string is sorted |
| `test_derive.py` | `building_age_years` uses `reference_date`, not `datetime.now()` (freeze a reference date and assert an exact value); age clipped at 0 for a 2028 build; `area_per_room` NA when rooms is 0 |
| `test_schema.py` | final column order enforced; unexpected column raises; raw schema mismatch raises with a useful message |
| `test_pipeline.py` | **reproducibility**: run twice on the same fixture → byte-identical CSV and identical report JSON (excluding a timestamp field, if any); Lithuanian text (`Žirmūnai`, `Šiaurė`, `ąčęėįšųūž`) survives a full round-trip through read → clean → write → read |

---

## 6. Execution order

1. Scaffold the repo (`pyproject.toml`, `requirements.txt`, `.gitignore`, `Makefile`,
   package skeleton, `config/*.yaml`). `git init`.
2. Create the venv, install deps.
3. `python scripts/ingest_raw.py` — copy the three CSVs into `data/raw/`.
   **Never write to the `real_estate` repo.**
4. Implement bottom-up: `parsers` → `columns` → `attributes` → `categorical` → `features`
   → `geo` → `dedup` → `quality` → `derive` → `schema`/`report`/`io` → `pipeline` → `cli`.
   Write each module's tests alongside it.
5. Run the pipeline on the real data.
6. Run `pytest --cov`.
7. **Verify against the measured expectations** below. Any mismatch is a bug in the new
   code, not a data surprise — investigate before proceeding.
8. Inspect the cleaned CSV and the report by hand (open the CSV, check Lithuanian
   characters render, check flag counts are sane).
9. Write the README from what was actually built.

### Verification checklist (measured expectations)

| Check | Expected |
|---|---|
| Input rows | 3105 + 834 = **3939** |
| Fatal removals | **0** |
| Rows in clean output | **3939** |
| `renovation_year` non-null | **355** (277 apt + 78 house) |
| `window_orientation` non-null | **1594** (apartments only) |
| `house_number` non-null | **2691** (2239 + 452) |
| `cadastral_id` non-null | **140** (103 + 37) |
| `water_body` non-null | **157** (houses) |
| `distance_to_water_m` non-null | **120** (houses) |
| `flag_non_standard_object` | **22** |
| `flag_plot_area_zero` | **10** |
| `flag_price_per_sqm_inconsistent` | **0** |
| `flag_floor_gt_total_floors` | **0** |
| `flag_coords_outside_lithuania` | **0** |
| `flag_coords_approximate` | **372** (234 + 138) |
| `flag_description_redacted` | **525** (apartments) |
| Columns dropped as all-null | ~**36** |
| Unmapped category values | should be **0** if the vocabulary in §2 is complete |
| Two consecutive runs | byte-identical outputs |

---

## 7. Documentation to produce

`README.md` — purpose; relationship to InmoAI (reuse/adapt/exclude summary, link to
`docs/SOURCE_ANALYSIS.md`); current scope; expected input (schema + where it comes from);
install (`venv` + `requirements.txt`); how to run; outputs produced; **assumptions**;
**deferred functionality**. Write it *after* the code works, describing what exists.

`src/inmoai_lt/enrichment/README.md` — the deferred hooks and their intended signatures:

```python
def enrich(df: pd.DataFrame, *, lat_col: str = "latitude", lon_col: str = "longitude") -> pd.DataFrame: ...
```
covering: census/socio-economic join, nearest-POI distances, district geometry. State the
data each needs and why it is not implemented.

### Assumptions to state explicitly in the README

1. `raw_attributes_json` is the authoritative source for attributes the scraper did not
   promote; recovering from it is preferred over re-scraping.
2. `Metai`'s `statyba`/`renovacija` split means construction / renovation year. Verified
   against 355 rows; `construction_year` from the recovery matches the scraper's value.
3. Absence of a feature key in `all_features_json` means "not advertised", treated as
   `False` only when the feature is captured for that property type (tri-state rule).
4. Bounds in `cleaning.yaml` are calibrated envelopes around the observed Vilnius
   distribution and set flags only — they never delete rows.
5. `reference_date` comes from the data's own max scrape timestamp, so output does not
   change with the wall clock.
6. Lithuanian diacritics are semantically meaningful and are preserved everywhere in
   output; folding is used only for internal lookup keys.
7. Rent listings are excluded from v1 because only 50 rows exist (a partial scrape).
8. `image_count` is a scraper capture artefact (4 for 99.5% of rows), not a listing
   attribute; retained but not used as a feature.

### Known data-quality issues to surface in the README

- 36 columns are structurally empty in the current scrape (`bedrooms`, `bathrooms`,
  `living_area_sqm`, `usable_area_sqm`, `ownership_type`, `seller_type`, `agency_name`,
  price-change fields…). These are scraper gaps, not cleaning gaps — fixing them belongs in
  `real_estate`, and the pipeline will pick them up automatically once populated.
- `lift` is never captured for apartments — a notable omission for price modelling, and a
  concrete feature request for the scraper.
- `full_address` lacks a house number; `Namo numeris` covers only 72% of apartments and 54%
  of houses, so the duplicate key is imperfect for the remainder.
- `heating_type`/`water_supply` token casing is inconsistent in the source
  (`"Centrinis, dujinis"`); handled here, but worth fixing upstream.
- `image_count` is capped at 4.
- Only 4 scrape days exist, so no temporal analysis is possible yet.
