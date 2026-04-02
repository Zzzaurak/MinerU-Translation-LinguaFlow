from __future__ import annotations

from mineru_batch_cli.http_client import HttpClient, HttpResponse
from mineru_batch_cli.polling import PollingError, poll_batch_until_terminal


def test_poll_until_done_or_failed() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            return HttpResponse(
                status_code=200,
                body=b'{"data":{"extract_result":[{"data_id":"a","state":"running"}]}}',
                headers={},
            )
        return HttpResponse(
            status_code=200,
            body=(
                b'{"data":{"extract_result":['
                b'{"data_id":"a","state":"done","full_zip_url":"https://zip/a"},'
                b'{"data_id":"b","state":"failed","err_msg":"x"}'
                b']}}'
            ),
            headers={},
        )

    http_client = HttpClient(request_func=fake_request, sleep_func=sleeps.append)
    now_values = iter([0.0, 1.0])

    result = poll_batch_until_terminal(
        http_client,
        api_base_url="https://mineru.net/api/v4",
        api_token="token",
        batch_id="batch-1",
        poll_interval_sec=5,
        max_poll_min=1,
        now_func=lambda: next(now_values),
        sleep_func=sleeps.append,
    )

    assert [item.data_id for item in result] == ["a", "b"]
    assert [item.state for item in result] == ["done", "failed"]
    assert sleeps == [5]


def test_timeout_marks_unfinished_items() -> None:
    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        return HttpResponse(
            status_code=200,
            body=b'{"data":{"extract_result":[{"data_id":"a","state":"running"}]}}',
            headers={},
        )

    http_client = HttpClient(request_func=fake_request)
    now_values = iter([0.0, 61.0])

    result = poll_batch_until_terminal(
        http_client,
        api_base_url="https://mineru.net/api/v4",
        api_token="token",
        batch_id="batch-1",
        poll_interval_sec=5,
        max_poll_min=1,
        now_func=lambda: next(now_values),
        sleep_func=lambda _sec: None,
    )

    assert len(result) == 1
    assert result[0].data_id == "a"
    assert result[0].state == "timeout"


def test_timeout_with_no_items_raises() -> None:
    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        return HttpResponse(status_code=200, body=b'{"data":{"extract_result":[]}}', headers={})

    http_client = HttpClient(request_func=fake_request)
    now_values = iter([0.0, 61.0])

    try:
        poll_batch_until_terminal(
            http_client,
            api_base_url="https://mineru.net/api/v4",
            api_token="token",
            batch_id="batch-1",
            poll_interval_sec=5,
            max_poll_min=1,
            now_func=lambda: next(now_values),
            sleep_func=lambda _sec: None,
        )
    except PollingError as exc:
        assert "No pollable items" in str(exc)
    else:
        raise AssertionError("Expected PollingError when no items are returned before timeout")
