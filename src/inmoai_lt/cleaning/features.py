"""Boolean features from `all_features_json` -- tri-state rule.

`all_features_json` only ever contains `True`. Absence is ambiguous: for each feature
key and each `property_type`, if that key appears at least once for that property
type, `NaN -> False` (the feature is captured for this type, so absence means "not
present"). If the key never appears for that property type, the value stays `NA` --
the source does not capture it, and writing `False` would fabricate data.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

# All feature keys observed across both property types (docs/DATA_PROFILE.md).
ALL_FEATURE_KEYS = [
    "balcony",
    "basement",
    "storage",
    "terrace",
    "garage",
    "lift",
    "alarm",
    "security_cameras",
    "fenced_area",
    "paved_access",
]


def _load_features(raw: object) -> dict[str, Any]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def expand_boolean_features(df: pd.DataFrame, report: Any = None) -> pd.DataFrame:
    """Expand `all_features_json` into one nullable-boolean column per known key.

    Applies the tri-state rule per `property_type`. Drops `all_features_json`.
    """
    result = df.copy()
    if "all_features_json" not in result.columns:
        return result

    parsed = result["all_features_json"].map(_load_features)
    property_types = result["property_type"] if "property_type" in result.columns else pd.Series(["_all_"] * len(result))

    coverage: dict[str, dict[str, bool]] = {}

    for key in ALL_FEATURE_KEYS:
        raw_present = parsed.map(lambda d, k=key: d.get(k) is True)
        col = pd.Series(pd.NA, index=result.index, dtype="boolean")
        for ptype in property_types.dropna().unique():
            mask = property_types == ptype
            captured_for_type = bool(raw_present[mask].any())
            coverage.setdefault(str(ptype), {})[key] = captured_for_type
            if captured_for_type:
                col.loc[mask] = raw_present.loc[mask]
        result[key] = col

    result = result.drop(columns=["all_features_json"])

    if report is not None:
        report.record_feature_coverage(coverage)

    return result
