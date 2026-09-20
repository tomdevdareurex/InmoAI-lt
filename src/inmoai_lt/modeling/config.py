"""Load config/modeling.yaml into a frozen dataclass."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from ..config import REPO_ROOT
from .target import SUPPORTED_TARGETS

DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "modeling.yaml"


@dataclass(frozen=True)
class ModelConfig:
    target: str
    test_size: float
    random_seed: int
    catboost: dict[str, Any]
    n_neighbors: int
    stacking_cv: int
    low_n_threshold: int
    models_dir: Path
    per_segment: dict[str, dict[str, Any]]

    def for_segment(self, segment: str) -> ModelConfig:
        """Apply this segment's overrides (small segments need fewer neighbours/folds)."""
        override = self.per_segment.get(segment, {})
        return replace(
            self,
            n_neighbors=override.get("n_neighbors", self.n_neighbors),
            stacking_cv=override.get("stacking_cv", self.stacking_cv),
        )


def load_model_config(path: Path | None = None, target: str | None = None) -> ModelConfig:
    """Read modeling.yaml. ``target`` overrides the file, for quick experiments."""
    path = path or DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    neighbours = raw.get("neighbours", {})
    split = raw.get("split", {})
    resolved_target = target or raw.get("target", "price")
    if resolved_target not in SUPPORTED_TARGETS:
        raise ValueError(f"unknown target {resolved_target!r}; expected one of {SUPPORTED_TARGETS}")

    models_dir = Path(raw.get("models_dir", "models"))
    if not models_dir.is_absolute():
        models_dir = REPO_ROOT / models_dir

    return ModelConfig(
        target=resolved_target,
        test_size=split.get("test_size", 0.2),
        random_seed=split.get("random_seed", 42),
        catboost=dict(raw.get("catboost", {})),
        n_neighbors=neighbours.get("n_neighbors", 30),
        stacking_cv=neighbours.get("stacking_cv", 5),
        low_n_threshold=raw.get("low_n_threshold", 300),
        models_dir=models_dir,
        per_segment=dict(neighbours.get("per_segment", {})),
    )
