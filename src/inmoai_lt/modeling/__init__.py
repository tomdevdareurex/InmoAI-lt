"""Price models for the four Vilnius market segments, plus cap-rate cross-prediction.

Typical use::

    from inmoai_lt.modeling import SegmentModel, load_segment, estimate_cap_rate

    model = SegmentModel.train("apartment_sale")
    model.save()

    rent_model = SegmentModel.load("apartment_rent")
    sale = load_segment("apartment_sale")
    cap_rates = estimate_cap_rate(sale, rent_model)
"""

from .config import ModelConfig, load_model_config
from .dataset import SEGMENTS, load_segment, prepare, split_segment
from .features import FeatureSpec, features_for
from .investment import cap_rate_by_district, estimate_cap_rate, estimate_monthly_rent
from .metrics import format_metrics, regression_metrics
from .model import SegmentModel, train_all
from .target import SUPPORTED_TARGETS, target_transform

__all__ = [
    "SEGMENTS",
    "SUPPORTED_TARGETS",
    "FeatureSpec",
    "ModelConfig",
    "SegmentModel",
    "cap_rate_by_district",
    "estimate_cap_rate",
    "estimate_monthly_rent",
    "features_for",
    "format_metrics",
    "load_model_config",
    "load_segment",
    "prepare",
    "regression_metrics",
    "split_segment",
    "target_transform",
    "train_all",
]
