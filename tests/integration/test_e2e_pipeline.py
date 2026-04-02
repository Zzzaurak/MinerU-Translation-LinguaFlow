from __future__ import annotations

import json
import io
import zipfile
from pathlib import Path

from mineru_batch_cli.cli import main
from mineru_batch_cli.http_client import HttpClient, HttpResponse


def _zip_bytes(markdown: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as archive:
        archive.writestr("full.md", markdown)
        archive.writestr("images/kept.png", b"img")
    return buf.getvalue()


def _patch_http(monkeypatch, fail_upload_for_name: str | None = None):
    state: dict[str, object] = {"uploaded": [], "name_to_data_id": {}}

    def fake_request(
        _self: HttpClient,
        method: str,
        url: str,
        *,
        headers=None,
        data=None,
        json_body=None,
    ) -> HttpResponse:
        if method == "POST" and url.endswith("/file-urls/batch") and isinstance(json_body, dict):
            files = json_body.get("files", [])
            file_urls = []
            for row in files if isinstance(files, list) else []:
                if not isinstance(row, dict):
                    continue
                data_id = str(row.get("data_id"))
                name = str(row.get("name"))
                mapping = state.get("name_to_data_id")
                if isinstance(mapping, dict):
                    mapping[name] = data_id
                file_urls.append({"data_id": data_id, "file_url": f"https://upload/{name}"})
            body = json.dumps({"data": {"batch_id": "batch-e2e", "file_urls": file_urls}}).encode("utf-8")
            return HttpResponse(status_code=200, body=body, headers={})

        if method == "PUT" and url.startswith("https://upload/"):
            name = url.rsplit("/", 1)[-1]
            if fail_upload_for_name is not None and name == fail_upload_for_name:
                return HttpResponse(status_code=500, body=b"", headers={})
            uploaded = state.get("uploaded")
            if isinstance(uploaded, list):
                uploaded.append(name)
            return HttpResponse(status_code=200, body=b"", headers={})

        if method == "GET" and "/extract-results/batch/" in url:
            rows = []
            uploaded = state.get("uploaded")
            mapping = state.get("name_to_data_id")
            if isinstance(uploaded, list) and isinstance(mapping, dict):
                for name in uploaded:
                    if not isinstance(name, str):
                        continue
                    data_id = mapping.get(name)
                    if not isinstance(data_id, str):
                        continue
                    rows.append(
                        {
                            "data_id": data_id,
                            "state": "done",
                            "full_zip_url": f"https://zip/{name}",
                        }
                    )
            return HttpResponse(
                status_code=200,
                body=json.dumps({"data": {"extract_result": rows}}).encode("utf-8"),
                headers={},
            )

        if method == "GET" and url.startswith("https://zip/"):
            return HttpResponse(status_code=200, body=_zip_bytes("![img](images/kept.png)\n"), headers={})

        return HttpResponse(status_code=404, body=b"", headers={})

    monkeypatch.setattr(HttpClient, "request", fake_request)


def _patch_http_done_without_zip(monkeypatch):
    state: dict[str, object] = {"name_to_data_id": {}}

    def fake_request(
        _self: HttpClient,
        method: str,
        url: str,
        *,
        headers=None,
        data=None,
        json_body=None,
    ) -> HttpResponse:
        if method == "POST" and url.endswith("/file-urls/batch") and isinstance(json_body, dict):
            files = json_body.get("files", [])
            file_urls = []
            for row in files if isinstance(files, list) else []:
                if not isinstance(row, dict):
                    continue
                data_id = str(row.get("data_id"))
                name = str(row.get("name"))
                mapping = state.get("name_to_data_id")
                if isinstance(mapping, dict):
                    mapping[name] = data_id
                file_urls.append({"data_id": data_id, "file_url": f"https://upload/{name}"})
            return HttpResponse(
                status_code=200,
                body=json.dumps({"data": {"batch_id": "batch-zless", "file_urls": file_urls}}).encode("utf-8"),
                headers={},
            )
        if method == "PUT" and url.startswith("https://upload/"):
            return HttpResponse(status_code=200, body=b"", headers={})
        if method == "GET" and "/extract-results/batch/" in url:
            mapping = state.get("name_to_data_id")
            rows = []
            if isinstance(mapping, dict):
                for data_id in mapping.values():
                    if not isinstance(data_id, str):
                        continue
                    rows.append({"data_id": data_id, "state": "done"})
            return HttpResponse(
                status_code=200,
                body=json.dumps({"data": {"extract_result": rows}}).encode("utf-8"),
                headers={},
            )
        return HttpResponse(status_code=404, body=b"", headers={})

    monkeypatch.setattr(HttpClient, "request", fake_request)


def test_e2e_pipeline_success(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    (input_dir / "doc-a.pdf").write_bytes(b"a")
    (input_dir / "doc-b.pdf").write_bytes(b"b")

    monkeypatch.setenv("MINERU_API_TOKEN", "test-token")
    _patch_http(monkeypatch)

    exit_code = main(
        [
            "run",
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
            "--model-version",
            "pipeline",
            "--continue-on-error",
            "true",
        ]
    )

    assert exit_code == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total"] == 2
    assert manifest["succeeded"] == 2
    assert manifest["failed"] == 0
    assert len(manifest["items"]) == 2


def test_one_failure_batch_continues(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    (input_dir / "doc-ok.pdf").write_bytes(b"ok")
    (input_dir / "doc-fail.pdf").write_bytes(b"fail")

    monkeypatch.setenv("MINERU_API_TOKEN", "test-token")
    _patch_http(monkeypatch, fail_upload_for_name="doc-fail.pdf")

    exit_code = main(
        [
            "run",
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
            "--model-version",
            "pipeline",
            "--continue-on-error",
            "true",
        ]
    )

    assert exit_code == 2
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["failed"] == 1
    assert manifest["succeeded"] == 1


def test_done_without_zip_url_is_failed(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    (input_dir / "doc-a.pdf").write_bytes(b"a")

    monkeypatch.setenv("MINERU_API_TOKEN", "test-token")
    _patch_http_done_without_zip(monkeypatch)

    exit_code = main(
        [
            "run",
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
            "--model-version",
            "pipeline",
            "--continue-on-error",
            "true",
        ]
    )

    assert exit_code == 1
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["failed"] == 1
    assert manifest["items"][0]["error_code"] == "poll_missing_zip_url"
