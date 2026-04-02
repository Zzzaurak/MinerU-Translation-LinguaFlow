from __future__ import annotations

from pathlib import Path

from mineru_batch_cli.image_filter import filter_referenced_images


def test_mixed_reference_styles(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "inline.png").write_bytes(b"1")
    (source_root / "ref.png").write_bytes(b"2")
    (source_root / "html.png").write_bytes(b"3")

    doc = tmp_path / "document.md"
    doc.write_text(
        "\n".join(
            [
                "![inline](inline.png)",
                "![ref-image][r1]",
                "[r1]: ref.png",
                '<img src="html.png" />',
            ]
        ),
        encoding="utf-8",
    )

    target_dir = tmp_path / "images"
    result = filter_referenced_images(doc, source_root, target_dir)

    assert sorted(result.kept_images) == ["html.png", "inline.png", "ref.png"]
    assert result.missing_images == []
    assert (target_dir / "inline.png").exists()
    assert (target_dir / "ref.png").exists()
    assert (target_dir / "html.png").exists()


def test_missing_referenced_image_flagged(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "exists.png").write_bytes(b"1")

    doc = tmp_path / "document.md"
    doc.write_text("![a](exists.png)\n![b](missing.png)", encoding="utf-8")

    target_dir = tmp_path / "images"
    result = filter_referenced_images(doc, source_root, target_dir)

    assert result.kept_images == ["exists.png"]
    assert result.missing_images == ["missing.png"]
    assert "exists.png" in result.rewritten_markdown
    assert (target_dir / "exists.png").exists()
    assert not (target_dir / "missing.png").exists()


def test_rewrites_nested_image_reference_to_flat_target(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    nested = source_root / "assets" / "img"
    nested.mkdir(parents=True)
    (nested / "n.png").write_bytes(b"n")

    doc = tmp_path / "document.md"
    doc.write_text("![n](assets/img/n.png)", encoding="utf-8")

    target_dir = tmp_path / "images"
    result = filter_referenced_images(doc, source_root, target_dir)

    assert result.kept_images == ["assets/img/n.png"]
    assert "![n](n.png)" in result.rewritten_markdown
    assert (target_dir / "n.png").exists()


def test_blocks_parent_traversal_reference(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()

    outside_file = tmp_path / "outside.png"
    outside_file.write_bytes(b"x")

    doc = tmp_path / "document.md"
    doc.write_text("![x](../outside.png)", encoding="utf-8")

    target_dir = tmp_path / "images"
    result = filter_referenced_images(doc, source_root, target_dir)

    assert result.kept_images == []
    assert result.missing_images == ["../outside.png"]
