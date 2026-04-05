from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: bytes
    headers: dict[str, str]


class HttpClientError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retriable: bool = False,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code: int | None = status_code
        self.retriable: bool = retriable
        self.response_body: str | None = response_body


Transport = Callable[[str, str, dict[str, str], bytes | None, float], HttpResponse]
Sleep = Callable[[float], None]


class HttpClient:
    def __init__(
        self,
        *,
        timeout_sec: float = 30.0,
        retry_max: int = 3,
        request_func: Transport | None = None,
        sleep_func: Sleep = time.sleep,
    ) -> None:
        self._timeout_sec: float = timeout_sec
        self._retry_max: int = retry_max
        self._request_func: Transport = request_func or _default_request
        self._sleep_func: Sleep = sleep_func

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        json_body: dict[str, object] | None = None,
    ) -> HttpResponse:
        resolved_headers = {} if headers is None else dict(headers)
        body = data
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            resolved_headers.setdefault("Content-Type", "application/json")

        attempt = 0
        while True:
            try:
                response = self._request_func(
                    method.upper(),
                    url,
                    resolved_headers,
                    body,
                    self._timeout_sec,
                )
            except (TimeoutError, socket.timeout) as exc:
                err = HttpClientError(
                    "Network error: request timed out",
                    status_code=None,
                    retriable=True,
                )
            except HttpClientError as exc:
                err = exc
            else:
                err = None

            if err is not None:
                if err.retriable and attempt < self._retry_max:
                    self._sleep_func(_backoff_seconds(attempt))
                    attempt += 1
                    continue
                raise err

            status_code = response.status_code
            if 400 <= status_code < 500 and status_code != 429:
                body_preview = _response_body_preview(response.body)
                raise HttpClientError(
                    f"HTTP request failed with status {status_code}",
                    status_code=status_code,
                    retriable=False,
                    response_body=body_preview,
                )

            should_retry = status_code == 429 or status_code >= 500
            if should_retry and attempt < self._retry_max:
                self._sleep_func(_backoff_seconds(attempt))
                attempt += 1
                continue

            if should_retry:
                body_preview = _response_body_preview(response.body)
                raise HttpClientError(
                    f"HTTP request failed after retries with status {status_code}",
                    status_code=status_code,
                    retriable=True,
                    response_body=body_preview,
                )

            return response


def _backoff_seconds(attempt: int) -> float:
    return float(2**attempt)


def _response_body_preview(body: bytes, max_chars: int = 500) -> str | None:
    if not body:
        return None
    decoded = body.decode("utf-8", errors="replace").strip()
    if not decoded:
        return None
    if len(decoded) <= max_chars:
        return decoded
    return f"{decoded[:max_chars]}..."


def _default_request(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    timeout_sec: float,
) -> HttpResponse:
    req = urllib.request.Request(url=url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return HttpResponse(
                status_code=resp.getcode(),
                body=resp.read(),
                headers=dict(resp.headers.items()),
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(
            status_code=exc.code,
            body=exc.read(),
            headers=dict(exc.headers.items()) if exc.headers is not None else {},
        )
    except urllib.error.URLError as exc:
        raise HttpClientError(
            f"Network error: {exc.reason}",
            status_code=None,
            retriable=True,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise HttpClientError(
            "Network error: request timed out",
            status_code=None,
            retriable=True,
        ) from exc
