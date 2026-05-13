from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib

from .domain import ApplyPlan, ApplyResult
from .modes import TargetMode
from .providers import SymbolProviderRegistry
from .utils import is_git_worktree, run_command


@dataclass(frozen=True)
class CertificateCheck:
    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class ApplyCertificate:
    verdict: str
    confidence: str
    trust_level: str
    title: str
    checks: list[CertificateCheck] = field(default_factory=list)
    planned_files: list[str] = field(default_factory=list)
    written_files: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict in {"SAFE", "DRY-RUN SAFE", "APPLY SAFE"}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def short_hash(text: str) -> str:
    return sha256_text(text)[:16]


def snapshot_disk(paths: list[Path] | set[Path]) -> dict[Path, str | None]:
    snapshot: dict[Path, str | None] = {}
    for path in paths:
        snapshot[path] = path.read_text() if path.exists() else None
    return snapshot


def render_plan_preview(plan: ApplyPlan, diff_builder) -> str:
    lines: list[str] = []
    lines.append(f"Operations: {len(plan.operations)}")
    lines.append(f"Changed operations: {len(plan.changed)}")
    lines.append(f"No-op operations: {len(plan.no_op)}")
    lines.append(f"Planned files: {len(plan.planned_files)}")
    for index, op in enumerate(plan.operations, start=1):
        marker = "changed" if op.old_text != op.new_text else "no-op"
        provider = f" via {op.provider_name}" if op.provider_name else ""
        note = f", {op.status_note}" if op.status_note else ""
        lines.append("")
        lines.append(f"=== Operation {index}: {op.rel_name} [{op.mode.value}, {marker}{provider}{note}] ===")
        lines.append(f"Old file sha256: {short_hash(op.old_text)}")
        lines.append(f"New file sha256: {short_hash(op.new_text)}")

        if op.mode == TargetMode.EXACT_REPLACE:
            find = op.operation.block_to_replace or ""
            replace = op.operation.replace_block or ""
            lines.append(f"Target fragment sha256: {short_hash(find)}")
            lines.append(f"Replacement fragment sha256: {short_hash(replace)}")
            lines.append(f"Target fragment occurrences before: {op.old_text.count(find) if find else 0}")
            lines.append(f"Target fragment occurrences after plan: {op.new_text.count(find) if find else 0}")
            lines.append(f"Replacement fragment occurrences after plan: {op.new_text.count(replace) if replace else 0}")
        elif op.mode == TargetMode.METHOD and op.operation.replace_block is not None:
            lines.append(f"Replacement symbol sha256: {short_hash(op.operation.replace_block)}")

        lines.append("")
        diff = diff_builder(op.old_text, op.new_text, op.rel_name)
        lines.append(diff if diff.strip() else "No diff.")
    return "\n".join(lines).rstrip() + "\n"


def render_certificate(certificate: ApplyCertificate) -> str:
    icon = {"SAFE": "✅", "DRY-RUN SAFE": "✅", "APPLY SAFE": "✅", "WARNING": "⚠️", "BLOCKED": "⛔"}.get(certificate.verdict, "•")
    lines = [
        f"{certificate.verdict} {icon}",
        "",
        certificate.title,
        f"Confidence: {certificate.confidence}",
        f"Trust level: {certificate.trust_level}",
        f"Planned files: {len(certificate.planned_files)}",
        f"Written files: {len(certificate.written_files)}",
        "",
        "Checks:",
    ]
    for check in certificate.checks:
        check_icon = {"pass": "✅", "warn": "⚠️", "fail": "⛔", "info": "•"}.get(check.status, "•")
        suffix = f" — {check.detail}" if check.detail else ""
        lines.append(f"{check_icon} {check.name}{suffix}")
    if certificate.planned_files:
        lines.append("")
        lines.append("Planned:")
        lines.extend(f"- {item}" for item in certificate.planned_files)
    if certificate.written_files:
        lines.append("")
        lines.append("Written:")
        lines.extend(f"- {item}" for item in certificate.written_files)
    return "\n".join(lines).rstrip() + "\n"


def build_preview_certificate(repo_root: Path, plan: ApplyPlan) -> ApplyCertificate:
    checks: list[CertificateCheck] = []
    checks.append(CertificateCheck("plan built", "pass", f"{len(plan.operations)} operations"))
    checks.append(CertificateCheck("batch validated before write", "pass"))
    checks.append(CertificateCheck("path guard passed", "pass", f"{len(plan.touched_files)} touched files"))
    if plan.changed:
        checks.append(CertificateCheck("planned changes exist", "pass", f"{len(plan.changed)} changed operations"))
    else:
        checks.append(CertificateCheck("planned changes exist", "info", "all operations are no-op / already applied"))

    for op in plan.operations:
        if op.status_note and op.status_note.startswith("already_applied"):
            checks.append(CertificateCheck("already-applied no-op detected", "info", f"{op.rel_name}: {op.status_note}"))

        if op.mode == TargetMode.EXACT_REPLACE:
            find = op.operation.block_to_replace or ""
            replace = op.operation.replace_block or ""
            checks.append(CertificateCheck("exact replace resolved", "pass", op.rel_name))
            checks.append(CertificateCheck("target fragment hash captured", "pass" if find else "warn", f"{op.rel_name}: {short_hash(find) if find else 'empty target fragment'}"))
            checks.append(CertificateCheck("replacement fragment hash captured", "pass" if replace else "warn", f"{op.rel_name}: {short_hash(replace) if replace else 'empty replacement fragment'}"))
            if find:
                checks.append(CertificateCheck("target fragment occurrence plan", "pass", f"{op.rel_name}: before={op.old_text.count(find)} after={op.new_text.count(find)}"))
            if replace:
                checks.append(CertificateCheck("replacement fragment occurrence plan", "pass", f"{op.rel_name}: after={op.new_text.count(replace)}"))
        elif op.mode == TargetMode.METHOD:
            provider = op.provider_name or "unknown provider"
            checks.append(CertificateCheck("symbol resolved uniquely", "pass", f"{op.rel_name} via {provider}"))
            if op.operation.replace_block is not None:
                checks.append(CertificateCheck("replacement symbol hash captured", "pass", f"{op.rel_name}: {short_hash(op.operation.replace_block)}"))
        elif op.mode == TargetMode.NEW_FILE:
            checks.append(CertificateCheck("new file planned", "pass", op.rel_name))
        elif op.mode == TargetMode.FULL_FILE:
            checks.append(CertificateCheck("full file replacement planned", "pass", op.rel_name))

    trust = _trust_from_checks(checks, base="HIGH")
    verdict = "WARNING" if trust == "MEDIUM" else "SAFE"
    return ApplyCertificate(
        verdict=verdict,
        confidence=trust,
        trust_level=trust,
        title="Preview certificate: plan is resolved; no files were written.",
        checks=checks,
        planned_files=sorted(plan.planned_rel_names),
        written_files=[],
    )


def build_apply_certificate(
    *,
    repo_root: Path,
    plan: ApplyPlan,
    result: ApplyResult,
    before_disk: dict[Path, str | None],
    before_git_status: set[str] | None,
    symbol_providers: SymbolProviderRegistry,
) -> ApplyCertificate:
    repo_root = repo_root.resolve()
    checks: list[CertificateCheck] = []
    final_by_path = {op.target_path: op.new_text for op in plan.changed}
    planned_rel = {op.rel_name for op in plan.changed}

    checks.append(CertificateCheck("plan built", "pass", f"{len(plan.operations)} operations"))
    checks.append(CertificateCheck("batch validated before write", "pass"))

    for op in plan.no_op:
        if op.status_note and op.status_note.startswith("already_applied"):
            checks.append(CertificateCheck("already-applied no-op detected", "info", f"{op.rel_name}: {op.status_note}"))

    if before_git_status:
        pre_existing = sorted(plan.touched_rel_names & before_git_status)
        if pre_existing:
            checks.append(CertificateCheck("pre-existing target modifications", "warn", ", ".join(pre_existing)))

    if result.dry_run:
        after_disk = snapshot_disk(set(before_disk))
        changed = [str(path.relative_to(repo_root)) for path, before_text in before_disk.items() if after_disk.get(path) != before_text]
        if changed:
            checks.append(CertificateCheck("dry-run disk guard", "fail", f"changed unexpectedly: {changed}"))
        else:
            checks.append(CertificateCheck("dry-run disk guard", "pass", "disk content unchanged"))
        checks.append(CertificateCheck("write skipped", "pass", "dry_run=True"))
        checks.append(
            CertificateCheck(
                "written files intentionally zero",
                "info",
                "Dry run validates the plan but must not write files. Turn off Dry run for real apply.",
            )
        )
    else:
        written_rel = {str(path.resolve().relative_to(repo_root)) for path in result.written_files}
        if plan.changed and not written_rel:
            checks.append(
                CertificateCheck(
                    "real apply wrote files",
                    "fail",
                    f"planned_changes={len(plan.changed)} but written_files=0",
                )
            )
        elif plan.changed:
            checks.append(
                CertificateCheck(
                    "real apply wrote files",
                    "pass",
                    f"written_files={len(written_rel)} planned_files={len(planned_rel)}",
                )
            )
        else:
            checks.append(
                CertificateCheck(
                    "real apply had nothing to write",
                    "info",
                    "all operations were no-op / already applied",
                )
            )

        if written_rel == planned_rel:
            checks.append(CertificateCheck("written files match planned files", "pass", ", ".join(sorted(written_rel)) or "none"))
            for op in plan.changed:
                if op.mode == TargetMode.NEW_FILE:
                    checks.append(CertificateCheck("new file written", "pass", op.rel_name))
        else:
            checks.append(CertificateCheck("written files match planned files", "fail", f"planned={sorted(planned_rel)} written={sorted(written_rel)}"))

        for path, planned_text in final_by_path.items():
            rel = str(path.relative_to(repo_root))
            actual = path.read_text() if path.exists() else None
            if actual == planned_text:
                checks.append(CertificateCheck("post-write disk content verified", "pass", rel))
                checks.append(CertificateCheck("post-write full file hash verified", "pass", f"{rel}: {short_hash(planned_text)}"))
            else:
                checks.append(CertificateCheck("post-write disk content verified", "fail", rel))
                checks.append(CertificateCheck("post-write full file hash verified", "fail", rel))

        for op in plan.changed:
            if op.mode == TargetMode.EXACT_REPLACE:
                _append_exact_replace_fragment_checks(checks, repo_root, op)
            if op.mode == TargetMode.METHOD:
                _append_method_symbol_checks(checks, repo_root, op, symbol_providers)

        if result.backups:
            checks.append(CertificateCheck("backups created", "pass", f"{len(result.backups)} backups"))
        else:
            checks.append(CertificateCheck("backups created", "info", "no existing files required backup or backup disabled"))

    if is_git_worktree(repo_root):
        after_git_status = git_changed_files(repo_root)
        if before_git_status is None:
            before_git_status = set()
        allowed_prefixes = (".smart-paster-backups/", ".smart-paster-dumps/", ".smart-paster-history/")
        unexpected = sorted(item for item in (after_git_status - before_git_status - planned_rel) if not item.startswith(allowed_prefixes))
        if unexpected:
            checks.append(CertificateCheck("git unexpected changes guard", "fail", ", ".join(unexpected)))
        else:
            checks.append(CertificateCheck("git unexpected changes guard", "pass"))
    else:
        checks.append(CertificateCheck("git worktree", "warn", "not available; disk verification used instead"))

    trust = _trust_from_checks(checks, base="HIGH")
    if any(check.status == "fail" for check in checks):
        verdict = "BLOCKED"
    elif trust == "MEDIUM":
        verdict = "WARNING"
    elif result.dry_run:
        verdict = "DRY-RUN SAFE"
    else:
        verdict = "APPLY SAFE"

    return ApplyCertificate(
        verdict=verdict,
        confidence=trust,
        trust_level=trust,
        title="Apply certificate: write result was checked against the resolved plan.",
        checks=checks,
        planned_files=sorted(planned_rel),
        written_files=sorted(str(path.resolve().relative_to(repo_root)) for path in result.written_files),
    )


def _trust_from_checks(checks: list[CertificateCheck], *, base: str) -> str:
    if any(check.status == "fail" for check in checks):
        return "LOW"
    if any(check.status == "warn" for check in checks):
        return "MEDIUM"
    return base


def _append_exact_replace_fragment_checks(checks: list[CertificateCheck], repo_root: Path, op) -> None:
    find = op.operation.block_to_replace or ""
    replace = op.operation.replace_block or ""
    actual_text = op.target_path.read_text() if op.target_path.exists() else ""
    rel = str(op.target_path.relative_to(repo_root))

    if find:
        actual_old_count = actual_text.count(find)
        planned_old_count = op.new_text.count(find)
        status = "pass" if actual_old_count == planned_old_count else "fail"
        checks.append(CertificateCheck("post-apply target fragment hash verified", status, f"{rel}: sha256={short_hash(find)} planned_old_count={planned_old_count} actual_old_count={actual_old_count}"))
    else:
        checks.append(CertificateCheck("post-apply target fragment hash verified", "warn", f"{rel}: empty target fragment"))

    if replace:
        actual_replace_count = actual_text.count(replace)
        planned_replace_count = op.new_text.count(replace)
        status = "pass" if actual_replace_count == planned_replace_count else "fail"
        checks.append(CertificateCheck("post-apply replacement fragment hash verified", status, f"{rel}: sha256={short_hash(replace)} planned_count={planned_replace_count} actual_count={actual_replace_count}"))
    else:
        checks.append(CertificateCheck("post-apply replacement fragment hash verified", "warn", f"{rel}: empty replacement fragment"))


def _append_method_symbol_checks(checks: list[CertificateCheck], repo_root: Path, op, symbol_providers: SymbolProviderRegistry) -> None:
    if op.operation.replace_block is None or not op.operation.symbol:
        return
    try:
        actual_text = op.target_path.read_text()
        span = symbol_providers.find_span(
            path=op.target_path,
            old_text=actual_text,
            symbol=op.operation.symbol,
            symbol_kind=op.operation.symbol_kind,
            container_name=op.operation.container_name,
            occurrence=op.operation.occurrence,
            repo_root=repo_root,
        )
        expected = op.operation.replace_block.strip()
        actual = span.selected_text.strip()
        if actual == expected:
            checks.append(CertificateCheck("post-apply symbol verified", "pass", op.rel_name))
            checks.append(CertificateCheck("post-apply symbol hash verified", "pass", f"{op.rel_name}: {short_hash(op.operation.replace_block)}"))
        else:
            checks.append(CertificateCheck("post-apply symbol verified", "fail", f"{op.rel_name}: symbol text differs"))
            checks.append(CertificateCheck("post-apply symbol hash verified", "fail", op.rel_name))
    except Exception as exc:
        checks.append(CertificateCheck("post-apply symbol verified", "fail", f"{op.rel_name}: {exc}"))
        checks.append(CertificateCheck("post-apply symbol hash verified", "fail", op.rel_name))


def git_changed_files(repo_root: Path) -> set[str]:
    code, out, _err = run_command(["git", "status", "--short"], cwd=repo_root)
    if code != 0:
        return set()
    result: set[str] = set()
    for line in out.splitlines():
        if not line.strip():
            continue
        raw = line[3:] if len(line) > 3 else line.strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        result.add(raw.strip())
    return result
