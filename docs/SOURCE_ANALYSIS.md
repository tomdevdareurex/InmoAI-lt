# InmoAI (Santiago) → InmoAI-lt (Vilnius): reuse analysis

Source inspected: `InmoAI/pre_processing/` (8 notebooks + 3 scripts + `utils.py`),
with supporting context from `InmoAI/data_static_cleansing/` and `InmoAI/configuration/`.

## What InmoAI's pipeline does

| Stage | Reads | Writes | Purpose |
|---|---|---|---|
| `a_0_fixed_date_pub.ipynb` | raw scrape `.xlsx` | `*_main.xlsx` | Parse Spanish relative dates (`"Publicado hace 3 meses"`) into day offsets |
| `a_post_processing.ipynb` | `*_main.xlsx` | `df_clean_*.parquet` | **Core cleaning**: numeric coercion, drop null prices, dedup, surface/bed/bath backfill, orientation, comuna extraction |
| `b_closest_block.py` | clean parquet + `censo_2017_manzanas_RM_1.xlsx` | block mapping `.csv` | Nearest census block by Haversine (multiprocessing) |
| `c_merge_*.ipynb` | clean + block map | `df_clean_censo_*.parquet` | Join ~130 census columns |
| `d_closest_barrio.py` | + `barrio_comuna_clean.csv` | barrio mapping `.csv` | Nearest neighbourhood by Haversine |
| `e_merge_*.ipynb` | + barrio map | `df_clean_censo_barrio_*.parquet` | Join barrio, snake_case all columns, strip accents |
| `f_subway_pimb.py` | + `subway_lat_lng.csv` | subway mapping `.csv` | Nearest metro station + distance |
| `g_merge_*.ipynb` | + subway map | `df_clean_censo_barrio_ss_*.parquet` | Fill missing metro distance per comuna; 0–3 proximity rating |
| `h_pimb_data_preparation.ipynb` | previous | final parquet | Age from year, price/m², 7-day rolling price index, correlation pruning, final filters |

## Reuse decision matrix

### Directly reusable (concept and structure)

| InmoAI element | How it carries over |
|---|---|
| Staged pipeline with an explicit order and a persisted artifact per stage | Keep the staged idea, but as ordered in-process functions with one report, not 9 files |
| `convert_to_numeric` — comma-vs-dot decimal handling | Same problem in Lithuanian (`54,02 m²`), plus space thousands separators (`1 000`) |
| `to_snake_case` for column names | Same, but must **not** strip Lithuanian diacritics from *values* |
| Drop rows with no price | Same fatal rule |
| `drop_duplicates` early, then a keyed dedup | Same two-tier idea, with a justified key |
| Backfill an area column from an alternative area column | Same pattern, different column names |
| Fill missing categorical with an explicit `"unknown"` sentinel rather than dropping | Same principle |
| Age from construction year (`current_year − year_built`) | Same formula, but use a fixed reference date for reproducibility |
| Price per m² as the core normalised value | Same |
| Bounds-based outlier filtering, with **different bounds per property type** | Same design; bounds re-derived from Vilnius data, never copied |
| Correlation check before modelling | Deferred to the analysis phase, not part of cleaning |

### Reusable with adaptation

| InmoAI element | Adaptation required |
|---|---|
| Relative-date parser (`calculate_new_date_pub`) | **Not needed.** aruodas gives real ISO dates (`listing_created_date`). Delete, don't port. |
| `replace_characters_df` (accent stripping) | **Invert the intent.** InmoAI strips `ñ→n`, `é→e` from values. For Lithuanian this would destroy meaning (`Šiaurė`≠`Siaure`, `Žirmūnai`≠`Zirmunai`). Apply diacritic folding **only** to internal match keys, never to stored values. |
| Orientation cleaning (space/slash → hyphen on Spanish cardinals) | Replace with a Lithuanian token parser producing an unordered set of N/S/E/W, because token order is inconsistent in the source. |
| Currency normalisation (CLP/USD → UF via central-bank rates) | **Not needed.** All prices are already EUR. No conversion, no external rate API. |
| Per-type numeric bounds (apartment 20–2000 m², house 20–8000 m², price 5–30000 UF …) | Structure kept; **all numbers re-derived from the Vilnius distributions**. Chilean values are meaningless here. |
| Boolean/flag columns | InmoAI has 0/1 ints. Vilnius has `True`/`NaN` with no explicit `False` — needs a tri-state rule (see plan). |
| Haversine nearest-POI join (block / barrio / subway) | Generic and genuinely useful; but there is **no POI dataset for Vilnius** in scope. Keep the *interface* as a deferred enrichment hook, implement nothing. |

### Chile-specific — excluded outright

- `location_parser()` — hard-coded dictionary of 50+ Santiago comunas.
- `get_comuna()` — parses `"… , RM"` / `"… , Metropolitana"` out of Chilean addresses.
- `get_mlc_number()` — extracts MercadoLibre Chile `MLC-` listing IDs.
- Census (CENSO 2017 manzanas, SEG 2012 socio-economic tiers) join and its ~130 columns.
- `barrio_comuna_clean.csv` barrio reference and the barrio Haversine join.
- Santiago Metro station file and the subway proximity rating (including the
  "imaginary station 30 km away" imputation for comunas with no metro).
- UF / CLP / USD conversion and the BCCH central-bank rate API.
- Spanish relative-date vocabulary (`hoy`, `esta semana`, `días`, `meses`, `años`).
- Spanish accent-stripping replacement table.

Vilnius equivalents (district / seniūnija, Lithuanian census, public transport stops) are
**not available in this repository's scope**, so they are deferred, not reimplemented.

### Deferred until more Lithuanian data exists

| Deferred | Blocked on | Interface preserved |
|---|---|---|
| Census / socio-economic enrichment | Lithuanian Statistics Dept. data at a spatial unit | `enrichment/` hook taking `(df, lat_col, lon_col) -> df` |
| Nearest-POI distances (transport, schools, shops) | A Vilnius POI dataset | same hook signature |
| District/seniūnija normalisation & geometry | Official Vilnius boundary file | `district` kept verbatim as a clean categorical |
| Rolling market price index (`price_uf_MA_7D`, `relative_price_uf`) | A time series. Data covers **4 scrape days**; a 7-day rolling index would be noise. | documented formula, not implemented |
| Rental pipeline | Only 50 rent rows exist (partial scrape) | source registered in config, disabled |
| Correlation-based feature pruning | Belongs to modelling, not cleaning | — |
| Price-change tracking | `original_price_eur` / `price_change_*` are 100% null | columns dropped, re-added when scraper populates them |

## Anti-patterns in InmoAI to deliberately avoid

1. **Notebooks as the pipeline.** 8 of 11 stages are `.ipynb` with cell-order dependencies.
   → Plain importable modules, one CLI entry point.
2. **Hard-coded absolute paths** (`ROOT = r"C:\Users\tomas\Desktop\..."`).
   → Paths in YAML config, resolved relative to the repo root.
3. **Secrets committed in config** (`technical_config_template.py` contains a real-looking
   password, a Google API key and two captcha keys).
   → No credentials anywhere; this pipeline needs none.
4. **Silent `except: a = 1`** swallowing failures in the Haversine loops.
   → Never bare-except. Parse failures produce a recorded flag, not silence.
5. **Magic numbers inline** across notebook cells, different per property type.
   → All thresholds in `config/cleaning.yaml`, sourced from measured distributions.
6. **In-place mutation** (`inplace=True` everywhere).
   → Functions take a DataFrame and return a new one.
7. **`print()` as logging**, no run record.
   → `logging` to file + console, plus a machine-readable cleaning report.
8. **Silent row loss.** Filters are applied with no count of what was removed or why.
   → Every removal and every flag is counted and attributed to a named rule.
9. **`current_year` used for age**, making output depend on when it was run.
   → A `reference_date` derived from the data itself, so reruns are byte-identical.
10. **Copy-pasted per-column cleaning blocks** (bedrooms, bathrooms, cellars, parkings…).
    → One parameterised helper.
