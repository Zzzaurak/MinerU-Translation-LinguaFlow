from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable

from mineru_batch_cli.http_client import HttpClient, HttpClientError


class PollingError(ValueError):
    pass


TERMINAL_STATES = {"done", "failed", "timeout"}


@dataclass(frozen=True)
class PolledItem:
    data_id: str
    state: str
    full_zip_url: str | None
    err_msg: str | None


def poll_batch_until_terminal(
    http_client: HttpClient,
    *,
    api_base_url: str,
    api_token: str,
    batch_id: str,
    poll_interval_sec: float,
    max_poll_min: float,
    now_func: Callable[[], float] = time.monotonic,
    sleep_func: Callable[[float], None] = time.sleep,
) -> list[PolledItem]:
    endpoint = f"{api_base_url.rstrip('/')}/extract-results/batch/{batch_id}"
    started = now_func()
    last_items: dict[str, PolledItem] = {}

    while True:
        try:
            response = http_client.request(
                "GET",
                endpoint,
                headers={"Authorization": f"Bearer {api_token}"},
            )
        except HttpClientError as exc:
            raise PollingError(f"Batch polling request failed: {exc}") from exc

        payload = _decode_json(response.body)
        rows = _extract_rows(payload)
        for row in rows:
            item = _to_item(row)
            if item is not None:
                last_items[item.data_id] = item

        if last_items and all(item.state in TERMINAL_STATES for item in last_items.values()):
            return [last_items[key] for key in sorted(last_items.keys())]

        elapsed = now_func() - started
        if elapsed >= max_poll_min * 60:
            if not last_items:
                raise PollingError("No pollable items returned before timeout")
            return _mark_timeouts(last_items)

        sleep_func(poll_interval_sec)


def _decode_json(body: bytes) -> dict[str, object]:
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PollingError("Invalid polling response JSON") from exc
    if not isinstance(decoded, dict):
        raise PollingError("Invalid polling response shape")
    return decoded


def _extract_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    rows = data.get("extract_result")
    if not isinstance(rows, list):
        return []
    result: list[dict[str, object]] = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
    return result


def _to_item(row: dict[str, object]) -> PolledItem | None:
    data_id = row.get("data_id")
    state = row.get("state")
    if not isinstance(data_id, str) or not isinstance(state, str):
        return None

    full_zip_url = row.get("full_zip_url")
    err_msg = row.get("err_msg")
    return PolledItem(
        data_id=data_id,
        state=state,
        full_zip_url=full_zip_url if isinstance(full_zip_url, str) else None,
        err_msg=err_msg if isinstance(err_msg, str) else None,
    )


def _mark_timeouts(items: dict[str, PolledItem]) -> list[PolledItem]:
    result: list[PolledItem] = []
    for key in sorted(items.keys()):
        item = items[key]
        if item.state in TERMINAL_STATES:
            result.append(item)
            continue
        result.append(
            PolledItem(
                data_id=item.data_id,
                state="timeout",
                full_zip_url=item.full_zip_url,
                err_msg=item.err_msg,
            )
        )
    return result
