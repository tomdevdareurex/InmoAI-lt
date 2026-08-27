# Vilnius Data Profile (verified)

Every number below was measured directly from the source CSVs on 2026-08-26.
Do not re-derive these; do not contradict them without re-measuring.

## Source files

Produced by the `real_estate` scraper (`aruodas_scraper` package, aruodas.lt):

`C:\Users\wn686\OneDrive - Deutsche Börse AG\Desktop\REPOs\real_estate\data\processed\`

| File | Rows | Cols | Notes |
|---|---|---|---|
| `apartments_sale_vilnius.csv` | 3105 | 102 | `listing_type=sale`, `property_type=apartment` |
| `houses_sale_vilnius.csv` | 834 | 102 | `listing_type=sale`, `property_type=house` |
| `apartments_rent_vilnius.csv` | 50 | 102 | `listing_type=rent`. Partial/test scrape. **Disabled by default.** |

- Encoding: **UTF-8 with BOM** (`utf-8-sig`). Must be read with `encoding="utf-8-sig"`.
- Identical 102-column schema across all three files.
- `listing_id` is unique within and across files (0 duplicates, 0 overlap). Prefix `1-`=apartment sale, `2-`=house sale.
- Scrape dates present: 2026-08-21, 2026-08-22, 2026-08-23, 2026-08-25.
- Constant-value columns: `country=Lithuania`, `currency=EUR`, `listing_status=active`,
  `record_source=detail`, `coordinate_source=embedded_script`, `city=municipality=Vilnius`.

## Column population

**48 columns are 100% NULL for apartments, 44 for houses.**

All-null in **both** files (drop, but record):
`access_road, additional_land_features, advertiser_name, agency_name, apartment_layout,
bathrooms, bedrooms, building_administration_information, building_renovation_status,
building_renovation_year, cadastral_or_legal_notes, completion_percent, description_en,
electricity, furnishing, gas, house_number, lift, living_area_sqm, microdistrict,
orientation, original_price_eur, outbuildings, ownership_type, parking, plot_purpose,
price_change_eur, price_change_percent, renovation_year, sector, seller_type, sewerage,
title_en, usable_area_sqm, video_url, virtual_tour_url, window_orientation`

All-null for **apartments only** (populated for houses — keep):
`basement_area_sqm, garage, garage_area_sqm, house_total_area_sqm, house_type,
number_of_floors, plot_area_ares, plot_area_original, plot_area_sqm, plot_area_unit, water_supply`

All-null for **houses only** (populated for apartments — keep):
`apartment_number, apartment_total_area_sqm, balcony, floor, storage`

> `house_number` and `window_orientation` are all-null **even though the data exists in
> `raw_attributes_json`**. See "Recoverable data" below. `renovation_year` likewise.

### Redundant / derived columns

| Column | Relationship | Action |
|---|---|---|
| `municipality` | == `city` (100%) | collapse to `city` |
| `district`, `local_area` | == `neighbourhood` (100% apt, 828/834 & 833/834 house) | collapse to `district` |
| `canonical_url` | == `listing_url` (100%) | collapse to `listing_url` |
| `apartment_total_area_sqm` | == `total_area_sqm` where apartment | drop |
| `house_total_area_sqm` | == `total_area_sqm` where house | drop |
| `number_of_floors` | == `total_floors` where house | drop |
| `price_per_sqm_eur` | == `price_eur / total_area_sqm` exactly (0 rows differ by >1) | keep, add consistency check |
| `plot_area_ares` | == `plot_area_sqm / 100` | drop |

`image_count` is **4 for 3918/3939 rows** (3 for 8, 1 for 8, 2 for 5). This is a scraper
capture limit, not a listing property. Keep but mark low-information; do not use as a feature.

## `raw_attributes_json` — measured label inventory

### Apartments (3105 rows, 14 distinct labels)

| LT label | Count | % | Promoted to column? | Sample values |
|---|---|---|---|---|
| `Aukštas` | 3105 | 100% | yes → `floor` | 3, 4, 1, 2, 5 |
| `Aukštų sk.` | 3105 | 100% | yes → `total_floors` | 9, 8, 4, 5 |
| `Kambarių sk.` | 3105 | 100% | yes → `rooms` | 2, 4, 3, 1 |
| `Metai` | 3105 | 100% | **PARTIAL** → `construction_year` | `2026`, `1960 statyba, 2026 renovacija` |
| `Pastato tipas` | 3105 | 100% | yes → `building_type` | Blokinis, Monolitinis, Mūrinis, Kita, Medinis, Rąstinis, Karkasinis |
| `Plotas` | 3105 | 100% | yes → `total_area_sqm` | `54,02 m²` |
| `Įrengimas` | 3105 | 100% | yes → `condition` | Įrengtas, Dalinė apdaila, Neįrengtas, Kita, Nebaigtas statyti |
| `Šildymas` | 3105 | 100% | yes → `heating_type` | `Centrinis kolektorinis, aeroterminis` |
| **`Namo numeris`** | **2239** | **72.1%** | **NO — lost** | 27, 5, 8A, 53 |
| **`Langų orientacija`** | **1594** | **51.3%** | **NO — lost** | `Vakarai`, `Šiaurė, pietūs, rytai` |
| `Pastato energijos suvartojimo klasė` | 542 | 17.5% | yes → `energy_class` | A++, A+, B, A, G, C, D, E |
| `Buto numeris` | 300 | 9.7% | yes → `apartment_number` | 6, C2-11, A86 |
| **`Unikalus daikto numeris (RC numeris)`** | **103** | **3.3%** | **NO — lost** | `4400-6802-5650:1258` |
| **`Objektas`** | **22** | **0.7%** | **NO — lost** | `Patalpa, poilsio paskirtis`(11), `Buto dalis`(7), `Patalpa, viešbučių paskirtis`(4) |

### Houses (834 rows, 15 distinct labels)

| LT label | Count | % | Promoted? | Sample values |
|---|---|---|---|---|
| `Metai` | 834 | 100% | **PARTIAL** | `2013`, `2013 statyba, 2025 renovacija` |
| `Namo tipas` | 834 | 100% | yes → `house_type` | Sublokuotas namas, Namas (gyvenamasis), Sodo namas, Namo dalis, Sodyba, Kita (nukeliamas, projektas, kt.) |
| `Pastato tipas` | 834 | 100% | yes | Mūrinis, Karkasinis, Blokinis, Monolitinis, Kita, Rąstinis, Medinis, Skydinis |
| `Plotas` | 834 | 100% | yes | `132,85 m²` |
| `Sklypo plotas` | 834 | 100% | yes → `plot_area_*` | `2,6 a`, `10,35 a` |
| `Įrengimas` | 834 | 100% | yes | + `Pamatai` (foundations only, 1 row) |
| `Šildymas` | 834 | 100% | yes | Dujinis, Aeroterminis, Geoterminis, ... |
| `Aukštų sk.` | 833 | 99.9% | yes | 1–4 |
| `Kambarių sk.` | 756 | 90.6% | yes | 1–22 |
| `Vanduo` | 472 | 56.6% | yes → `water_supply` | `Artezinis gręžinys, vietinis vandentiekis` |
| **`Namo numeris`** | **452** | **54.2%** | **NO — lost** | 24, 55, 9E |
| `Pastato energijos suvartojimo klasė` | 254 | 30.5% | yes | A++ … G |
| **`Artimiausias vandens telkinys`** | **157** | **18.8%** | **NO — lost** | Ežeras(68), Upė(60), Tvenkinys(29) |
| **`Iki vandens telkinio (m)`** | **120** | **14.4%** | **NO — lost** | `250`, `1 000`, `3 800` (space thousands sep) |
| **`Unikalus daikto numeris (RC numeris)`** | **37** | **4.4%** | **NO — lost** | `4400-3673-0174` |

### Recoverable data — the highest-value work in this repo

1. **`renovation_year`** — `Metai` encodes `"<year> statyba, <year> renovacija"` for
   **277 apartments + 78 houses**. The scraper's `parse_integer` took the first number and
   discarded the renovation year. `renovation_year` column is 100% NULL as a result.
2. **`window_orientation`** — 1594 apartments (51.3%). Column is 100% NULL.
3. **`house_number`** — 2239 apartments + 452 houses. Column is 100% NULL. Needed for a
   safe address-based duplicate key (`full_address` is street-level only).
4. **`cadastral_id`** — 140 rows total.
5. **water proximity** (houses) — 157 water-body types + 120 distances.
6. **`Objektas`** — 22 apartments that are *not* standard apartments (hotel premises,
   share-of-apartment, recreational premises). Quality flag, not a drop.

### `Langų orientacija` — measured value space

17 distinct combinations. **Token order is NOT canonical**: both `Šiaurė, pietūs` (98) and
`Pietūs, šiaurė` (1) occur; both `Vakarai, rytai` (162) and `Rytai, vakarai` (1) occur.
Must parse to an unordered set.

Token totals: `rytai` 789 (east), `vakarai` 787 (west), `pietūs` 750 (south), `šiaurė` 361 (north).

## Categorical fields — mixed Lithuanian / English

The scraper maps only a subset of values to English; **unmapped values pass through in
Lithuanian**, producing mixed-language columns.

| Column | Distinct | English values present | Lithuanian leftovers |
|---|---|---|---|
| `building_type` | 8 | brick(2829), concrete_block(688), monolithic(247), wood(61) | Kita(42), Rąstinis(43), Karkasinis(28), Skydinis(1) |
| `condition` | 6 | fully_finished(3152), partially_finished(629), unfinished(81) | Kita(67), Nebaigtas statyti(9), **Pamatai(1)** |
| `house_type` | 6 | detached_house(445), terraced_house(277) | Sodo namas(71), Namo dalis(31), Kita (nukeliamas, projektas, kt.)(6), Sodyba(4) |
| `heating_type` | 43 apt / 58 house | *none mapped* | all Lithuanian, multi-valued |
| `water_supply` | 12 | *none mapped* | all Lithuanian, multi-valued |
| `energy_class` | 9 | A++, A+, A, B, C, D, E, F, G | — |
| `district` | 52 apt / 59 house | Lithuanian place names — **keep as-is, do not translate** | Naujamiestis, Senamiestis, Žirmūnai … |

### Multi-valued fields — case is inconsistent

`heating_type` and `water_supply` are comma-separated. **The second and later tokens are
lowercased by the source**, e.g. `"Centrinis, dujinis"`, `"Kietu kuru, kita"`.
Mapping must be **case-insensitive**.

Measured `heating_type` tokens (case-folded): `centrinis kolektorinis`(1318),
`centrinis`(1254), `dujinis`(627), `aeroterminis`(389), `elektra`(251),
`kietu kuru`(220), `kita`(134), `geoterminis`(87), `saulės energija`(46), `skystu kuru`(3).

Measured `water_supply` tokens (case-folded): `miesto vandentiekis`(226),
`artezinis gręžinys`(153), `vietinis vandentiekis`(105), `šulinys`(21), `kita`(7).

## Boolean feature columns

`all_features_json` only ever contains `True` values. The boolean columns are `True` / `NaN`
— there is no explicit `False`.

Feature keys observed **per property type**:

- apartments: `balcony`(1316), `basement`(544), `security_cameras`(571), `storage`(461),
  `terrace`(339), `alarm`(282). **Never** `garage`, `lift`, `fenced_area`, `paved_access`.
- houses: `paved_access`(426), `terrace`(385), `fenced_area`(361), `alarm`(240),
  `garage`(236), `basement`(138), `security_cameras`(102). **Never** `balcony`, `storage`, `lift`.

Consequence: `lift` is all-NULL for apartments **not** because no building has a lift, but
because aruodas does not expose that feature label in the scraped section. Treating NaN as
`False` for `lift` would fabricate data. See the tri-state rule in the implementation plan.

## Numeric distributions (measured)

### Apartments (n=3105)
| Column | min | p1 | median | p99 | max |
|---|---|---|---|---|---|
| `price_eur` | 3 427 | 40 036 | 199 000 | 1 394 600 | 7 000 000 |
| `price_per_sqm_eur` | 348 | 1 225 | 3 905 | 9 225 | 11 900 |
| `total_area_sqm` | 5.55 | 15.21 | 53.50 | 204.87 | 1 319.00 |
| `rooms` | 1 | 1 | 2 | 6 | 15 |
| `floor` | 0 | 0 | 3 | 14 | 29 |
| `total_floors` | 1 | 1 | 5 | 18 | 29 |
| `construction_year` | 1736 | 1913 | 2000 | 2027 | 2028 |
| `views_count` | 1 | 89 | 1 150 | 11 964 | 35 515 |
| `listing_age_days` | 0 | 0 | 21 | 336 | 1 518 |

### Houses (n=834)
| Column | min | p1 | median | p99 | max |
|---|---|---|---|---|---|
| `price_eur` | 13 000 | 49 998 | 349 000 | 2 433 500 | 7 000 000 |
| `price_per_sqm_eur` | 203 | 605 | 2 655 | 8 077 | 11 293 |
| `total_area_sqm` | 20.00 | 30.00 | 135.00 | 560.45 | 2 842.76 |
| `rooms` | 1 | 2 | 4 | 10 | 22 |
| `total_floors` | 1 | 1 | 2 | 3 | 4 |
| `construction_year` | 1696 | 1939 | 2017 | 2026 | 2027 |
| `plot_area_sqm` | **0** | 0 | 600 | 2 822 | 19 000 |
| `views_count` | 25 | 132 | 1 643 | 21 559 | 129 756 |
| `listing_age_days` | 0 | 0 | 25.5 | 358 | 1 669 |

Measured anomalies:
- `floor > total_floors`: **0** rows. `floor == 0`: 37 apartments (ground/semi-basement).
- `plot_area_sqm == 0` (`"0 a"` verbatim): **10** houses.
- `total_area_sqm < 15`: 25 apartments, 0 houses.
- `price_eur < 20 000`: 4 apartments, 2 houses.
- `price_per_sqm_eur < 500`: 1 apartment, 7 houses.
- `construction_year > 2026`: present (off-plan / new builds up to 2028). Valid.
- `listing_created_date > listing_updated_date`: 0 rows.
- `listing_created_date > scrape date`: 0 rows.
- `diagnostic_warnings` non-empty: **0** rows (all coordinates passed the scraper's
  Lithuania-bounds check).

## Geography

- Latitude range 54.5738 – 54.8234 (p0.5–p99.5: 54.5905 – 54.8073)
- Longitude range 25.0516 – 25.4655 (p0.5–p99.5: 25.0800 – 25.4318)
- All inside the scraper's Lithuania bounds (53.8–56.5 N, 20.8–26.9 E).
- `coordinate_precision == "approximate"`: 234 apartments (7.5%), 138 houses (16.5%);
  NULL otherwise (meaning exact). This is a real quality signal — keep it.

## Text

- Lithuanian diacritics are intact: `č š ž ę ė į ų ū ą`.
  Example title: `Butas, Vilniuje Visoriuose Visorių g., 2 kambarių butas`.
- `description_lt` contains `[REDACTED_PHONE]` / `[REDACTED_EMAIL]` in **525** apartment
  rows — the scraper already applied privacy redaction. Do not attempt to reverse it.
- `street` suffixes are varied and meaningful: `g.` (gatvė/street), `pr.` (prospektas/avenue),
  `al.` (alėja), `kel.` (kelias/road), `pl.` (plentas/highway), `a.` (aikštė/square).
- JSON-encoded string columns that must be parsed: `raw_attributes_json`,
  `all_features_json`, `image_urls`, `security_features`, `additional_land_features`,
  `diagnostic_warnings`.

## Duplicates (measured)

| Key | Apartments | Houses |
|---|---|---|
| `listing_id` | 0 | 0 |
| `canonical_url` | 0 | 0 |
| `full_address + price + area + rooms` | 48 | 21 |
| `full_address + area + rooms` (price may differ) | 151 | 42 |
| `lat + lon + area + price` | 66 | 20 |
| `title_lt + price` | 116 | 27 |

`full_address` is street-level only (`Vilnius, Žirmūnai, Kareivių g.`) — it contains **no
house number**. Address-only deduplication is therefore unsafe: two different flats on the
same street with the same size and room count are not necessarily the same listing.
Recovering `Namo numeris` materially improves the key.
