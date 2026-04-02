from __future__ import annotations

from pathlib import Path

from mineru_batch_cli.http_client import HttpClient, HttpResponse
from mineru_batch_cli.mineru_client import MineruClient, MineruClientError, UploadItem


def test_signed_put_flow(tmp_path: Path) -> None:
    file_a = tmp_path / "a.pdf"
    file_b = tmp_path / "b.pdf"
    file_a.write_bytes(b"A")
    file_b.write_bytes(b"B")

    calls: list[tuple[str, str]] = []

    def fake_request(
        method: str,
        url: str,
        headers: dict[str, str],
        data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        calls.append((method, url))
        if method == "POST" and url.endswith("/file-urls/batch"):
            assert headers.get("Authorization") == "Bearer test-token"
            return HttpResponse(
                status_code=200,
                body=(
                    b'{"data":{"batch_id":"batch-1","file_urls":['
                    b'{"data_id":"id-a","file_url":"https://upload/a"},'
                    b'{"data_id":"id-b","file_url":"https://upload/b"}'
                    b"]}}"
                ),
                headers={},
            )
        if method == "PUT" and url in {"https://upload/a", "https://upload/b"}:
            assert data in {b"A", b"B"}
            return HttpResponse(status_code=200, body=b"", headers={})
        raise AssertionError(f"Unexpected request {method} {url}")

    client = MineruClient(
        HttpClient(request_func=fake_request),
        api_base_url="https://mineru.net/api/v4",
        api_token="test-token",
    )
    result = client.upload_local_files_batch(
        [
            UploadItem(path=file_a, data_id="id-a"),
            UploadItem(path=file_b, data_id="id-b"),
        ]
    )

    assert result.batch_id == "batch-1"
    assert [item.status for item in result.results] == ["uploaded", "uploaded"]
    assert calls[0] == ("POST", "https://mineru.net/api/v4/file-urls/batch")


def test_partial_upload_failure_recorded(tmp_path: Path) -> None:
    file_a = tmp_path / "a.pdf"
    file_b = tmp_path / "b.pdf"
    file_a.write_bytes(b"A")
    file_b.write_bytes(b"B")

    def fake_request(
        method: str,
        url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        if method == "POST":
            return HttpResponse(
                status_code=200,
                body=(
                    b'{"data":{"batch_id":"batch-2","file_urls":['
                    b'{"data_id":"id-a","file_url":"https://upload/a"},'
                    b'{"data_id":"id-b","file_url":"https://upload/b"}'
                    b"]}}"
                ),
                headers={},
            )
        if method == "PUT" and url == "https://upload/a":
            return HttpResponse(status_code=500, body=b"error", headers={})
        if method == "PUT" and url == "https://upload/b":
            return HttpResponse(status_code=200, body=b"", headers={})
        raise AssertionError(f"Unexpected request {method} {url}")

    client = MineruClient(
        HttpClient(request_func=fake_request),
        api_base_url="https://mineru.net/api/v4",
        api_token="test-token",
    )
    result = client.upload_local_files_batch(
        [
            UploadItem(path=file_a, data_id="id-a"),
            UploadItem(path=file_b, data_id="id-b"),
        ]
    )

    assert result.batch_id == "batch-2"
    statuses = {item.data_id: item.status for item in result.results}
    assert statuses["id-a"] == "upload_failed"
    assert statuses["id-b"] == "uploaded"


def test_signed_put_flow_supports_string_url_array(tmp_path: Path) -> None:
    file_a = tmp_path / "a.pdf"
    file_b = tmp_path / "b.pdf"
    file_a.write_bytes(b"A")
    file_b.write_bytes(b"B")

    calls: list[tuple[str, str]] = []

    def fake_request(
        method: str,
        url: str,
        headers: dict[str, str],
        data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        calls.append((method, url))
        if method == "POST" and url.endswith("/file-urls/batch"):
            assert headers.get("Authorization") == "Bearer test-token"
            return HttpResponse(
                status_code=200,
                body=(
                    b'{"code":0,"msg":"ok","trace_id":"t1","data":{'
                    b'"batch_id":"batch-3","file_urls":['
                    b'"https://upload/a","https://upload/b"'
                    b"]}}"
                ),
                headers={},
            )
        if method == "PUT" and url in {"https://upload/a", "https://upload/b"}:
            assert data in {b"A", b"B"}
            return HttpResponse(status_code=200, body=b"", headers={})
        raise AssertionError(f"Unexpected request {method} {url}")

    client = MineruClient(
        HttpClient(request_func=fake_request),
        api_base_url="https://mineru.net/api/v4",
        api_token="test-token",
    )
    result = client.upload_local_files_batch(
        [
            UploadItem(path=file_a, data_id="id-a"),
            UploadItem(path=file_b, data_id="id-b"),
        ]
    )

    assert result.batch_id == "batch-3"
    assert [item.status for item in result.results] == ["uploaded", "uploaded"]
    assert calls[0] == ("POST", "https://mineru.net/api/v4/file-urls/batch")


def test_upload_batch_surfaces_nonzero_code_with_context(tmp_path: Path) -> None:
    file_a = tmp_path / "a.pdf"
    file_a.write_bytes(b"A")

    def fake_request(
        method: str,
        url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        if method == "POST" and url.endswith("/file-urls/batch"):
            return HttpResponse(
                status_code=200,
                body=(
                    b'{"code":-60001,"msg":"failed to generate upload URL",'
                    b'"trace_id":"trace-xyz","data":{"batch_id":"batch-x","file_urls":[]}}'
                ),
                headers={},
            )
        raise AssertionError(f"Unexpected request {method} {url}")

    client = MineruClient(
        HttpClient(request_func=fake_request),
        api_base_url="https://mineru.net/api/v4",
        api_token="test-token",
    )

    try:
        client.upload_local_files_batch([UploadItem(path=file_a, data_id="id-a")])
        raise AssertionError("Expected MineruClientError")
    except MineruClientError as exc:
        message = str(exc)
        assert "code=-60001" in message
        assert "failed to generate upload URL" in message
        assert "trace_id=trace-xyz" in message
