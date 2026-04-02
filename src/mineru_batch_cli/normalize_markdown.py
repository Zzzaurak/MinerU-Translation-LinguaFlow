from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


class MarkdownSelectionError(ValueError):
    pass


@dataclass(frozen=True)
class MarkdownNormalizationResult:
    status: str
    source_path: Path | None = None
    document_path: Path | None = None


def normalize_primary_markdown(extracted_dir: Path, item_output_dir: Path) -> MarkdownNormalizationResult:
    source = _select_markdown_source(extracted_dir)
    if source is None:
        return MarkdownNormalizationResult(status="markdown_missing")

    item_output_dir.mkdir(parents=True, exist_ok=True)
    target = item_output_dir / "document.md"
    shutil.copy2(source, target)
    return MarkdownNormalizationResult(
        status="markdown_ready",
        source_path=source,
        document_path=target,
    )


def _select_markdown_source(extracted_dir: Path) -> Path | None:
    full_md = extracted_dir / "full.md"
    if full_md.exists() and full_md.is_file():
        return full_md

    document_md = extracted_dir / "document.md"
    if document_md.exists() and document_md.is_file():
        return document_md

    md_files = sorted(path for path in extracted_dir.glob("*.md") if path.is_file())
    if len(md_files) == 1:
        return md_files[0]
    return None
