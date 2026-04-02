from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast


ALLOWED_MODEL_VERSIONS = ("pipeline", "vlm", "MinerU-HTML")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RunConfig:
    api_token: str
    api_base_url: str
    model_version: str
    poll_interval_sec: float
    max_poll_min: float
    retry_max: int


def load_run_config(
    args: argparse.Namespace,
    env: dict[str, str] | None = None,
    config_path: str | os.PathLike[str] | None = None,
) -> RunConfig:
    env_vars = os.environ if env is None else env
    json_config = _load_json_config(config_path)

    model_version = _coalesce_str(
        json_config.get("model_version"),
        getattr(args, "model_version", None),
        None,
        "",
    )
    if model_version not in ALLOWED_MODEL_VERSIONS:
        raise ConfigError(
            "model-version must be one of: pipeline, vlm, MinerU-HTML"
        )

    api_token = _coalesce_str(
        json_config.get("api_token"),
        getattr(args, "api_token", None),
        env_vars.get("MINERU_API_TOKEN"),
        "",
    )
    if not api_token:
        raise ConfigError("Missing required API token: set MINERU_API_TOKEN")

    api_base_url = _coalesce_str(
        json_config.get("api_base_url"),
        getattr(args, "api_base_url", None),
        env_vars.get("MINERU_API_BASE_URL"),
        "https://mineru.net/api/v4",
    )

    poll_interval_sec = _coalesce_positive_float(
        json_config.get("poll_interval_sec"),
        getattr(args, "poll_interval_sec", None),
        env_vars.get("MINERU_POLL_INTERVAL_SEC"),
        5.0,
        name="poll-interval-sec",
    )
    max_poll_min = _coalesce_positive_float(
        json_config.get("max_poll_min"),
        getattr(args, "max_poll_min", None),
        env_vars.get("MINERU_MAX_POLL_MIN"),
        30.0,
        name="max-poll-min",
    )
    retry_max = _coalesce_positive_int(
        json_config.get("retry_max"),
        getattr(args, "retry_max", None),
        env_vars.get("MINERU_RETRY_MAX"),
        3,
        name="retry-max",
    )

    return RunConfig(
        api_token=api_token,
        api_base_url=api_base_url,
        model_version=model_version,
        poll_interval_sec=poll_interval_sec,
        max_poll_min=max_poll_min,
        retry_max=retry_max,
    )


def _coalesce_str(
    json_value: object | None,
    cli_value: object,
    env_value: str | None,
    default: str,
) -> str:
    for raw in (json_value, cli_value, env_value):
        if _is_unset(raw):
            continue
        value = str(raw).strip()
        if value:
            return value
    return default


def _coalesce_positive_float(
    json_value: object | None,
    cli_value: object,
    env_value: str | None,
    default: float,
    *,
    name: str,
) -> float:
    raw = _pick_raw(json_value, cli_value, env_value)
    if raw is None:
        value = default
    else:
        try:
            value = float(str(raw))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive number")
    return value


def _coalesce_positive_int(
    json_value: object | None,
    cli_value: object,
    env_value: str | None,
    default: int,
    *,
    name: str,
) -> int:
    raw = _pick_raw(json_value, cli_value, env_value)
    if raw is None:
        value = default
    else:
        try:
            value = int(str(raw))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return value


def _pick_raw(
    json_value: object | None,
    cli_value: object,
    env_value: str | None,
) -> object | None:
    for raw in (json_value, cli_value, env_value):
        if _is_unset(raw):
            continue
        return raw
    return None


def _is_unset(raw: object | None) -> bool:
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip() == ""
    return False


def _load_json_config(config_path: str | os.PathLike[str] | None) -> dict[str, object]:
    path = _resolve_config_path(config_path)
    is_explicit = config_path is not None

    if not path.exists():
        if is_explicit:
            raise ConfigError(f"Config file not found: {path}")
        return {}

    try:
        with path.open("r", encoding="utf-8") as fp:
            loaded = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Failed to read config file: {path}") from exc

    if not isinstance(loaded, dict):
        raise ConfigError(f"Config file must be a JSON object: {path}")

    loaded_obj = cast(dict[str, object], loaded)

    return {
        "api_token": loaded_obj.get("api_token"),
        "api_base_url": loaded_obj.get("api_base_url"),
        "model_version": loaded_obj.get("model_version"),
        "poll_interval_sec": loaded_obj.get("poll_interval_sec"),
        "max_poll_min": loaded_obj.get("max_poll_min"),
        "retry_max": loaded_obj.get("retry_max"),
    }


def _resolve_config_path(config_path: str | os.PathLike[str] | None) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser()
    return Path(__file__).resolve().parents[2] / "mineru.config.json"
