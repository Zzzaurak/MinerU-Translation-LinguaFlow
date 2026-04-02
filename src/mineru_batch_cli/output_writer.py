from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ItemOutput:
    item_slug: str
    item_dir: Path
    document_path: Path
    images_dir: Path
    item_json_path: Path


def build_item_slug(relative_path: str, *, existing: set[str] | None = None) -> str:
    normalized = relative_path.replace("\\", "/").strip("/")
    base = normalized.replace("/", "-").replace(" ", "-").lower()
    base = "".join(ch if ch.isalnum() or ch in {"-", ".", "_"} else "-" for ch in base)
    base = "-".join(part for part in base.split("-") if part)
    if not base:
        base = "item"

    if existing is None or base not in existing:
        return base

    suffix = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{suffix}"


def write_item_output(
    *,
    output_root: Path,
    item_slug: str,
    document_source: Path,
    images_source_dir: Path,
    item_metadata_json: str,
) -> ItemOutput:
    items_root = output_root / "items"
    item_dir = items_root / item_slug
    if item_dir.exists():
        shutil.rmtree(item_dir)
    item_dir.mkdir(parents=True, exist_ok=True)

    document_target = item_dir / "document.md"
    shutil.copy2(document_source, document_target)

    images_target = item_dir / "images"
    images_target.mkdir(parents=True, exist_ok=True)
    if images_source_dir.exists() and images_source_dir.is_dir():
        for image in images_source_dir.iterdir():
            if image.is_file():
                shutil.copy2(image, images_target / image.name)

    item_json_path = item_dir / "item.json"
    item_json_path.write_text(item_metadata_json, encoding="utf-8")

    return ItemOutput(
        item_slug=item_slug,
        item_dir=item_dir,
        document_path=document_target,
        images_dir=images_target,
        item_json_path=item_json_path,
    )
