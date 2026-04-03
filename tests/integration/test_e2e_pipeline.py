from __future__ import annotations

import json
import io
import zipfile
from pathlib import Path

from mineru_batch_cli.cli import main
from mineru_batch_cli.http_client import HttpClient, HttpResponse
from mineru_batch_cli.translation_client import OpenAICompatibleTranslationAdapter


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


def _write_translation_config(path: Path, *, enabled: bool) -> Path:
    config = {
        "api_token": "test-token",
        "model_version": "pipeline",
        "translation_enabled": enabled,
        "translation_api_base_url": "https://llm.example/v1",
        "translation_api_key": "trans-key",
        "translation_model": "gpt-4.1-mini",
        "translation_target_language": "zh-CN",
        "translation_timeout_sec": 5,
        "translation_retry_max": 2,
    }
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


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


def test_pipeline_translation_enabled_writes_translated_document(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    config_path = tmp_path / "mineru.config.json"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    (input_dir / "doc-a.pdf").write_bytes(b"a")

    _patch_http(monkeypatch)
    calls: list[str] = []

    def fake_translate(self, markdown: str, *, target_language: str) -> str:
        calls.append(target_language)
        assert "kept.png" in markdown
        return markdown.replace("kept.png", "kept.png") + "\n\n翻译完成"

    monkeypatch.setattr(OpenAICompatibleTranslationAdapter, "translate_markdown", fake_translate)
    _write_translation_config(config_path, enabled=True)

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
            "--config",
            str(config_path),
        ]
    )

    assert exit_code == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    item = manifest["items"][0]
    assert item["translation_status"] == "succeeded"
    assert item["translated_document_path"] is not None
    translated_path = Path(item["translated_document_path"])
    assert translated_path.exists()
    assert "翻译完成" in translated_path.read_text(encoding="utf-8")
    assert calls == ["zh-CN"]


def test_pipeline_translation_failure_falls_back_to_original_document(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    config_path = tmp_path / "mineru.config.json"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    (input_dir / "doc-a.pdf").write_bytes(b"a")

    _patch_http(monkeypatch)

    def fake_translate_fail(self, markdown: str, *, target_language: str) -> str:
        raise ValueError("provider rejected")

    monkeypatch.setattr(OpenAICompatibleTranslationAdapter, "translate_markdown", fake_translate_fail)
    _write_translation_config(config_path, enabled=True)

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
            "--config",
            str(config_path),
        ]
    )

    assert exit_code == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    item = manifest["items"][0]
    assert item["status"] == "succeeded"
    assert item["document_path"] is not None
    assert item["translated_document_path"] is None
    assert item["translation_status"] == "failed"
    assert "provider rejected" in (item["translation_error"] or "")
    assert any("translation_failed" in warning for warning in item["warnings"])


def test_continue_on_error_false_stops_after_first_failure(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    (input_dir / "a-fail.pdf").write_bytes(b"a")
    (input_dir / "b-ok.pdf").write_bytes(b"b")

    monkeypatch.setenv("MINERU_API_TOKEN", "test-token")
    _patch_http(monkeypatch, fail_upload_for_name="a-fail.pdf")

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
            "false",
        ]
    )

    assert exit_code == 1
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["failed"] == 2
    assert manifest["succeeded"] == 0
    first = manifest["items"][0]
    second = manifest["items"][1]
    assert first["error_code"] == "upload_failed"
    assert second["error_code"] == "skipped_after_failure"
