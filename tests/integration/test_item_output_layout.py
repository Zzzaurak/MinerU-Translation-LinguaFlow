from __future__ import annotations

from pathlib import Path

from mineru_batch_cli.output_writer import build_item_slug, write_item_output


def test_item_layout_contract(tmp_path: Path) -> None:
    document_source = tmp_path / "source.md"
    document_source.write_text("# doc", encoding="utf-8")

    images_source = tmp_path / "images-src"
    images_source.mkdir()
    (images_source / "a.png").write_bytes(b"a")

    output = write_item_output(
        output_root=tmp_path / "out",
        item_slug="doc-1",
        document_source=document_source,
        translated_document_source=None,
        source_input_file=None,
        images_source_dir=images_source,
        item_metadata_json='{"status":"ok"}',
    )

    assert output.item_dir == tmp_path / "out" / "items" / "doc-1"
    assert output.document_path.exists()
    assert output.item_json_path.exists()
    assert (output.images_dir / "a.png").exists()
    names = sorted(path.name for path in output.item_dir.iterdir())
    assert names == ["document.md", "images", "item.json"]
    assert output.translated_document_path is None
    assert output.source_document_path is None
    assert output.source_move_status is None
    assert output.source_move_error is None


def test_item_layout_contract_writes_translated_markdown_when_provided(tmp_path: Path) -> None:
    document_source = tmp_path / "source.md"
    translated_source = tmp_path / "source.zh.md"
    document_source.write_text("# hello", encoding="utf-8")
    translated_source.write_text("# 你好", encoding="utf-8")

    output = write_item_output(
        output_root=tmp_path / "out",
        item_slug="doc-zh",
        document_source=document_source,
        translated_document_source=translated_source,
        source_input_file=None,
        images_source_dir=tmp_path / "missing-images",
        item_metadata_json='{"status":"ok"}',
    )

    assert output.translated_document_path == output.item_dir / "source.zh.md"
    translated = output.translated_document_path
    assert translated is not None
    assert translated.exists()
    assert translated.read_text(encoding="utf-8") == "# 你好"
    names = sorted(path.name for path in output.item_dir.iterdir())
    assert names == ["document.md", "images", "item.json", "source.zh.md"]


def test_item_layout_contract_moves_source_file_when_provided(tmp_path: Path) -> None:
    document_source = tmp_path / "source.md"
    input_file = tmp_path / "doc-a.pdf"
    document_source.write_text("# hello", encoding="utf-8")
    input_file.write_bytes(b"pdf")

    output = write_item_output(
        output_root=tmp_path / "out",
        item_slug="doc-source",
        document_source=document_source,
        translated_document_source=None,
        source_input_file=input_file,
        images_source_dir=tmp_path / "missing-images",
        item_metadata_json='{"status":"ok"}',
    )

    source_path = output.source_document_path
    assert source_path is not None
    assert source_path.exists()
    assert source_path.name == "doc-a.pdf"
    assert output.source_move_status in {"moved", "copied_then_deleted"}
    assert output.source_move_error is None
    assert not input_file.exists()
    names = sorted(path.name for path in output.item_dir.iterdir())
    assert names == ["document.md", "images", "item.json", "source"]


def test_slug_collision_resolved() -> None:
    existing = {"docs-file.pdf"}
    slug = build_item_slug("docs/file.pdf", existing=existing)

    assert slug.startswith("docs-file.pdf-")
    assert len(slug.split("-")[-1]) == 8
