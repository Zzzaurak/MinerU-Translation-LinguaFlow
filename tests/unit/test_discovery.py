from __future__ import annotations

from pathlib import Path

import pytest

from mineru_batch_cli.discovery import DiscoveryError, discover_inputs


def test_discover_inputs_returns_stable_sorted_results(tmp_path: Path) -> None:
    nested = tmp_path / "z" / "x"
    nested.mkdir(parents=True)
    (tmp_path / "b.PDF").write_bytes(b"b")
    (tmp_path / "a.docx").write_bytes(b"a")
    (nested / "c.jpg").write_bytes(b"c")
    (tmp_path / "ignore.txt").write_text("no")

    first = discover_inputs(tmp_path)
    second = discover_inputs(tmp_path)

    first_rel = [item.relative_path for item in first]
    second_rel = [item.relative_path for item in second]
    assert first_rel == ["a.docx", "b.PDF", "z/x/c.jpg"]
    assert second_rel == first_rel
    assert [item.input_id for item in first] == [item.input_id for item in second]


def test_discover_inputs_raises_for_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(DiscoveryError, match="Input directory does not exist"):
        discover_inputs(missing)
