from __future__ import annotations

from pathlib import Path

from mineru_batch_cli.normalize_markdown import normalize_primary_markdown
from mineru_batch_cli.output_writer import (
    build_primary_markdown_name,
    build_translated_markdown_name,
)


def test_prefer_full_md(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    output = tmp_path / "output"
    extracted.mkdir()
    (extracted / "full.md").write_text("full")
    (extracted / "document.md").write_text("doc")

    result = normalize_primary_markdown(extracted, output)

    assert result.status == "markdown_ready"
    assert result.source_path == extracted / "full.md"
    assert (output / "document.md").read_text() == "full"


def test_missing_markdown_marks_failed(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    output = tmp_path / "output"
    extracted.mkdir()
    (extracted / "model.json").write_text("{}")

    result = normalize_primary_markdown(extracted, output)

    assert result.status == "markdown_missing"
    assert result.document_path is None
    assert not output.exists()


def test_build_primary_markdown_name_uses_source_stem() -> None:
    assert build_primary_markdown_name("doc-a.pdf") == "doc-a.md"
    assert build_primary_markdown_name("report.v1.pdf") == "report.v1.md"
    assert build_primary_markdown_name("doc-a.md") == "doc-a.md"


def test_build_translated_markdown_name_uses_source_stem_and_language_suffix() -> None:
    assert build_translated_markdown_name("doc-a.pdf", "zh-CN") == "doc-a_zh.md"
    assert build_translated_markdown_name("report.v1.pdf", "zh-CN") == "report.v1_zh.md"
    assert build_translated_markdown_name("doc-a.md", "zh-CN") == "doc-a_zh.md"
