from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _launcher_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return env


def test_launcher_help_prints_usage() -> None:
    repo = _repo_root()
    result = subprocess.run(
        ["bash", "scripts/run-mineru.sh", "--help"],
        cwd=repo,
        env=_launcher_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Usage: run-mineru.sh" in result.stdout


def test_launcher_fails_when_input_missing(tmp_path: Path) -> None:
    repo = _repo_root()
    missing = tmp_path / "missing-input"
    result = subprocess.run(
        [
            "bash",
            "scripts/run-mineru.sh",
            "--input",
            str(missing),
            "--output",
            str(tmp_path / "out"),
            "--model-version",
            "pipeline",
        ],
        cwd=repo,
        env=_launcher_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Input directory does not exist" in result.stderr


def test_launcher_command_invokes_shell_wrapper_help() -> None:
    repo = _repo_root()
    result = subprocess.run(
        ["bash", "scripts/run-mineru.command", "--help"],
        cwd=repo,
        env=_launcher_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Usage: run-mineru.sh" in result.stdout


def test_launcher_requires_executable_shell_script(tmp_path: Path) -> None:
    repo = _repo_root()
    sh_path = repo / "scripts" / "run-mineru.sh"
    original_mode = sh_path.stat().st_mode
    try:
        sh_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        result = subprocess.run(
            ["bash", "scripts/run-mineru.command", "--help"],
            cwd=repo,
            env=_launcher_env(),
            text=True,
            capture_output=True,
            input="\n",
            check=False,
        )
        assert result.returncode != 0
        assert "launcher script is not executable" in result.stderr
    finally:
        sh_path.chmod(original_mode)


def test_launcher_accepts_relative_input_from_non_repo_cwd(tmp_path: Path) -> None:
    repo = _repo_root()
    runner_dir = tmp_path / "runner"
    local_input = runner_dir / "local-in"
    local_output = runner_dir / "local-out"
    runner_dir.mkdir(parents=True)
    local_input.mkdir()
    (local_input / "a.pdf").write_bytes(b"pdf")

    result = subprocess.run(
        [
            "bash",
            str(repo / "scripts" / "run-mineru.sh"),
            "--input",
            "local-in",
            "--output",
            "local-out",
            "--model-version",
            "pipeline",
        ],
        cwd=runner_dir,
        env=_launcher_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode in {0, 1, 2}
    assert local_output.exists()


def test_launcher_forwards_extra_args_to_cli(tmp_path: Path) -> None:
    repo = _repo_root()
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    (input_dir / "a.pdf").write_bytes(b"pdf")

    result = subprocess.run(
        [
            "bash",
            str(repo / "scripts" / "run-mineru.sh"),
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
            "--",
            "--no-such-arg",
        ],
        cwd=repo,
        env=_launcher_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "--no-such-arg" in result.stderr
