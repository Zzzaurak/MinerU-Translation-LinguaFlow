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
        images_source_dir=images_source,
        item_metadata_json='{"status":"ok"}',
    )

    assert output.item_dir == tmp_path / "out" / "items" / "doc-1"
    assert output.document_path.exists()
    assert output.item_json_path.exists()
    assert (output.images_dir / "a.png").exists()
    names = sorted(path.name for path in output.item_dir.iterdir())
    assert names == ["document.md", "images", "item.json"]


def test_slug_collision_resolved() -> None:
    existing = {"docs-file.pdf"}
    slug = build_item_slug("docs/file.pdf", existing=existing)

    assert slug.startswith("docs-file.pdf-")
    assert len(slug.split("-")[-1]) == 8
