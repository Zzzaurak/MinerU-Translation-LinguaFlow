from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


ALLOWED_INPUT_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".html",
)


class DiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class DiscoveredInput:
    path: Path
    relative_path: str
    input_id: str


def discover_inputs(input_dir: Path) -> list[DiscoveredInput]:
    root = input_dir.resolve()
    if not root.exists() or not root.is_dir():
        raise DiscoveryError(f"Input directory does not exist: {input_dir}")

    collected: list[DiscoveredInput] = []
    for candidate in root.rglob("*"):
        if candidate.is_dir() or candidate.is_symlink():
            continue
        if candidate.suffix.lower() not in ALLOWED_INPUT_EXTENSIONS:
            continue

        relative = candidate.relative_to(root).as_posix()
        stats = candidate.stat()
        material = f"{relative}|{stats.st_size}|{stats.st_mtime_ns}"
        input_id = sha256(material.encode("utf-8")).hexdigest()[:16]
        collected.append(
            DiscoveredInput(path=candidate, relative_path=relative, input_id=input_id)
        )

    return sorted(
        collected,
        key=lambda item: (item.relative_path.casefold(), item.relative_path),
    )
