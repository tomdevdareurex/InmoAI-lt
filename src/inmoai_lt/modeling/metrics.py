"""Regression metrics, always computed in EUR.

Metric choice follows InmoAI/models/display_helpers.py (RMSE, RMSPE, MAPE, MedAE), plus MAE
and R2. Because every target mode is inverted back to EUR before scoring, the three modes in
config/modeling.yaml can be compared directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs((y_true - y_pred) / y_true)))


def root_mean_square_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean(((y_true - y_pred) / y_true) ** 2)))


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """MAE / MedAE / RMSE in EUR; MAPE / RMSPE as fractions; R2 unitless."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    error = y_true - y_pred
    ss_res = float(np.sum(error**2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    return {
        "n": int(len(y_true)),
        "MAE": float(np.mean(np.abs(error))),
        "MedAE": float(np.median(np.abs(error))),
        "RMSE": float(np.sqrt(np.mean(error**2))),
        "MAPE": mean_absolute_percentage_error(y_true, y_pred),
        "RMSPE": root_mean_square_percentage_error(y_true, y_pred),
        "R2": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
    }


def format_metrics(metrics: dict[str, float]) -> pd.DataFrame:
    """One-row frame with EUR amounts rounded and percentages shown as percentages."""
    return pd.DataFrame(
        [
            {
                "n": metrics["n"],
                "MAE (EUR)": round(metrics["MAE"], 1),
                "MedAE (EUR)": round(metrics["MedAE"], 1),
                "RMSE (EUR)": round(metrics["RMSE"], 1),
                "MAPE (%)": round(metrics["MAPE"] * 100, 2),
                "RMSPE (%)": round(metrics["RMSPE"] * 100, 2),
                "R2": round(metrics["R2"], 4),
            }
        ]
    )
