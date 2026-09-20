"""Cap-rate cross-prediction: the arithmetic, the guards, and the confidence flag."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pytest

from inmoai_lt.modeling import cap_rate_by_district, estimate_cap_rate, estimate_monthly_rent


@dataclass
class StubModel:
    """Stands in for a SegmentModel so the arithmetic can be checked against known rents."""

    property_type: str = "apartment"
    listing_type: str = "rent"
    monthly_rent: float = 800.0
    metadata: dict[str, Any] = field(default_factory=lambda: {"districts_seen": ["Alpha"]})

    @property
    def low_n(self) -> bool:
        return bool(self.metadata.get("low_n", False))

    @property
    def segment(self) -> str:
        return f"{self.property_type}_{self.listing_type}"

    def predict(self, listings: pd.DataFrame) -> np.ndarray:
        return np.full(len(listings), self.monthly_rent)


@pytest.fixture
def sale_listings() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "listing_id": ["a-1", "a-2"],
            "district": ["Alpha", "Beta"],
            "property_type": ["apartment", "apartment"],
            "total_area_sqm": [50.0, 80.0],
            "price_eur": [192_000.0, 240_000.0],
        }
    )


def test_cap_rate_is_annual_rent_over_asking_price(sale_listings):
    result = estimate_cap_rate(sale_listings, StubModel(monthly_rent=800.0))

    assert result["estimated_annual_rent_eur"].tolist() == [9600.0, 9600.0]
    assert result["gross_cap_rate_pct"].tolist() == [5.0, 4.0]


def test_price_premium_compares_asking_to_the_sale_model(sale_listings):
    sale_model = StubModel(listing_type="sale", monthly_rent=160_000.0)
    result = estimate_cap_rate(sale_listings, StubModel(), sale_model=sale_model)

    assert result["predicted_price_eur"].tolist() == [160_000.0, 160_000.0]
    assert result["price_premium_pct"].tolist() == [20.0, 50.0]


def test_unseen_districts_are_flagged_low_confidence(sale_listings):
    # The rent model saw "Alpha" only, so "Beta" is target-encoded to the global mean.
    result = estimate_cap_rate(sale_listings, StubModel())
    assert result["low_confidence"].tolist() == [False, True]


def test_a_low_n_rent_model_flags_every_row(sale_listings):
    rent_model = StubModel(metadata={"districts_seen": ["Alpha", "Beta"], "low_n": True})
    result = estimate_cap_rate(sale_listings, rent_model)
    assert result["low_confidence"].all()


def test_a_sale_model_cannot_be_used_to_estimate_rent(sale_listings):
    with pytest.raises(ValueError, match="expected a rent model"):
        estimate_monthly_rent(sale_listings, StubModel(listing_type="sale"))


def test_property_types_must_match(sale_listings):
    with pytest.raises(ValueError, match="rent model is for"):
        estimate_cap_rate(sale_listings, StubModel(property_type="house"))


def test_district_summary_drops_thin_districts():
    cap_rates = pd.DataFrame(
        {
            "district": ["Alpha"] * 3 + ["Beta"],
            "gross_cap_rate_pct": [4.0, 5.0, 6.0, 9.0],
            "asking_price_eur": [100_000.0, 200_000.0, 300_000.0, 150_000.0],
            "estimated_monthly_rent_eur": [500.0, 700.0, 900.0, 1000.0],
        }
    )
    summary = cap_rate_by_district(cap_rates, min_listings=3)

    assert summary.index.tolist() == ["Alpha"]
    assert summary.loc["Alpha", "median_cap_rate_pct"] == 5.0
    assert summary.loc["Alpha", "listings"] == 3
