from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from mineru_batch_cli.http_client import HttpClient, HttpClientError


class ArtifactError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactFetchResult:
    data_id: str
    status: str
    extracted_dir: Path | None = None
    error: str | None = None


def fetch_and_extract_artifacts(
    http_client: HttpClient,
    *,
    items: list[dict[str, str]],
    output_root: Path,
) -> list[ArtifactFetchResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[ArtifactFetchResult] = []

    for item in items:
        data_id = item.get("data_id", "")
        state = item.get("state")
        zip_url = item.get("full_zip_url")

        if not data_id:
            continue
        if state != "done" or not zip_url:
            results.append(
                ArtifactFetchResult(
                    data_id=data_id,
                    status="artifact_missing",
                    error="missing done state or full_zip_url",
                )
            )
            continue

        try:
            response = http_client.request("GET", zip_url)
        except HttpClientError as exc:
            results.append(
                ArtifactFetchResult(
                    data_id=data_id,
                    status="artifact_download_failed",
                    error=str(exc),
                )
            )
            continue

        if response.status_code != 200 or not response.body:
            results.append(
                ArtifactFetchResult(
                    data_id=data_id,
                    status="artifact_download_failed",
                    error=f"download status {response.status_code}",
                )
            )
            continue

        target_dir = output_root / data_id
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            _safe_extract_zip(response.body, target_dir)
        except ArtifactError as exc:
            results.append(
                ArtifactFetchResult(
                    data_id=data_id,
                    status="artifact_corrupt",
                    error=str(exc),
                )
            )
            continue

        results.append(
            ArtifactFetchResult(
                data_id=data_id,
                status="artifact_ready",
                extracted_dir=target_dir,
            )
        )

    return results


def _safe_extract_zip(content: bytes, target_dir: Path) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            if not names:
                raise ArtifactError("empty zip")
            resolved_target = target_dir.resolve()
            for member in names:
                member_path = (target_dir / member).resolve()
                try:
                    member_path.relative_to(resolved_target)
                except ValueError as exc:
                    raise ArtifactError("zip slip detected")
                if member.startswith("/") or ".." in Path(member).parts:
                    raise ArtifactError("zip slip detected")
            archive.extractall(target_dir)
    except zipfile.BadZipFile as exc:
        raise ArtifactError("corrupted zip") from exc
