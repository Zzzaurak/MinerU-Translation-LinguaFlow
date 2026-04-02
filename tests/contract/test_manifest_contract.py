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
    return buf.getvalue()


def test_partial_success_exit_code_2(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    (input_dir / "ok.pdf").write_bytes(b"ok")
    (input_dir / "fail.pdf").write_bytes(b"fail")

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
                name_to_data_id = state.get("name_to_data_id")
                if isinstance(name_to_data_id, dict):
                    name_to_data_id[name] = data_id
                file_urls.append({"data_id": data_id, "file_url": f"https://upload/{name}"})
            body = json.dumps({"data": {"batch_id": "batch-1", "file_urls": file_urls}}).encode("utf-8")
            return HttpResponse(status_code=200, body=body, headers={})

        if method == "PUT" and url.startswith("https://upload/"):
            if "fail" in url:
                return HttpResponse(status_code=500, body=b"", headers={})
            uploaded = state.get("uploaded")
            if isinstance(uploaded, list):
                uploaded.append(url.rsplit("/", 1)[-1])
            return HttpResponse(status_code=200, body=b"", headers={})

        if method == "GET" and "/extract-results/batch/" in url:
            rows = []
            uploaded = state.get("uploaded")
            name_to_data_id = state.get("name_to_data_id")
            if isinstance(uploaded, list) and isinstance(name_to_data_id, dict):
                for name in uploaded:
                    if not isinstance(name, str):
                        continue
                    data_id = name_to_data_id.get(name)
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
            return HttpResponse(status_code=200, body=_zip_bytes("# doc\n"), headers={})

        return HttpResponse(status_code=404, body=b"", headers={})

    monkeypatch.setenv("MINERU_API_TOKEN", "test-token")
    monkeypatch.setattr(HttpClient, "request", fake_request)

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
    manifest_path = output_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["succeeded"] == 1
    assert payload["failed"] == 1


def test_verify_prints_manifest_ok_for_valid_manifest(tmp_path: Path, capsys) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-1",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "input_root": "/tmp/in",
                "output_root": "/tmp/out",
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "items": [
                    {
                        "input_path": "a.pdf",
                        "item_slug": "a-pdf",
                        "status": "succeeded",
                        "error_code": None,
                        "error_message": None,
                        "document_path": "items/a-pdf/document.md",
                        "images_count": 0,
                        "warnings": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["verify", "--manifest", str(manifest)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "MANIFEST_OK" in captured.out


def test_verify_rejects_invalid_item_schema(tmp_path: Path, capsys) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-1",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "input_root": "/tmp/in",
                "output_root": "/tmp/out",
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "items": [{"input_path": "a.pdf"}],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["verify", "--manifest", str(manifest)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing keys" in captured.err


def test_verify_rejects_wrong_item_field_types(tmp_path: Path, capsys) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "run-1",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:01Z",
                "input_root": "/tmp/in",
                "output_root": "/tmp/out",
                "total": 1,
                "succeeded": 1,
                "failed": 0,
                "items": [
                    {
                        "input_path": "a.pdf",
                        "item_slug": "a-pdf",
                        "status": "succeeded",
                        "error_code": None,
                        "error_message": None,
                        "document_path": "items/a-pdf/document.md",
                        "images_count": "wrong",
                        "warnings": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["verify", "--manifest", str(manifest)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "images_count must be an integer" in captured.err
