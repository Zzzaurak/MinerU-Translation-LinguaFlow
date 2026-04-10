from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _launcher_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return env


def _run_launcher(
    *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    repo = _repo_root()
    launcher = (
        repo / "scripts" / ("run-mineru.ps1" if os.name == "nt" else "run-mineru.sh")
    )
    if os.name == "nt":
        cmd = [
            "pwsh",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
            *args,
        ]
    else:
        cmd = ["sh", str(launcher), *args]

    return subprocess.run(
        cmd,
        cwd=cwd or repo,
        env=_launcher_env(),
        text=True,
        capture_output=True,
        check=False,
    )


def test_launcher_help_prints_usage() -> None:
    result = _run_launcher("--help")
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "run-mineru" in result.stdout


def test_launcher_fails_when_input_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing-input"
    result = _run_launcher(
        "--input",
        str(missing),
        "--output",
        str(tmp_path / "out"),
        "--model-version",
        "pipeline",
    )
    assert result.returncode != 0
    assert "Input directory does not exist" in result.stderr


def test_launcher_accepts_relative_input_from_non_repo_cwd(tmp_path: Path) -> None:
    runner_dir = tmp_path / "runner"
    local_input = runner_dir / "local-in"
    runner_dir.mkdir(parents=True)
    local_input.mkdir()
    (local_input / "a.pdf").write_bytes(b"pdf")

    result = _run_launcher(
        "--input",
        "local-in",
        "--output",
        "local-out",
        "--model-version",
        "pipeline",
        "--",
        "--no-such-arg",
        cwd=runner_dir,
    )
    assert result.returncode != 0
    assert "unrecognized arguments:" in result.stderr
    assert "--no-such-arg" in result.stderr


def test_launcher_handles_paths_with_spaces_and_extra_args(tmp_path: Path) -> None:
    runner_dir = tmp_path / "runner box"
    input_dir = runner_dir / "in box"
    output_dir = runner_dir / "out box"
    runner_dir.mkdir(parents=True)
    input_dir.mkdir()
    (input_dir / "a.pdf").write_bytes(b"pdf")

    result = _run_launcher(
        "--input",
        str(input_dir),
        "--output",
        str(output_dir),
        "--model-version",
        "pipeline",
        "--",
        "--no-such-arg",
        cwd=runner_dir,
    )
    assert result.returncode != 0
    assert "unrecognized arguments:" in result.stderr
    assert "--no-such-arg" in result.stderr
    assert "Input directory does not exist" not in result.stderr


def test_launcher_forwards_extra_args_to_cli(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    (input_dir / "a.pdf").write_bytes(b"pdf")

    result = _run_launcher(
        "--input",
        str(input_dir),
        "--output",
        str(output_dir),
        "--",
        "--no-such-arg",
    )
    assert result.returncode != 0
    assert "unrecognized arguments:" in result.stderr
    assert "--no-such-arg" in result.stderr
