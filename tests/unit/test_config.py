from __future__ import annotations

# pyright: reportMissingImports=false

import argparse
from pathlib import Path
import re

import pytest

from mineru_batch_cli.cli import main
from mineru_batch_cli import config as config_module
from mineru_batch_cli.config import ConfigError, load_run_config, load_translate_config


@pytest.fixture(autouse=True)
def _isolate_default_project_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing_default = tmp_path / "mineru.config.json"

    def _resolve(config_path):
        if config_path is not None:
            return Path(config_path).expanduser()
        return missing_default

    monkeypatch.setattr(config_module, "_resolve_config_path", _resolve)


def _args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "model_version": "pipeline",
        "api_token": None,
        "api_base_url": None,
        "poll_interval_sec": None,
        "max_poll_min": None,
        "retry_max": None,
        "translation_enabled": None,
        "translation_api_base_url": None,
        "translation_api_key": None,
        "translation_model": None,
        "translation_target_language": None,
        "translation_timeout_sec": None,
        "translation_retry_max": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_load_run_config_uses_env_when_cli_absent() -> None:
    cfg = load_run_config(
        _args(),
        env={
            "MINERU_API_TOKEN": "env-token",
            "MINERU_API_BASE_URL": "https://env.example",
            "MINERU_POLL_INTERVAL_SEC": "2.5",
            "MINERU_MAX_POLL_MIN": "15",
            "MINERU_RETRY_MAX": "7",
            "MINERU_TRANSLATION_ENABLED": "true",
            "MINERU_TRANSLATION_API_BASE_URL": "https://llm.example/v1",
            "MINERU_TRANSLATION_API_KEY": "env-trans-key",
            "MINERU_TRANSLATION_MODEL": "gpt-4.1-mini",
            "MINERU_TRANSLATION_TARGET_LANGUAGE": "zh-CN",
            "MINERU_TRANSLATION_TIMEOUT_SEC": "20",
            "MINERU_TRANSLATION_RETRY_MAX": "4",
        },
    )

    assert cfg.api_token == "env-token"
    assert cfg.api_base_url == "https://env.example"
    assert cfg.poll_interval_sec == 2.5
    assert cfg.max_poll_min == 15.0
    assert cfg.retry_max == 7
    assert cfg.translation_enabled is True
    assert cfg.translation_api_base_url == "https://llm.example/v1"
    assert cfg.translation_api_key == "env-trans-key"
    assert cfg.translation_model == "gpt-4.1-mini"
    assert cfg.translation_target_language == "zh-CN"
    assert cfg.translation_timeout_sec == 20.0
    assert cfg.translation_retry_max == 4


def test_load_run_config_cli_overrides_env() -> None:
    cfg = load_run_config(
        _args(
            api_token="cli-token",
            api_base_url="https://cli.example",
            poll_interval_sec=9,
            max_poll_min=21,
            retry_max=5,
            model_version="vlm",
        ),
        env={
            "MINERU_API_TOKEN": "env-token",
            "MINERU_API_BASE_URL": "https://env.example",
            "MINERU_POLL_INTERVAL_SEC": "2",
            "MINERU_MAX_POLL_MIN": "10",
            "MINERU_RETRY_MAX": "1",
        },
    )

    assert cfg.api_token == "cli-token"
    assert cfg.api_base_url == "https://cli.example"
    assert cfg.poll_interval_sec == 9.0
    assert cfg.max_poll_min == 21.0
    assert cfg.retry_max == 5
    assert cfg.model_version == "vlm"


def test_load_run_config_uses_defaults_when_env_missing() -> None:
    cfg = load_run_config(
        _args(api_token="cli-token", model_version="MinerU-HTML"),
        env={},
    )

    assert cfg.api_base_url == "https://mineru.net/api/v4"
    assert cfg.poll_interval_sec == 5.0
    assert cfg.max_poll_min == 30.0
    assert cfg.retry_max == 3
    assert cfg.model_version == "MinerU-HTML"
    assert cfg.translation_enabled is False
    assert cfg.translation_api_base_url == "https://api.openai.com/v1"
    assert cfg.translation_api_key == ""
    assert cfg.translation_model == "gpt-4o-mini"
    assert cfg.translation_target_language == "zh-CN"
    assert cfg.translation_timeout_sec == 30.0
    assert cfg.translation_retry_max == 3


def test_load_run_config_raises_when_token_missing() -> None:
    with pytest.raises(ConfigError, match="Missing required API token"):
        load_run_config(_args(), env={})


def test_load_run_config_reads_json_when_config_path_provided(tmp_path) -> None:
    config_file = tmp_path / "custom.json"
    config_file.write_text(
        """
{
  "api_token": "json-token",
  "api_base_url": "https://json.example",
  "model_version": "vlm",
  "poll_interval_sec": 4,
  "max_poll_min": 12,
  "retry_max": 6,
  "translation_enabled": true,
  "translation_api_base_url": "https://llm-json.example/v1",
  "translation_api_key": "json-key",
  "translation_model": "gpt-4.1",
  "translation_target_language": "zh-TW",
  "translation_timeout_sec": 18,
  "translation_retry_max": 5
}
""".strip(),
        encoding="utf-8",
    )

    cfg = load_run_config(
        _args(model_version=None),
        env={},
        config_path=config_file,
    )

    assert cfg.api_token == "json-token"
    assert cfg.api_base_url == "https://json.example"
    assert cfg.model_version == "vlm"
    assert cfg.poll_interval_sec == 4.0
    assert cfg.max_poll_min == 12.0
    assert cfg.retry_max == 6
    assert cfg.translation_enabled is True
    assert cfg.translation_api_base_url == "https://llm-json.example/v1"
    assert cfg.translation_api_key == "json-key"
    assert cfg.translation_model == "gpt-4.1"
    assert cfg.translation_target_language == "zh-TW"
    assert cfg.translation_timeout_sec == 18.0
    assert cfg.translation_retry_max == 5


def test_load_run_config_uses_json_first_per_field_and_blank_fallback(tmp_path) -> None:
    config_file = tmp_path / "precedence.json"
    config_file.write_text(
        """
{
  "api_token": "json-token",
  "api_base_url": "   ",
  "model_version": "vlm",
  "poll_interval_sec": "   ",
  "max_poll_min": 9,
  "retry_max": 2,
  "translation_enabled": " ",
  "translation_model": "gpt-4.1",
  "translation_timeout_sec": " ",
  "translation_retry_max": 9
}
""".strip(),
        encoding="utf-8",
    )

    cfg = load_run_config(
        _args(
            api_token="cli-token",
            api_base_url="https://cli.example",
            model_version="pipeline",
            poll_interval_sec=8,
            max_poll_min=16,
            retry_max=4,
        ),
        env={
            "MINERU_API_TOKEN": "env-token",
            "MINERU_API_BASE_URL": "https://env.example",
            "MINERU_POLL_INTERVAL_SEC": "3",
            "MINERU_MAX_POLL_MIN": "11",
            "MINERU_RETRY_MAX": "5",
            "MINERU_TRANSLATION_ENABLED": "true",
            "MINERU_TRANSLATION_API_KEY": "env-trans-key",
            "MINERU_TRANSLATION_TIMEOUT_SEC": "25",
        },
        config_path=config_file,
    )

    assert cfg.api_token == "json-token"
    assert cfg.model_version == "vlm"
    assert cfg.max_poll_min == 9.0
    assert cfg.retry_max == 2
    assert cfg.api_base_url == "https://cli.example"
    assert cfg.poll_interval_sec == 8.0
    assert cfg.translation_enabled is True
    assert cfg.translation_model == "gpt-4.1"
    assert cfg.translation_api_key == "env-trans-key"
    assert cfg.translation_timeout_sec == 25.0
    assert cfg.translation_retry_max == 9


def test_load_run_config_invalid_numeric_falls_through_blank_json_cli_then_fails_env(
    tmp_path,
) -> None:
    config_file = tmp_path / "invalid-numeric.json"
    config_file.write_text(
        """
{
  "api_token": "json-token",
  "model_version": "pipeline",
  "poll_interval_sec": "  "
}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigError, match="poll-interval-sec must be a positive number"
    ):
        load_run_config(
            _args(poll_interval_sec="   "),
            env={"MINERU_POLL_INTERVAL_SEC": "abc"},
            config_path=config_file,
        )


def test_load_run_config_translation_requires_key_when_enabled() -> None:
    with pytest.raises(ConfigError, match="Missing required translation API key"):
        load_run_config(
            _args(api_token="cli-token", translation_enabled=True),
            env={},
        )


def test_load_run_config_translation_boolean_validation() -> None:
    with pytest.raises(ConfigError, match="translation-enabled must be a boolean"):
        load_run_config(
            _args(api_token="cli-token"),
            env={"MINERU_TRANSLATION_ENABLED": "maybe"},
        )


def test_load_run_config_translation_numeric_validation() -> None:
    with pytest.raises(
        ConfigError, match="translation-timeout-sec must be a positive number"
    ):
        load_run_config(
            _args(api_token="cli-token"),
            env={"MINERU_TRANSLATION_TIMEOUT_SEC": "0"},
        )

    with pytest.raises(
        ConfigError, match="translation-retry-max must be a positive integer"
    ):
        load_run_config(
            _args(api_token="cli-token"),
            env={"MINERU_TRANSLATION_RETRY_MAX": "0"},
        )


def test_load_run_config_translation_cli_overrides_env() -> None:
    cfg = load_run_config(
        _args(
            api_token="cli-token",
            translation_enabled="false",
            translation_api_base_url="https://cli-llm.example/v1",
            translation_api_key="cli-trans-key",
            translation_model="gpt-cli",
            translation_target_language="zh-CN",
            translation_timeout_sec="12",
            translation_retry_max="2",
        ),
        env={
            "MINERU_TRANSLATION_ENABLED": "true",
            "MINERU_TRANSLATION_API_BASE_URL": "https://env-llm.example/v1",
            "MINERU_TRANSLATION_API_KEY": "env-trans-key",
            "MINERU_TRANSLATION_MODEL": "gpt-env",
            "MINERU_TRANSLATION_TARGET_LANGUAGE": "zh-TW",
            "MINERU_TRANSLATION_TIMEOUT_SEC": "25",
            "MINERU_TRANSLATION_RETRY_MAX": "5",
        },
    )

    assert cfg.translation_enabled is False
    assert cfg.translation_api_base_url == "https://cli-llm.example/v1"
    assert cfg.translation_api_key == "cli-trans-key"
    assert cfg.translation_model == "gpt-cli"
    assert cfg.translation_target_language == "zh-CN"
    assert cfg.translation_timeout_sec == 12.0
    assert cfg.translation_retry_max == 2


def test_load_run_config_raises_when_explicit_config_path_missing(tmp_path) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(ConfigError, match=re.escape(str(missing_path))):
        load_run_config(_args(api_token="cli-token"), env={}, config_path=missing_path)


def test_load_run_config_raises_on_malformed_json_config(tmp_path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text('{"api_token": "json-token",', encoding="utf-8")

    with pytest.raises(ConfigError, match="Failed to read config file"):
        load_run_config(
            _args(model_version="pipeline"),
            env={},
            config_path=bad_file,
        )


def test_load_run_config_raises_on_non_object_json_config(tmp_path) -> None:
    bad_file = tmp_path / "bad-type.json"
    bad_file.write_text("[]", encoding="utf-8")

    with pytest.raises(ConfigError, match="Config file must be a JSON object"):
        load_run_config(
            _args(model_version="pipeline"),
            env={},
            config_path=bad_file,
        )


def test_load_run_config_skips_missing_default_project_config(
    monkeypatch, tmp_path
) -> None:
    missing_path = tmp_path / "mineru.config.json"
    monkeypatch.setattr(config_module, "_resolve_config_path", lambda _: missing_path)

    cfg = load_run_config(_args(api_token="cli-token"), env={})

    assert cfg.api_token == "cli-token"
    assert cfg.model_version == "pipeline"


def test_run_command_returns_non_zero_and_clear_error_when_token_missing(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)
    input_dir = tmp_path / "in"
    input_dir.mkdir()

    exit_code = main(
        [
            "run",
            "--input",
            str(input_dir),
            "--output",
            str(tmp_path / "out"),
            "--model-version",
            "pipeline",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Missing required API token" in captured.err


def test_load_translate_config_uses_env_when_cli_absent() -> None:
    cfg = load_translate_config(
        _args(),
        env={
            "MINERU_TRANSLATION_API_BASE_URL": "https://llm.example/v1",
            "MINERU_TRANSLATION_API_KEY": "env-trans-key",
            "MINERU_TRANSLATION_MODEL": "gpt-4.1-mini",
            "MINERU_TRANSLATION_TARGET_LANGUAGE": "zh-CN",
            "MINERU_TRANSLATION_TIMEOUT_SEC": "20",
            "MINERU_TRANSLATION_RETRY_MAX": "4",
        },
    )

    assert cfg.translation_api_base_url == "https://llm.example/v1"
    assert cfg.translation_api_key == "env-trans-key"
    assert cfg.translation_model == "gpt-4.1-mini"
    assert cfg.translation_target_language == "zh-CN"
    assert cfg.translation_timeout_sec == 20.0
    assert cfg.translation_retry_max == 4


def test_load_translate_config_uses_defaults_when_env_missing() -> None:
    cfg = load_translate_config(_args(), env={"MINERU_TRANSLATION_API_KEY": "k"})
    assert cfg.translation_api_base_url == "https://api.openai.com/v1"
    assert cfg.translation_model == "gpt-4o-mini"
    assert cfg.translation_target_language == "zh-CN"
    assert cfg.translation_timeout_sec == 30.0
    assert cfg.translation_retry_max == 3


def test_load_translate_config_requires_key() -> None:
    with pytest.raises(ConfigError, match="Missing required translation API key"):
        load_translate_config(_args(), env={})
