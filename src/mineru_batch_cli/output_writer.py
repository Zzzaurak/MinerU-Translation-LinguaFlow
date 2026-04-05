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
    translated_document_path: Path | None
    source_document_path: Path | None
    source_move_status: str | None
    source_move_error: str | None
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
    translated_document_source: Path | None,
    source_input_file: Path | None,
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

    translated_target: Path | None = None
    if translated_document_source is not None:
        translated_name = translated_document_source.name
        if not translated_name:
            translated_name = "document.zh.md"
        translated_target = item_dir / translated_name
        shutil.copy2(translated_document_source, translated_target)

    images_target = item_dir / "images"
    images_target.mkdir(parents=True, exist_ok=True)
    if images_source_dir.exists() and images_source_dir.is_dir():
        for image in images_source_dir.iterdir():
            if image.is_file():
                shutil.copy2(image, images_target / image.name)

    item_json_path = item_dir / "item.json"
    item_json_path.write_text(item_metadata_json, encoding="utf-8")

    source_target: Path | None = None
    source_move_status: str | None = None
    source_move_error: str | None = None
    if source_input_file is not None:
        source_dir = item_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_target = source_dir / source_input_file.name
        try:
            shutil.move(str(source_input_file), str(source_target))
            source_move_status = "moved"
        except OSError as move_exc:
            try:
                shutil.copy2(source_input_file, source_target)
            except OSError as copy_exc:
                source_target = None
                source_move_status = "failed"
                source_move_error = f"move failed: {move_exc}; fallback copy failed: {copy_exc}"
            else:
                try:
                    source_input_file.unlink()
                except OSError as unlink_exc:
                    source_move_status = "failed"
                    source_move_error = (
                        f"move failed: {move_exc}; fallback copied but delete failed: {unlink_exc}"
                    )
                else:
                    source_move_status = "copied_then_deleted"

    return ItemOutput(
        item_slug=item_slug,
        item_dir=item_dir,
        document_path=document_target,
        translated_document_path=translated_target,
        source_document_path=source_target,
        source_move_status=source_move_status,
        source_move_error=source_move_error,
        images_dir=images_target,
        item_json_path=item_json_path,
    )
