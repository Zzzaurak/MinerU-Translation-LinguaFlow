from __future__ import annotations

import subprocess
import os
import sys
from pathlib import Path


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    return subprocess.run(
        [sys.executable, "-m", "mineru_batch_cli", *args],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )


def test_top_level_help_lists_run_and_verify() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert "run" in result.stdout
    assert "verify" in result.stdout


def test_run_help_includes_expected_arguments() -> None:
    result = run_cli("run", "--help")
    assert result.returncode == 0
    assert "--input" in result.stdout
    assert "--output" in result.stdout
    assert "--model-version" in result.stdout
    assert "--continue-on-error" in result.stdout
    assert "--config" in result.stdout
    assert "--translation-enabled" in result.stdout
    assert "--translation-api-base-url" in result.stdout
    assert "--translation-api-key" in result.stdout
    assert "--translation-model" in result.stdout
    assert "--translation-target-language" in result.stdout
    assert "--translation-timeout-sec" in result.stdout
    assert "--translation-retry-max" in result.stdout


def test_verify_help_includes_manifest_argument() -> None:
    result = run_cli("verify", "--help")
    assert result.returncode == 0
    assert "--manifest" in result.stdout
