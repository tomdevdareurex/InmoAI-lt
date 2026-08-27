"""Copy scraper CSV outputs into ``data/raw/`` without modifying the source.

Usage:
    python scripts/ingest_raw.py
    python scripts/ingest_raw.py --source "<real_estate>/data/processed"
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT.parent / "real_estate" / "data" / "processed"
DEFAULT_DEST = REPO_ROOT / "data" / "raw"

SOURCE_FILES = [
    "apartments_sale_vilnius.csv",
    "houses_sale_vilnius.csv",
    "apartments_rent_vilnius.csv",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Directory containing the scraper's processed CSVs (read-only).",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help="Destination directory (data/raw by default).",
    )
    return parser.parse_args(argv)


def ingest(source_dir: Path, dest_dir: Path) -> list[Path]:
    """Copy each expected source CSV into dest_dir. Never writes to source_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    missing: list[str] = []
    for name in SOURCE_FILES:
        src = source_dir / name
        if not src.exists():
            missing.append(name)
            continue
        dst = dest_dir / name
        shutil.copyfile(src, dst)
        copied.append(dst)
        print(f"copied {src} -> {dst}")
    if missing:
        print(f"WARNING: missing source files: {missing}", file=sys.stderr)
    return copied


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_dir = args.source.resolve()
    dest_dir = args.dest.resolve()
    if not source_dir.exists():
        print(f"ERROR: source directory does not exist: {source_dir}", file=sys.stderr)
        return 1
    copied = ingest(source_dir, dest_dir)
    if not copied:
        print("ERROR: no files copied", file=sys.stderr)
        return 1
    print(f"Ingested {len(copied)} file(s) into {dest_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
