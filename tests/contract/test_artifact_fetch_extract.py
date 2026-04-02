from __future__ import annotations

import io
import zipfile
from pathlib import Path

from mineru_batch_cli.artifacts import fetch_and_extract_artifacts
from mineru_batch_cli.http_client import HttpClient, HttpResponse


def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_extract_success(tmp_path: Path) -> None:
    zip_bytes = _make_zip_bytes({"full.md": b"# hello", "images/a.png": b"img"})

    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        return HttpResponse(status_code=200, body=zip_bytes, headers={})

    results = fetch_and_extract_artifacts(
        HttpClient(request_func=fake_request),
        items=[{"data_id": "id-a", "state": "done", "full_zip_url": "https://zip/a"}],
        output_root=tmp_path,
    )

    assert len(results) == 1
    assert results[0].status == "artifact_ready"
    assert (tmp_path / "id-a" / "full.md").exists()
    assert (tmp_path / "id-a" / "images" / "a.png").exists()


def test_corrupt_zip_marked_failed(tmp_path: Path) -> None:
    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        return HttpResponse(status_code=200, body=b"not-a-zip", headers={})

    results = fetch_and_extract_artifacts(
        HttpClient(request_func=fake_request),
        items=[{"data_id": "id-a", "state": "done", "full_zip_url": "https://zip/a"}],
        output_root=tmp_path,
    )

    assert len(results) == 1
    assert results[0].status == "artifact_corrupt"
    assert results[0].error is not None


def test_zip_slip_detected(tmp_path: Path) -> None:
    zip_bytes = _make_zip_bytes({"../escape.txt": b"bad"})

    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        return HttpResponse(status_code=200, body=zip_bytes, headers={})

    results = fetch_and_extract_artifacts(
        HttpClient(request_func=fake_request),
        items=[{"data_id": "id-a", "state": "done", "full_zip_url": "https://zip/a"}],
        output_root=tmp_path,
    )

    assert len(results) == 1
    assert results[0].status == "artifact_corrupt"
