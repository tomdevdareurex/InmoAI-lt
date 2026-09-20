"""Every target mode has to come back to EUR, or the modes are not comparable."""

from __future__ import annotations

import numpy as np
import pytest

from inmoai_lt.modeling import SUPPORTED_TARGETS, target_transform

PRICE = np.array([120_000.0, 250_000.0, 89_500.0])
AREA = np.array([40.0, 75.0, 31.5])


@pytest.mark.parametrize("name", SUPPORTED_TARGETS)
def test_forward_then_inverse_returns_the_original_price(name: str):
    transform = target_transform(name)
    recovered = transform.inverse(transform.forward(PRICE, AREA), AREA)
    assert np.allclose(recovered, PRICE)


@pytest.mark.parametrize("name", SUPPORTED_TARGETS)
def test_per_sqm_basis_is_the_same_quantity_in_every_target_space(name: str):
    """The neighbour KNN fits on to_per_sqm(); inverting it must give EUR/sqm in all modes."""
    transform = target_transform(name)
    per_sqm = transform.to_per_sqm(transform.forward(PRICE, AREA), AREA)
    # Inverting a per-sqm value with an area of 1 recovers the price-per-sqm in EUR.
    as_eur_per_sqm = transform.inverse(per_sqm, np.ones_like(AREA))
    assert np.allclose(as_eur_per_sqm, PRICE / AREA)


def test_unknown_target_is_rejected():
    with pytest.raises(ValueError, match="unknown target"):
        target_transform("price_per_room")
