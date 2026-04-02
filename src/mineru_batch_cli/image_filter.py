from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path


INLINE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
REFERENCE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\[([^\]]+)\]")
REFERENCE_DEF_RE = re.compile(r"^\[([^\]]+)\]:\s*(\S+)", re.MULTILINE)
HTML_IMAGE_RE = re.compile(r"<img[^>]*src=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)


@dataclass(frozen=True)
class ImageFilterResult:
    kept_images: list[str]
    missing_images: list[str]
    rewritten_markdown: str


def filter_referenced_images(document_path: Path, source_image_root: Path, target_image_dir: Path) -> ImageFilterResult:
    text = document_path.read_text(encoding="utf-8")
    referenced = _extract_image_paths(text)

    target_image_dir.mkdir(parents=True, exist_ok=True)
    kept: list[str] = []
    missing: list[str] = []
    replacements: dict[str, str] = {}
    source_root_resolved = source_image_root.resolve()
    for ref in sorted(referenced):
        normalized = _normalize_ref(ref)
        if normalized is None:
            continue
        source = (source_image_root / normalized).resolve()
        try:
            source.relative_to(source_root_resolved)
        except ValueError:
            missing.append(normalized.as_posix())
            continue
        if not source.exists() or not source.is_file():
            missing.append(normalized.as_posix())
            continue

        target = target_image_dir / normalized.name
        shutil.copy2(source, target)
        kept.append(normalized.as_posix())
        replacements[normalized.as_posix()] = normalized.name

    rewritten = _rewrite_markdown_image_refs(text, replacements)
    document_path.write_text(rewritten, encoding="utf-8")

    return ImageFilterResult(
        kept_images=kept,
        missing_images=missing,
        rewritten_markdown=rewritten,
    )


def _extract_image_paths(text: str) -> set[str]:
    result: set[str] = set(INLINE_IMAGE_RE.findall(text))
    result.update(HTML_IMAGE_RE.findall(text))

    ref_defs = {name: path for name, path in REFERENCE_DEF_RE.findall(text)}
    for ref_name in REFERENCE_IMAGE_RE.findall(text):
        path = ref_defs.get(ref_name)
        if path:
            result.add(path)

    return result


def _normalize_ref(ref: str) -> Path | None:
    cleaned = ref.strip()
    if not cleaned or cleaned.startswith("http://") or cleaned.startswith("https://"):
        return None
    return Path(cleaned)


def _rewrite_markdown_image_refs(text: str, replacements: dict[str, str]) -> str:
    if not replacements:
        return text

    def replace_inline(match: re.Match[str]) -> str:
        raw = match.group(1)
        cleaned = raw.strip()
        rewritten = replacements.get(cleaned)
        if rewritten is None:
            return match.group(0)
        return match.group(0).replace(raw, rewritten)

    def replace_html(match: re.Match[str]) -> str:
        raw = match.group(1)
        cleaned = raw.strip()
        rewritten = replacements.get(cleaned)
        if rewritten is None:
            return match.group(0)
        return match.group(0).replace(raw, rewritten)

    def replace_ref_def(match: re.Match[str]) -> str:
        name = match.group(1)
        path = match.group(2)
        rewritten = replacements.get(path.strip())
        if rewritten is None:
            return match.group(0)
        return f"[{name}]: {rewritten}"

    text = INLINE_IMAGE_RE.sub(replace_inline, text)
    text = HTML_IMAGE_RE.sub(replace_html, text)
    text = REFERENCE_DEF_RE.sub(replace_ref_def, text)
    return text
