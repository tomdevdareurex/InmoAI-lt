"""Which cleaned columns each segment model is allowed to use.

Feature availability is a function of ``property_type``, NOT ``listing_type``. The scraper
captures ``floor``/``balcony``/``storage`` only for apartments and
``plot_area_sqm``/``garage``/``house_type`` only for houses, while rent and sale differ only
in price regime (EUR/month vs EUR) -- they share an identical set of populated columns.

That is why two feature lists generate all four segment models with no per-segment branching.
Measured against ``data/processed/segments/*_analysis.csv``; see ``docs/DATA_PROFILE.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICE_COLUMN = "price_eur"
AREA_COLUMN = "total_area_sqm"

# Deliberately excluded, despite being fully populated:
#   views_count, listing_age_days, days_since_update -- these describe the advertisement,
#     not the property. Including them would break cross-prediction: when the rent model
#     scores a for-sale listing, the ad metadata belongs to the sale ad, not to the
#     hypothetical rental ad we are pricing.
#   image_count -- a scraper capture artefact, capped at 4 for ~99.5% of rows (README §9).
#   price_per_sqm_eur -- derived from the target; including it would leak the answer.

_SHARED_NUMERIC = (
    "total_area_sqm",
    "rooms",
    "area_per_room",
    "total_floors",
    "construction_year",
    "building_age_years",
    "effective_year",
    "years_since_renovation",  # ~9% populated; CatBoost handles NaN natively
    "is_new_build",
    "has_renovation",
    "latitude",
    "longitude",
    "heating_type_count",
    "heating_central",
    "heating_gas",
    "heating_electric",
    "basement",
    "terrace",
    "alarm",
    "security_cameras",
    "security_feature_count",
    "has_water_body_nearby",
)

_SHARED_CATEGORICAL = (
    "district",
    "building_type",
    "condition",
    "energy_class",  # 16-31% populated; NaN becomes its own "unknown" category
)

# Populated for apartments only (0% for houses).
_APARTMENT_NUMERIC = (
    "floor",
    "floor_ratio",
    "is_ground_floor",
    "is_top_floor",
    "balcony",
    "storage",
    "orientation_count",
)

# Populated for houses only (0% for apartments).
_HOUSE_NUMERIC = (
    "plot_area_sqm",
    "plot_to_building_ratio",
    "garage",
    "fenced_area",
    "paved_access",
    "water_city",
)

_HOUSE_CATEGORICAL = ("house_type",)


@dataclass(frozen=True)
class FeatureSpec:
    """The columns one segment model consumes, split by how they are preprocessed."""

    numeric: tuple[str, ...]
    categorical: tuple[str, ...]

    @property
    def all_columns(self) -> tuple[str, ...]:
        return self.numeric + self.categorical


def features_for(property_type: str) -> FeatureSpec:
    """Return the feature set for ``apartment`` or ``house``."""
    if property_type == "apartment":
        return FeatureSpec(
            numeric=_SHARED_NUMERIC + _APARTMENT_NUMERIC,
            categorical=_SHARED_CATEGORICAL,
        )
    if property_type == "house":
        return FeatureSpec(
            numeric=_SHARED_NUMERIC + _HOUSE_NUMERIC,
            categorical=_SHARED_CATEGORICAL + _HOUSE_CATEGORICAL,
        )
    raise ValueError(f"unknown property_type: {property_type!r} (expected apartment or house)")
