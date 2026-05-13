from __future__ import annotations

from pathlib import Path

from smart_paster.domain import SymbolSpan
from smart_paster.errors import SymbolResolutionError
from smart_paster.providers.angelica_kotlin_provider import AngelicaKotlinSymbolProvider
from smart_paster.providers.base import SymbolProvider
from smart_paster.providers.regex_provider import RegexFallbackSymbolProvider
from smart_paster.providers.tree_sitter_python_provider import TreeSitterPythonSymbolProvider


class SymbolProviderRegistry:
    def __init__(self, providers: list[SymbolProvider] | None = None) -> None:
        self.providers = providers or [
            AngelicaKotlinSymbolProvider(),
            TreeSitterPythonSymbolProvider(),
            RegexFallbackSymbolProvider(),
        ]

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
        errors: list[str] = []
        for provider in self.providers:
            if not provider.supports(path):
                continue
            try:
                return provider.find_span(
                    path=path,
                    old_text=old_text,
                    symbol=symbol,
                    symbol_kind=symbol_kind,
                    container_name=container_name,
                    occurrence=occurrence,
                    repo_root=repo_root,
                )
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
        raise SymbolResolutionError("No symbol provider could resolve the symbol. " + " | ".join(errors))
