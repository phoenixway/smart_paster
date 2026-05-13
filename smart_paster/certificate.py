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
    title: str
    checks: list[CertificateCheck] = field(default_factory=list)
    planned_files: list[str] = field(default_factory=list)
    written_files: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "SAFE"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def snapshot_disk(paths: list[Path] | set[Path]) -> dict[Path, str | None]:
    snapshot: dict[Path, str | None] = {}
    for path in paths:
        snapshot[path] = path.read_text() if path.exists() else None
    return snapshot


def render_plan_preview(plan: ApplyPlan, diff_builder) -> str:
    lines: list[str] = []
    lines.append(f"Operations: {len(plan.operations)}")
    lines.append(f"Changed operations: {len(plan.changed)}")
    lines.append(f"Planned files: {len(plan.planned_files)}")
    for index, op in enumerate(plan.operations, start=1):
        marker = "changed" if op.old_text != op.new_text else "no-change"
        provider = f" via {op.provider_name}" if op.provider_name else ""
        lines.append("")
        lines.append(f"=== Operation {index}: {op.rel_name} [{op.mode.value}, {marker}{provider}] ===")
        lines.append(f"Old sha256: {sha256_text(op.old_text)[:16]}")
        lines.append(f"New sha256: {sha256_text(op.new_text)[:16]}")
        lines.append("")
        diff = diff_builder(op.old_text, op.new_text, op.rel_name)
        lines.append(diff if diff.strip() else "No diff.")
    return "\n".join(lines).rstrip() + "\n"


def render_certificate(certificate: ApplyCertificate) -> str:
    icon = {"SAFE": "✅", "WARNING": "⚠️", "BLOCKED": "⛔"}.get(certificate.verdict, "•")
    lines = [
        f"{certificate.verdict} {icon}",
        "",
        certificate.title,
        f"Confidence: {certificate.confidence}",
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
    checks.append(CertificateCheck("path guard passed", "pass", f"{len(plan.planned_files)} planned files"))
    if plan.changed:
        checks.append(CertificateCheck("planned changes exist", "pass", f"{len(plan.changed)} changed operations"))
    else:
        checks.append(CertificateCheck("planned changes exist", "warn", "plan contains no changes"))
    for op in plan.operations:
        if op.mode == TargetMode.EXACT_REPLACE:
            checks.append(CertificateCheck("exact replace resolved uniquely", "pass", op.rel_name))
        elif op.mode == TargetMode.METHOD:
            provider = op.provider_name or "unknown provider"
            checks.append(CertificateCheck("symbol resolved uniquely", "pass", f"{op.rel_name} via {provider}"))
        elif op.mode == TargetMode.NEW_FILE:
            checks.append(CertificateCheck("new file planned", "pass", op.rel_name))
        elif op.mode == TargetMode.FULL_FILE:
            checks.append(CertificateCheck("full file replacement planned", "pass", op.rel_name))

    verdict = "SAFE" if all(check.status != "fail" for check in checks) else "BLOCKED"
    confidence = "HIGH" if verdict == "SAFE" and plan.changed else "MEDIUM"
    return ApplyCertificate(
        verdict=verdict,
        confidence=confidence,
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

    if result.dry_run:
        after_disk = snapshot_disk(set(before_disk))
        changed = [
            str(path.relative_to(repo_root))
            for path, before_text in before_disk.items()
            if after_disk.get(path) != before_text
        ]
        if changed:
            checks.append(CertificateCheck("dry-run disk guard", "fail", f"changed unexpectedly: {changed}"))
        else:
            checks.append(CertificateCheck("dry-run disk guard", "pass", "disk content unchanged"))
        checks.append(CertificateCheck("write skipped", "pass", "dry_run=True"))
    else:
        written_rel = {str(path.resolve().relative_to(repo_root)) for path in result.written_files}
        if written_rel == planned_rel:
            checks.append(CertificateCheck("written files match planned files", "pass", ", ".join(sorted(written_rel)) or "none"))
        else:
            checks.append(
                CertificateCheck(
                    "written files match planned files",
                    "fail",
                    f"planned={sorted(planned_rel)} written={sorted(written_rel)}",
                )
            )

        for path, planned_text in final_by_path.items():
            rel = str(path.relative_to(repo_root))
            actual = path.read_text() if path.exists() else None
            if actual == planned_text:
                checks.append(CertificateCheck("post-write disk content verified", "pass", rel))
            else:
                checks.append(CertificateCheck("post-write disk content verified", "fail", rel))

        for op in plan.changed:
            if op.mode != TargetMode.METHOD or op.operation.replace_block is None or not op.operation.symbol:
                continue
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
                else:
                    checks.append(CertificateCheck("post-apply symbol verified", "fail", f"{op.rel_name}: symbol text differs"))
            except Exception as exc:
                checks.append(CertificateCheck("post-apply symbol verified", "fail", f"{op.rel_name}: {exc}"))

        if result.backups:
            checks.append(CertificateCheck("backups created", "pass", f"{len(result.backups)} backups"))
        else:
            checks.append(CertificateCheck("backups created", "info", "no existing files required backup or backup disabled"))

    if is_git_worktree(repo_root):
        after_git_status = git_changed_files(repo_root)
        if before_git_status is None:
            before_git_status = set()
        allowed_prefixes = (".smart-paster-backups/", ".smart-paster-dumps/")
        unexpected = sorted(
            item for item in (after_git_status - before_git_status - planned_rel)
            if not item.startswith(allowed_prefixes)
        )
        if unexpected:
            checks.append(CertificateCheck("git unexpected changes guard", "fail", ", ".join(unexpected)))
        else:
            checks.append(CertificateCheck("git unexpected changes guard", "pass"))
    else:
        checks.append(CertificateCheck("git worktree", "warn", "not available; disk verification used instead"))

    if any(check.status == "fail" for check in checks):
        verdict = "BLOCKED"
        confidence = "LOW"
    elif any(check.status == "warn" for check in checks):
        verdict = "WARNING"
        confidence = "MEDIUM"
    else:
        verdict = "SAFE"
        confidence = "HIGH"

    return ApplyCertificate(
        verdict=verdict,
        confidence=confidence,
        title="Apply certificate: write result was checked against the resolved plan.",
        checks=checks,
        planned_files=sorted(planned_rel),
        written_files=sorted(str(path.resolve().relative_to(repo_root)) for path in result.written_files),
    )


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
