from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .modes import TargetMode


@dataclass(frozen=True)
class PatchOperation:
    filename: str
    mode: TargetMode | None = None
    replace_block: str | None = None
    block_to_replace: str | None = None
    symbol: str | None = None
    symbol_kind: str | None = None
    container_name: str | None = None
    occurrence: int = 1
    allow_overwrite: bool = False
    source_kind: str = "unknown"


@dataclass(frozen=True)
class PatchBatch:
    operations: list[PatchOperation]
    smart_paster_version: int = 1
    atomic: bool = True
    sequential_per_file: bool = True
    source_kind: str = "batch"


@dataclass(frozen=True)
class ResolvedOperation:
    operation: PatchOperation
    target_path: Path
    rel_name: str
    old_text: str
    new_text: str
    mode: TargetMode
    provider_name: str | None = None


@dataclass(frozen=True)
class ApplyPlan:
    operations: list[ResolvedOperation]

    @property
    def changed(self) -> list[ResolvedOperation]:
        return [op for op in self.operations if op.old_text != op.new_text]

    @property
    def planned_files(self) -> set[Path]:
        return {op.target_path for op in self.changed}

    @property
    def planned_rel_names(self) -> set[str]:
        return {op.rel_name for op in self.changed}


@dataclass(frozen=True)
class BackupRecord:
    original_path: Path
    backup_path: Path


@dataclass(frozen=True)
class ApplyResult:
    written_files: list[Path] = field(default_factory=list)
    backups: list[BackupRecord] = field(default_factory=list)
    dry_run: bool = True


@dataclass(frozen=True)
class SymbolSpan:
    provider: str
    symbol: str
    symbol_kind: str
    container_name: str | None
    start_line: int
    end_line: int
    start_col: int = 1
    end_col: int = 1
    selected_text: str = ""
    candidates: list[dict[str, object]] = field(default_factory=list)

    def line_slice(self) -> tuple[int, int]:
        return max(0, self.start_line - 1), max(0, self.end_line)
