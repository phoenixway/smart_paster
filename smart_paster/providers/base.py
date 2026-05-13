from __future__ import annotations

from pathlib import Path

from smart_paster.domain import SymbolSpan


class SymbolProvider:
    name = "base"

    def supports(self, path: Path) -> bool:
        return False

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
        raise NotImplementedError
