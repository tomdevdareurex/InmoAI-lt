"""How the price target is transformed for regression, and inverted back to EUR.

Everything the caller sees is EUR. The transform chosen in ``config/modeling.yaml`` only
changes what the estimator regresses on internally, so the three modes stay directly
comparable on the same held-out split.

``to_per_sqm`` exists for the geo-neighbour base learner: averaging the raw prices of
nearby listings is noisy because neighbours differ in size, so the KNN is always fitted on
a per-square-metre version of the target, expressed in that target's own space.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

import numpy as np
import pandas as pd

# Written as typing.Union, not `|`: this alias is evaluated at import time, and numpy types
# do not support `|` on the Python 3.9 this project still targets.
Array = Union[np.ndarray, pd.Series]


@dataclass(frozen=True)
class TargetTransform:
    """Maps price <-> model space. ``area`` is ``total_area_sqm``, never null or zero
    (``quality.fatal`` in config/cleaning.yaml drops such rows)."""

    name: str

    def forward(self, price: Array, area: Array) -> Array:
        """price (EUR) -> what the estimator regresses on."""
        if self.name == "price":
            return price
        if self.name == "price_per_sqm":
            return price / area
        return np.log(price)

    def inverse(self, model_output: Array, area: Array) -> Array:
        """estimator output -> price (EUR)."""
        if self.name == "price":
            return model_output
        if self.name == "price_per_sqm":
            return model_output * area
        return np.exp(model_output)

    def to_per_sqm(self, y_model: Array, area: Array) -> Array:
        """Model-space target rescaled to a per-sqm basis, for the neighbour KNN."""
        if self.name == "price":
            return y_model / area
        if self.name == "price_per_sqm":
            return y_model  # already per sqm
        return y_model - np.log(area)  # log(price) - log(area) == log(price/area)


SUPPORTED_TARGETS = ("price", "price_per_sqm", "log_price")


def target_transform(name: str) -> TargetTransform:
    if name not in SUPPORTED_TARGETS:
        raise ValueError(f"unknown target {name!r}; expected one of {SUPPORTED_TARGETS}")
    return TargetTransform(name)
