from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mineru_batch_cli.http_client import HttpClient, HttpClientError


class MineruClientError(ValueError):
    pass


@dataclass(frozen=True)
class UploadItem:
    path: Path
    data_id: str


@dataclass(frozen=True)
class UploadResult:
    data_id: str
    status: str
    error: str | None = None


@dataclass(frozen=True)
class UploadBatchResult:
    batch_id: str
    results: list[UploadResult]


class MineruClient:
    def __init__(self, http_client: HttpClient, *, api_base_url: str, api_token: str) -> None:
        self._http: HttpClient = http_client
        self._api_base_url: str = api_base_url.rstrip("/")
        self._api_token: str = api_token

    def upload_local_files_batch(self, items: list[UploadItem]) -> UploadBatchResult:
        if not items:
            raise MineruClientError("No files provided for upload")

        request_items = [{"name": item.path.name, "data_id": item.data_id} for item in items]
        endpoint = f"{self._api_base_url}/file-urls/batch"
        try:
            response = self._http.request(
                "POST",
                endpoint,
                headers={"Authorization": f"Bearer {self._api_token}"},
                json_body={"files": request_items},
            )
        except HttpClientError as exc:
            raise MineruClientError(f"Failed to create upload batch: {exc}") from exc

        if response.status_code != 200:
            raise MineruClientError(
                f"Upload batch creation failed with status {response.status_code}"
            )

        payload = _decode_json(response.body)
        code = payload.get("code")
        msg = payload.get("msg")
        trace_id = payload.get("trace_id")
        if isinstance(code, int) and code != 0:
            detail = f"Upload batch rejected: code={code}"
            if isinstance(msg, str) and msg.strip():
                detail += f", msg={msg.strip()}"
            if isinstance(trace_id, str) and trace_id.strip():
                detail += f", trace_id={trace_id.strip()}"
            raise MineruClientError(detail)

        data = payload.get("data")
        if not isinstance(data, dict):
            raise MineruClientError("Missing data in upload batch response")

        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls")
        if not isinstance(batch_id, str) or not isinstance(file_urls, list):
            raise MineruClientError("Invalid upload batch response schema")

        url_by_data_id = _map_upload_urls(items, file_urls)

        results: list[UploadResult] = []
        for item in items:
            upload_url = url_by_data_id.get(item.data_id)
            if upload_url is None:
                results.append(
                    UploadResult(
                        data_id=item.data_id,
                        status="upload_failed",
                        error="missing signed upload URL",
                    )
                )
                continue

            try:
                content = item.path.read_bytes()
            except OSError as exc:
                results.append(
                    UploadResult(
                        data_id=item.data_id,
                        status="upload_failed",
                        error=f"read failed: {exc}",
                    )
                )
                continue

            try:
                put_response = self._http.request(
                    "PUT",
                    upload_url,
                    headers={"Content-Type": ""},
                    data=content,
                )
            except HttpClientError as exc:
                detail = f"upload request failed: {exc}"
                if exc.response_body:
                    detail += f"; response_body={exc.response_body}"
                results.append(
                    UploadResult(
                        data_id=item.data_id,
                        status="upload_failed",
                        error=detail,
                    )
                )
                continue

            if 200 <= put_response.status_code < 300:
                results.append(UploadResult(data_id=item.data_id, status="uploaded"))
            else:
                results.append(
                    UploadResult(
                        data_id=item.data_id,
                        status="upload_failed",
                        error=f"upload status {put_response.status_code}",
                    )
                )

        return UploadBatchResult(batch_id=batch_id, results=results)


def _map_upload_urls(items: list[UploadItem], file_urls: list[object]) -> dict[str, str]:
    url_by_data_id: dict[str, str] = {}

    for idx, row in enumerate(file_urls):
        if isinstance(row, str):
            if idx < len(items):
                url_by_data_id[items[idx].data_id] = row
            continue

        if not isinstance(row, dict):
            continue

        data_id = row.get("data_id")
        file_url = row.get("file_url")
        if isinstance(data_id, str) and isinstance(file_url, str):
            url_by_data_id[data_id] = file_url
            continue

        if isinstance(file_url, str) and idx < len(items):
            url_by_data_id[items[idx].data_id] = file_url

    return url_by_data_id


def _decode_json(body: bytes) -> dict[str, object]:
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MineruClientError("Invalid JSON response") from exc
    if not isinstance(decoded, dict):
        raise MineruClientError("Invalid JSON response shape")
    return decoded
