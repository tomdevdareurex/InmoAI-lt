# Enrichment (deferred)

This package is a placeholder for spatial/socio-economic enrichment of the cleaned
listings produced by `inmoai_lt.pipeline.run_pipeline`. **None of it is implemented.**
`enrich()` exists only to document the intended signature and raises
`NotImplementedError` if called.

```python
def enrich(df: pd.DataFrame, *, lat_col: str = "latitude", lon_col: str = "longitude") -> pd.DataFrame: ...
```

The cleaning pipeline's output (`vilnius_listings_clean.csv` /
`vilnius_listings_analysis.csv`) is complete and self-contained without enrichment.
Nothing downstream depends on this package.

## Why deferred

Every enrichment below needs an external dataset that is not part of
`real_estate/data/processed/` and was not measured in `docs/DATA_PROFILE.md`. Adding
any of them now would mean fabricating a join key or a value that was never verified
against real data -- the one thing this project's cleaning rules explicitly forbid.

## Planned hooks

### 1. Census / socio-economic join
- **Needs**: a district- or microdistrict-level dataset (population, income, age
  structure) keyed by the same `district` names produced by `columns.collapse_district`.
- **Why deferred**: no such dataset is present in the repo or `real_estate/`; Lithuania's
  statistics office (Statistikos departamentas) publishes this but at a different
  administrative granularity than the scraper's `district` field, so the join key would
  need to be worked out and verified before writing any code.

### 2. Nearest-POI distances
- **Needs**: point datasets for POIs (schools, transit stops, supermarkets, parks) with
  coordinates, plus a spatial index (e.g. `scipy.spatial.cKDTree` or `geopandas`/`shapely`
  nearest-neighbour join) against `latitude`/`longitude`.
- **Why deferred**: no POI dataset is bundled; `requirements.txt` does not include a
  geospatial-nearest-neighbour library, and adding one speculatively would violate the
  "only add what's needed" scope of this pass.

### 3. District geometry
- **Needs**: polygon boundaries for Vilnius districts/microdistricts (e.g. a GeoJSON of
  administrative boundaries) to support area-normalised aggregates or map rendering.
- **Why deferred**: no boundary file is available in the repo; `coordinate_precision`
  (see `flag_coords_approximate` in the clean output) also means point-in-polygon
  lookups would be unreliable for ~7.5-16.5% of rows without first accounting for that
  imprecision.

## If implementing later

- Keep the same "new DataFrame, no `inplace=True`" contract as every stage in
  `cleaning/`.
- Never fabricate a value where the source geometry/join key doesn't actually match --
  prefer leaving the enrichment column `NA` (pandas nullable dtypes) over guessing.
- Record provenance (source dataset, download date, join method) in a `CleaningReport`-
  style accumulator so the enrichment run stays auditable like the base pipeline.
