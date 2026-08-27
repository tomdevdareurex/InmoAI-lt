"""Load and hash the pipeline configuration (cleaning.yaml + mappings_lt_en.yaml)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class PipelineConfig:
    cleaning: dict[str, Any]
    mappings: dict[str, dict[str, str]]
    config_hash: str
    raw_dir: Path
    output_dir: Path


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _hash_config(cleaning: dict[str, Any], mappings: dict[str, Any]) -> str:
    import json

    payload = json.dumps({"cleaning": cleaning, "mappings": mappings}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_config(
    config_path: Path | None = None,
    mappings_path: Path | None = None,
    raw_dir: Path | None = None,
    out_dir: Path | None = None,
) -> PipelineConfig:
    config_path = config_path or (REPO_ROOT / "config" / "cleaning.yaml")
    mappings_path = mappings_path or (REPO_ROOT / "config" / "mappings_lt_en.yaml")

    cleaning = _load_yaml(config_path)
    mappings = _load_yaml(mappings_path)

    resolved_raw_dir = raw_dir or (REPO_ROOT / cleaning.get("input", {}).get("raw_dir", "data/raw"))
    resolved_out_dir = out_dir or (REPO_ROOT / cleaning.get("output", {}).get("dir", "data/processed"))

    return PipelineConfig(
        cleaning=cleaning,
        mappings=mappings,
        config_hash=_hash_config(cleaning, mappings),
        raw_dir=Path(resolved_raw_dir),
        output_dir=Path(resolved_out_dir),
    )
