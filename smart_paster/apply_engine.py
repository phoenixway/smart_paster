from __future__ import annotations

import shutil
import time
from collections import defaultdict
from pathlib import Path

from .domain import ApplyPlan, ApplyResult, BackupRecord, PatchBatch, PatchOperation, ResolvedOperation, SymbolSpan
from .errors import ApplyError, ValidationError
from .modes import TargetMode
from .path_guard import safe_target_path
from .providers import SymbolProviderRegistry


class ApplyEngine:
    """Pure-ish application core.

    GUI/CLI should call plan() first. plan() validates all operations before any
    write happens. apply_plan() writes only already-resolved operations.
    """

    def __init__(self, symbol_providers: SymbolProviderRegistry | None = None) -> None:
        self.symbol_providers = symbol_providers or SymbolProviderRegistry()

    def plan(
        self,
        *,
        repo_root: Path,
        batch: PatchBatch,
        default_mode: TargetMode = TargetMode.EXACT_REPLACE,
        ui_target_override: str | None = None,
        ui_symbol_override: str | None = None,
    ) -> ApplyPlan:
        repo_root = repo_root.resolve()
        if not repo_root.exists() or not repo_root.is_dir():
            raise ValidationError(f"Repo root does not exist or is not a directory: {repo_root}")

        # Sequential per file: each operation sees prior in-memory changes for the same file.
        current_text_by_path: dict[Path, str] = {}
        original_text_by_path: dict[Path, str] = {}
        resolved: list[ResolvedOperation] = []

        for index, operation in enumerate(batch.operations):
            allow_override = len(batch.operations) == 1
            op = self._with_ui_overrides(operation, allow_override, ui_target_override, ui_symbol_override)
            target_path = safe_target_path(repo_root, op.filename)
            rel_name = str(target_path.relative_to(repo_root))
            mode = op.mode or default_mode

            if target_path in current_text_by_path:
                old_text = current_text_by_path[target_path]
            else:
                old_text = target_path.read_text() if target_path.exists() else ""
                original_text_by_path[target_path] = old_text

            new_text, provider_name = self._resolve_new_text(
                repo_root=repo_root,
                target_path=target_path,
                rel_name=rel_name,
                old_text=old_text,
                operation=op,
                mode=mode,
            )
            current_text_by_path[target_path] = new_text
            resolved.append(
                ResolvedOperation(
                    operation=op,
                    target_path=target_path,
                    rel_name=rel_name,
                    old_text=old_text,
                    new_text=new_text,
                    provider_name=provider_name,
                )
            )

        return ApplyPlan(resolved)

    def apply_plan(self, *, repo_root: Path, plan: ApplyPlan, dry_run: bool = True, backup: bool = True) -> ApplyResult:
        repo_root = repo_root.resolve()
        changed = plan.changed
        if dry_run:
            return ApplyResult(written_files=[], backups=[], dry_run=True)

        backups: list[BackupRecord] = []
        final_by_path: dict[Path, str] = {}
        for op in changed:
            final_by_path[op.target_path] = op.new_text

        # Backup before writing anything. If backup fails, nothing has been written yet.
        if backup:
            for path in final_by_path:
                if path.exists():
                    backups.append(BackupRecord(original_path=path, backup_path=make_backup(path, repo_root)))

        written: list[Path] = []
        for path, new_text in final_by_path.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_text)
            written.append(path)

        return ApplyResult(written_files=written, backups=backups, dry_run=False)

    def _with_ui_overrides(
        self,
        operation: PatchOperation,
        allow_override: bool,
        ui_target_override: str | None,
        ui_symbol_override: str | None,
    ) -> PatchOperation:
        if not allow_override:
            return operation
        filename = ui_target_override.strip() if ui_target_override and ui_target_override.strip() else operation.filename
        symbol = ui_symbol_override.strip() if ui_symbol_override and ui_symbol_override.strip() else operation.symbol
        return PatchOperation(
            filename=filename,
            mode=operation.mode,
            replace_block=operation.replace_block,
            block_to_replace=operation.block_to_replace,
            symbol=symbol,
            symbol_kind=operation.symbol_kind,
            container_name=operation.container_name,
            occurrence=operation.occurrence,
            allow_overwrite=operation.allow_overwrite,
            source_kind=operation.source_kind,
        )

    def _resolve_new_text(
        self,
        *,
        repo_root: Path,
        target_path: Path,
        rel_name: str,
        old_text: str,
        operation: PatchOperation,
        mode: TargetMode,
    ) -> tuple[str, str | None]:
        if operation.replace_block is None:
            raise ValidationError(f"Operation for {rel_name} requires replace_block.")

        if mode == TargetMode.NEW_FILE:
            if target_path.exists() and not operation.allow_overwrite:
                raise ValidationError(f"New file target already exists: {rel_name}. Set allow_overwrite=true or use full_file.")
            return operation.replace_block, None

        if not target_path.exists():
            raise ValidationError(f"Target file does not exist: {rel_name}")

        if mode == TargetMode.FULL_FILE:
            return operation.replace_block, None

        if mode == TargetMode.EXACT_REPLACE:
            if operation.block_to_replace is None:
                raise ValidationError(f"Exact replace for {rel_name} requires block_to_replace/find/old.")
            return exact_replace(old_text, operation.block_to_replace, operation.replace_block), None

        if mode == TargetMode.METHOD:
            symbol = operation.symbol
            if not symbol:
                raise ValidationError(f"Method replace for {rel_name} requires symbol/method/function.")
            span = self.symbol_providers.find_span(
                path=target_path,
                old_text=old_text,
                symbol=symbol,
                symbol_kind=operation.symbol_kind,
                container_name=operation.container_name,
                occurrence=operation.occurrence,
                repo_root=repo_root,
            )
            return replace_line_span(old_text, span, operation.replace_block), span.provider

        raise ValidationError(f"Unsupported mode: {mode}")


def exact_replace(old_text: str, find: str, replace: str) -> str:
    count = old_text.count(find)
    if count == 0:
        raise ApplyError("Exact block was not found in target file.")
    if count > 1:
        raise ApplyError(f"Exact block occurs {count} times. Refusing ambiguous replace.")
    return old_text.replace(find, replace, 1)


def replace_line_span(old_text: str, span: SymbolSpan, replacement: str) -> str:
    lines = old_text.splitlines(keepends=True)
    start, end = span.line_slice()
    if start >= len(lines) or end > len(lines) or start >= end:
        raise ApplyError(f"Invalid symbol line range from {span.provider}: {span.start_line}-{span.end_line}")
    replacement = replacement.rstrip() + "\n"
    return "".join(lines[:start]) + replacement + "".join(lines[end:])


def make_backup(path: Path, repo_root: Path) -> Path:
    backup_root = repo_root / ".smart-paster-backups"
    backup_root.mkdir(exist_ok=True)
    rel = path.relative_to(repo_root)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = backup_root / f"{str(rel).replace('/', '__')}.{stamp}.bak"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path
