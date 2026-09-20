"""Cross-prediction: price a for-sale listing with the rental model, then derive a cap rate.

Ports the reference notebook's ``cap_rate = price_uf_pred_rent * 12 / price_uf``.

This works because a rent model and a sale model of the same property type consume an
identical feature set -- feature availability follows ``property_type``, not
``listing_type`` (see features.py). So an apartment_sale frame can be fed straight to the
apartment_rent model.

The result is a GROSS yield: it ignores vacancy, management, maintenance, and tax. Treat it
as a comparative ranking signal, not a net return.
"""

from __future__ import annotations

import pandas as pd

from .features import PRICE_COLUMN
from .model import SegmentModel

MONTHS_PER_YEAR = 12


def estimate_monthly_rent(sale_listings: pd.DataFrame, rent_model: SegmentModel) -> pd.Series:
    """Estimated achievable rent in EUR/month for listings that are advertised for sale."""
    if rent_model.listing_type != "rent":
        raise ValueError(
            f"expected a rent model, got segment {rent_model.segment!r} -- "
            "cross-prediction needs the rental model of the same property type"
        )
    predicted = rent_model.predict(sale_listings)
    return pd.Series(predicted, index=sale_listings.index, name="estimated_monthly_rent_eur")


def estimate_cap_rate(
    sale_listings: pd.DataFrame,
    rent_model: SegmentModel,
    sale_model: SegmentModel | None = None,
) -> pd.DataFrame:
    """Estimated gross cap rate per listing.

        gross_cap_rate = estimated_monthly_rent * 12 / sale_price

    Pass ``sale_model`` to also get its price estimate alongside the asking price, which
    shows whether a listing looks over- or under-priced independently of its yield.
    """
    if rent_model.property_type != sale_listings["property_type"].iloc[0]:
        raise ValueError(
            f"rent model is for {rent_model.property_type!r} but listings are "
            f"{sale_listings['property_type'].iloc[0]!r}"
        )

    monthly_rent = estimate_monthly_rent(sale_listings, rent_model)
    annual_rent = monthly_rent * MONTHS_PER_YEAR
    asking_price = pd.to_numeric(sale_listings[PRICE_COLUMN], errors="coerce")

    # A district the rent model never saw is target-encoded to the global mean, so its rent
    # estimate carries no local signal. Surfaced rather than silently averaged away.
    districts_seen = set(rent_model.metadata.get("districts_seen", []))
    unseen_district = ~sale_listings["district"].astype(str).isin(districts_seen)

    result = pd.DataFrame(
        {
            "listing_id": sale_listings["listing_id"],
            "district": sale_listings["district"],
            "total_area_sqm": sale_listings["total_area_sqm"],
            "asking_price_eur": asking_price,
            "estimated_monthly_rent_eur": monthly_rent.round(0),
            "estimated_annual_rent_eur": annual_rent.round(0),
            "gross_cap_rate_pct": (annual_rent / asking_price * 100).round(2),
            # True when the rent model was trained on too little data (house_rent) or the
            # district was unseen. Either way, do not lean on this number.
            "low_confidence": rent_model.low_n | unseen_district,
        },
        index=sale_listings.index,
    )

    if sale_model is not None:
        predicted_price = sale_model.predict(sale_listings)
        result["predicted_price_eur"] = pd.Series(
            predicted_price, index=sale_listings.index
        ).round(0)
        result["price_premium_pct"] = (
            (asking_price - result["predicted_price_eur"]) / result["predicted_price_eur"] * 100
        ).round(2)

    return result


def cap_rate_by_district(cap_rates: pd.DataFrame, min_listings: int = 10) -> pd.DataFrame:
    """Median gross cap rate per district, for districts with enough listings to mean anything."""
    grouped = cap_rates.groupby("district").agg(
        listings=("gross_cap_rate_pct", "size"),
        median_cap_rate_pct=("gross_cap_rate_pct", "median"),
        median_price_eur=("asking_price_eur", "median"),
        median_monthly_rent_eur=("estimated_monthly_rent_eur", "median"),
    )
    return (
        grouped[grouped["listings"] >= min_listings]
        .sort_values("median_cap_rate_pct", ascending=False)
        .round(2)
    )
