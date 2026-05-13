from __future__ import annotations

from pathlib import Path

from .errors import ValidationError


def safe_target_path(repo_root: Path, filename: str) -> Path:
    if not filename or not filename.strip():
        raise ValidationError("Target file path is empty.")

    raw = filename.strip()
    path = Path(raw)

    if path.is_absolute():
        raise ValidationError(f"Absolute paths are refused: {raw}")
    if ".." in path.parts:
        raise ValidationError(f"Path escaping via '..' is refused: {raw}")

    root = repo_root.resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"Path escapes repo root: {raw}") from exc
    return resolved
