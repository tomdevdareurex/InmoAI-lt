"""Schema constants: the expected raw column set and the final output column order."""

from __future__ import annotations

from typing import Iterable

# The 102-column schema shared by all three source CSVs (measured, docs/DATA_PROFILE.md).
EXPECTED_RAW_COLUMNS: list[str] = [
    "scrape_timestamp_utc", "listing_id", "property_type", "record_source", "listing_type",
    "country", "municipality", "city", "district", "neighbourhood", "microdistrict",
    "sector", "local_area", "street", "house_number", "full_address", "title_lt",
    "title_en", "description_lt", "description_en", "price_eur", "price_per_sqm_eur",
    "original_price_eur", "price_change_eur", "price_change_percent", "currency",
    "listing_created_date", "listing_updated_date", "listing_age_days", "seller_type",
    "advertiser_name", "agency_name", "listing_status", "source_search_url",
    "source_page_number", "search_position", "views_count", "saved_by_users_count",
    "latitude", "longitude", "coordinate_source", "coordinate_precision", "image_count",
    "image_urls", "virtual_tour_url", "video_url", "rooms", "bedrooms", "bathrooms",
    "total_area_sqm", "living_area_sqm", "usable_area_sqm", "plot_area_original",
    "plot_area_unit", "plot_area_sqm", "plot_area_ares", "floor", "total_floors",
    "building_type", "house_type", "construction_year", "renovation_year",
    "completion_percent", "condition", "furnishing", "energy_class", "heating_type",
    "water_supply", "sewerage", "electricity", "gas", "parking", "garage", "balcony",
    "terrace", "basement", "storage", "lift", "orientation", "security_features",
    "ownership_type", "cadastral_or_legal_notes", "all_features_json",
    "raw_attributes_json", "apartment_number", "apartment_total_area_sqm",
    "apartment_layout", "window_orientation", "building_renovation_status",
    "building_renovation_year", "building_administration_information",
    "house_total_area_sqm", "basement_area_sqm", "garage_area_sqm", "number_of_floors",
    "outbuildings", "access_road", "plot_purpose", "additional_land_features",
    "diagnostic_warnings", "listing_url", "canonical_url",
]

assert len(EXPECTED_RAW_COLUMNS) == 102, f"expected 102 columns, got {len(EXPECTED_RAW_COLUMNS)}"

# Columns known to hold JSON-encoded strings; read as `dtype=str` and parsed downstream.
JSON_COLUMNS: list[str] = [
    "raw_attributes_json",
    "all_features_json",
    "image_urls",
    "security_features",
    "additional_land_features",
    "diagnostic_warnings",
]

# Explicit final column order for both clean and analysis outputs, grouped by concern.
# Enforced at write time: any produced column missing from this list raises (schema.py
# forces the schema to stay intentional). Not every column here is guaranteed to exist
# on every run (e.g. a source column that turns out all-null gets dropped upstream) —
# io.py filters this list down to columns actually present before reindexing.
FINAL_COLUMN_ORDER: list[str] = [
    # identity
    "listing_id", "property_type", "listing_type", "source_file",
    # location
    "city", "district", "street", "house_number", "full_address",
    "latitude", "longitude",
    # price
    "price_eur", "price_per_sqm_eur",
    # property
    "rooms", "total_area_sqm", "floor", "total_floors",
    "plot_area_sqm", "plot_area_original", "plot_area_unit",
    "building_type", "building_type_raw", "house_type", "house_type_raw",
    "object_type_lt", "object_type",
    "construction_year", "renovation_year", "has_renovation",
    "energy_class", "apartment_number", "cadastral_id",
    # condition / systems
    "condition", "condition_raw",
    "heating_type_raw", "heating_types", "heating_type_count",
    "heating_central", "heating_central_collector", "heating_gas", "heating_electric",
    "heating_air_source_heat_pump", "heating_geothermal", "heating_solid_fuel",
    "heating_liquid_fuel", "heating_solar", "heating_stove", "heating_other",
    "water_supply_raw", "water_supply_types", "water_supply_type_count",
    "water_city", "water_local", "water_artesian_well", "water_well", "water_other",
    "water_body_lt", "water_body", "distance_to_water_m",
    # window orientation
    "window_orientation", "orientation_north", "orientation_south",
    "orientation_east", "orientation_west", "orientation_count",
    # features (tri-state boolean)
    "balcony", "basement", "storage", "terrace", "garage", "lift",
    "alarm", "security_cameras", "fenced_area", "paved_access",
    "security_features", "security_feature_count",
    # text / listing metadata
    "title_lt", "description_lt", "listing_url", "source_search_url",
    "image_urls", "diagnostic_warnings",
    "listing_created_date", "listing_updated_date", "listing_age_days",
    "views_count", "saved_by_users_count", "image_count",
    "source_page_number", "search_position",
    "scrape_timestamp_utc", "coordinate_source",
    # duplicates
    "duplicate_group_id", "is_duplicate", "is_duplicate_primary",
    # flags
    "flag_price_out_of_range", "flag_area_out_of_range",
    "flag_price_per_sqm_out_of_range", "flag_price_per_sqm_inconsistent",
    "flag_construction_year_out_of_range", "flag_rooms_out_of_range",
    "flag_floor_gt_total_floors", "flag_plot_area_zero",
    "flag_non_standard_object", "flag_not_habitable",
    "flag_coords_outside_vilnius", "flag_coords_outside_lithuania",
    "flag_coords_approximate", "flag_stale_listing",
    "flag_description_redacted", "flag_missing_description", "flag_duplicate",
    "quality_flag_count", "quality_flags", "is_valid",
    # derived
    "building_age_years", "effective_year", "years_since_renovation",
    "is_new_build", "floor_ratio", "is_ground_floor", "is_top_floor",
    "area_per_room", "plot_to_building_ratio", "has_water_body_nearby",
    "days_since_update",
]


def assert_raw_schema(columns: Iterable[str], source_name: str = "") -> None:
    """Fail loudly if the raw CSV's columns don't match `EXPECTED_RAW_COLUMNS`.

    Schema drift is a real signal (the scraper changed its output), not noise.
    """
    expected = set(EXPECTED_RAW_COLUMNS)
    actual = set(columns)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        label = f" in {source_name}" if source_name else ""
        raise ValueError(
            f"Raw schema mismatch{label}. Missing: {missing}. Extra: {extra}"
        )


def enforce_final_column_order(columns: Iterable[str]) -> list[str]:
    """Return `FINAL_COLUMN_ORDER` filtered to columns actually present.

    Fails if a produced column is present but unlisted in `FINAL_COLUMN_ORDER` --
    this forces the schema to stay intentional.
    """
    present = set(columns)
    unlisted = present - set(FINAL_COLUMN_ORDER)
    if unlisted:
        raise ValueError(f"Unlisted columns present in output: {sorted(unlisted)}")
    return [c for c in FINAL_COLUMN_ORDER if c in present]
