from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


MANIFEST_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ManifestItem:
    input_path: str
    item_slug: str
    status: str
    error_code: str | None
    error_message: str | None
    document_path: str | None
    images_count: int
    warnings: list[str]


def build_manifest(
    *,
    run_id: str,
    started_at: str,
    finished_at: str,
    input_root: str,
    output_root: str,
    items: list[ManifestItem],
) -> dict[str, object]:
    succeeded = sum(1 for item in items if item.status == "succeeded")
    failed = len(items) - succeeded
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "input_root": input_root,
        "output_root": output_root,
        "total": len(items),
        "succeeded": succeeded,
        "failed": failed,
        "items": [
            {
                "input_path": item.input_path,
                "item_slug": item.item_slug,
                "status": item.status,
                "error_code": item.error_code,
                "error_message": item.error_message,
                "document_path": item.document_path,
                "images_count": item.images_count,
                "warnings": item.warnings,
            }
            for item in items
        ],
    }


def write_manifest(manifest_path: Path, manifest: dict[str, object]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
