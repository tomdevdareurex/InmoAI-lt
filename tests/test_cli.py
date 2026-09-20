"""CLI smoke tests: both subcommands must parse their own arguments correctly.

Regression test for a bug where `profile`'s subparser (no `--raw-dir` flag, since it
never reads raw sources) crashed in `_load_ctx` because it unconditionally read
`args.raw_dir`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from inmoai_lt import cli


def _write_yaml(path: Path, data: dict) -> Path:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return path


def test_clean_then_profile(
    tmp_path, monkeypatch, synthetic_raw_dir, synthetic_cleaning_config, mappings
):
    # `clean` hard-codes its log directory to `REPO_ROOT / "logs"`; redirect that to a
    # tmp dir so the test suite never writes into the real repo's logs/.
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)

    out_dir = tmp_path / "out"
    config_path = _write_yaml(tmp_path / "cleaning.yaml", synthetic_cleaning_config)
    mappings_path = _write_yaml(tmp_path / "mappings_lt_en.yaml", mappings)

    clean_exit = cli.main(
        [
            "clean",
            "--config", str(config_path),
            "--mappings", str(mappings_path),
            "--raw-dir", str(synthetic_raw_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert clean_exit == 0
    clean_basename = synthetic_cleaning_config["output"]["clean_basename"]
    assert (out_dir / f"{clean_basename}.csv").exists()
    assert (out_dir / "cleaning_report.html").exists()

    # `profile` has no `--raw-dir` flag at all -- this is the exact call that used to
    # raise `AttributeError: 'Namespace' object has no attribute 'raw_dir'`.
    profile_exit = cli.main(
        [
            "profile",
            "--config", str(config_path),
            "--mappings", str(mappings_path),
            "--out-dir", str(out_dir),
        ]
    )
    assert profile_exit == 0


def test_profile_without_prior_clean_run_reports_missing_output(
    tmp_path, monkeypatch, synthetic_cleaning_config, mappings
):
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    out_dir = tmp_path / "out"
    config_path = _write_yaml(tmp_path / "cleaning.yaml", synthetic_cleaning_config)
    mappings_path = _write_yaml(tmp_path / "mappings_lt_en.yaml", mappings)

    exit_code = cli.main(
        [
            "profile",
            "--config", str(config_path),
            "--mappings", str(mappings_path),
            "--out-dir", str(out_dir),
        ]
    )
    assert exit_code == 1
