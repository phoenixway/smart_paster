from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

from smart_paster.domain import SymbolSpan
from smart_paster.errors import SymbolResolutionError
from smart_paster.providers.base import SymbolProvider


class AngelicaKotlinSymbolProvider(SymbolProvider):
    """Optional adapter for Angelica's KotlinSymbolExtractor.

    It is intentionally dynamic. Smart Paster can run outside Angelica and still
    function via RegexFallbackSymbolProvider. If the user runs Smart Paster inside
    the Angelica repo, or sets SMART_PASTER_ANGELICA_ROOT, this provider can use
    the Tree-sitter extractor directly.
    """

    name = "angelica_kotlin_tree_sitter"
    IMPORT_CANDIDATES = (
        "modules.tools._kotlin_symbol_extractor",
        "modules.tools.code._kotlin_symbol_extractor",
        "modules.agent.tools._kotlin_symbol_extractor",
        "modules.agent.tools.code._kotlin_symbol_extractor",
        "modules.agent.tools.files._kotlin_symbol_extractor",
        "_kotlin_symbol_extractor",
    )

    def __init__(self) -> None:
        self._extractor: Any | None = None
        self._load_error: str | None = None

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".kt"

    def find_span(
        self,
        *,
        path: Path,
        old_text: str,
        symbol: str,
        symbol_kind: str | None = None,
        container_name: str | None = None,
        occurrence: int = 1,
        repo_root: Path | None = None,
    ) -> SymbolSpan:
        extractor = self._get_extractor(repo_root=repo_root)
        result = extractor.extract_symbol(
            path=str(path),
            symbol_name=symbol,
            symbol_kind=symbol_kind or "auto",
            container_name=container_name,
            occurrence=occurrence,
            include_body=True,
            include_signature=True,
            include_line_range=True,
        )
        if result.get("status") != "success":
            details = result.get("error_details") or {}
            candidates = details.get("candidates") or result.get("candidates") or []
            raise SymbolResolutionError(
                f"Angelica Kotlin provider failed: {result.get('error_code', 'ERROR')}: "
                f"{result.get('output', '')} Candidates: {candidates}"
            )
        return SymbolSpan(
            provider=self.name,
            symbol=str(result.get("symbol_name") or symbol),
            symbol_kind=str(result.get("symbol_kind") or symbol_kind or "auto"),
            container_name=result.get("container_name") or container_name,
            start_line=int(result.get("start_line") or 1),
            end_line=int(result.get("end_line") or 1),
            start_col=int(result.get("start_col") or 1),
            end_col=int(result.get("end_col") or 1),
            selected_text=str(result.get("file_content") or result.get("output") or ""),
            candidates=list(result.get("candidates") or []),
        )

    def _get_extractor(self, repo_root: Path | None) -> Any:
        if self._extractor is not None:
            return self._extractor

        added_paths: list[str] = []
        for candidate in self._candidate_roots(repo_root):
            value = str(candidate)
            if value not in sys.path:
                sys.path.insert(0, value)
                added_paths.append(value)

        errors: list[str] = []
        for module_name in self.IMPORT_CANDIDATES:
            try:
                module = importlib.import_module(module_name)
                cls = getattr(module, "KotlinSymbolExtractor")
                self._extractor = cls()
                self._load_error = None
                return self._extractor
            except Exception as exc:
                errors.append(f"{module_name}: {exc}")

        self._load_error = "; ".join(errors)
        raise SymbolResolutionError(
            "Angelica KotlinSymbolExtractor is unavailable. "
            f"Import attempts: {self._load_error}"
        )

    def _candidate_roots(self, repo_root: Path | None) -> list[Path]:
        roots: list[Path] = []
        env_root = os.environ.get("SMART_PASTER_ANGELICA_ROOT")
        if env_root:
            roots.append(Path(env_root).expanduser().resolve())
        if repo_root:
            roots.append(repo_root.resolve())
        roots.append(Path.cwd().resolve())
        return roots
