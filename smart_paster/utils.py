from __future__ import annotations

import subprocess
from pathlib import Path


def run_command(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def discover_git_root(start: Path) -> Path | None:
    code, out, _err = run_command(["git", "rev-parse", "--show-toplevel"], cwd=start)
    if code == 0 and out.strip():
        return Path(out.strip()).resolve()
    return None


def is_git_worktree(path: Path) -> bool:
    code, out, _err = run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
    return code == 0 and out.strip() == "true"


def git_root_for(path: Path) -> Path | None:
    return discover_git_root(path)


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def detect_language(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".kt", ".kts"}:
        return "kotlin"
    if suffix == ".java":
        return "java"
    if suffix == ".go":
        return "go"
    return "unknown"


def line_col_from_offset(text: str, offset: int) -> tuple[int, int]:
    offset = max(0, min(offset, len(text)))
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    col = offset + 1 if last_newline < 0 else offset - last_newline
    return line, col


def line_from_end_offset(text: str, offset: int) -> int:
    """Return an inclusive 1-based line number for an exclusive end offset.

    If the end offset sits just after a trailing newline, the symbol still ends
    on the previous content line. This avoids spans like 1-4 for a 3-line file.
    """
    offset = max(0, min(offset, len(text)))
    if offset > 0 and text[offset - 1] == "\n":
        return max(1, text.count("\n", 0, offset))
    return text.count("\n", 0, offset) + 1
