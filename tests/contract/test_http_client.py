from __future__ import annotations

import json

import pytest

from mineru_batch_cli.http_client import HttpClient, HttpClientError, HttpResponse


def test_retry_on_429_then_success() -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        calls.append(1)
        if len(calls) == 1:
            return HttpResponse(status_code=429, body=b"rate", headers={})
        return HttpResponse(status_code=200, body=b"ok", headers={})

    client = HttpClient(
        retry_max=3,
        request_func=fake_request,
        sleep_func=sleeps.append,
    )
    response = client.request("GET", "https://example.test")

    assert response.status_code == 200
    assert len(calls) == 2
    assert sleeps == [1.0]


def test_401_fail_fast() -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        calls.append(1)
        return HttpResponse(status_code=401, body=b"unauthorized", headers={})

    client = HttpClient(
        retry_max=3,
        request_func=fake_request,
        sleep_func=sleeps.append,
    )

    with pytest.raises(HttpClientError, match="status 401") as exc_info:
        client.request("GET", "https://example.test")

    assert exc_info.value.status_code == 401
    assert exc_info.value.retriable is False
    assert len(calls) == 1
    assert sleeps == []


def test_request_sets_json_content_type() -> None:
    captured: dict[str, object] = {}

    def fake_request(
        _method: str,
        _url: str,
        headers: dict[str, str],
        data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        captured["headers"] = headers
        captured["data"] = data
        return HttpResponse(status_code=200, body=b"ok", headers={})

    client = HttpClient(request_func=fake_request)
    client.request("POST", "https://example.test", json_body={"k": "v"})

    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers.get("Content-Type") == "application/json"

    data = captured["data"]
    assert isinstance(data, bytes)
    assert json.loads(data.decode("utf-8")) == {"k": "v"}
