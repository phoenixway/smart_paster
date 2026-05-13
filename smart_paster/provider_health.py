from __future__ import annotations

from pathlib import Path
from typing import Any

from .providers import SymbolProviderRegistry


SAMPLE_SUFFIXES = [".py", ".kt", ".java", ".go"]


def build_provider_health_report(registry: SymbolProviderRegistry, repo_root: Path) -> str:
    lines: list[str] = []
    lines.append("Provider health")
    lines.append("===============")
    lines.append("")
    lines.append(f"Repo root: {repo_root}")
    lines.append("")

    for provider in registry.providers:
        lines.append(f"## {provider.name}")
        lines.append("")
        supported = [suffix for suffix in SAMPLE_SUFFIXES if provider.supports(Path(f"sample{suffix}"))]
        lines.append(f"Supports: {', '.join(supported) if supported else 'none detected'}")

        checks = _provider_specific_checks(provider, repo_root)
        if checks:
            lines.extend(checks)
        else:
            lines.append("Status: passive provider / no load check available")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _provider_specific_checks(provider: Any, repo_root: Path) -> list[str]:
    lines: list[str] = []

    if hasattr(provider, "_get_language"):
        try:
            provider._get_language(repo_root=repo_root)
            lines.append("✅ language load check passed")
        except Exception as exc:
            lines.append(f"⚠️ language load check failed: {type(exc).__name__}: {exc}")

    if hasattr(provider, "_get_extractor"):
        try:
            provider._get_extractor(repo_root=repo_root)
            lines.append("✅ extractor load check passed")
        except Exception as exc:
            lines.append(f"⚠️ extractor load check failed: {type(exc).__name__}: {exc}")

    return lines
