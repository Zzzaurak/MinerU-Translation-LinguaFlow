from __future__ import annotations

from pathlib import Path

from mineru_batch_cli.normalize_markdown import normalize_primary_markdown


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
