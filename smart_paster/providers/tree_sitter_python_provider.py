from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

from smart_paster.domain import SymbolSpan
from smart_paster.errors import SymbolResolutionError
from smart_paster.providers.base import SymbolProvider


class TreeSitterPythonSymbolProvider(SymbolProvider):
    """Optional Tree-sitter provider for Python symbols.

    Loading order:
    1. Angelica's modules.code_parser.CodeParser via SMART_PASTER_ANGELICA_ROOT,
       repo root, cwd, or importable sys.path. This is best when compiled grammar
       libraries already live inside Angelica.
    2. tree_sitter_python package, if installed.
    3. SMART_PASTER_PYTHON_TS_LIB or common repo-local .so candidates.

    The provider is intentionally optional. If Tree-sitter is unavailable or the
    symbol cannot be resolved, the registry can fall back to RegexFallbackSymbolProvider.
    """

    name = "tree_sitter_python"

    def __init__(self) -> None:
        self._language: Any | None = None
        self._load_error: str | None = None

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".py"

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
        if not symbol:
            raise SymbolResolutionError("Python Tree-sitter provider requires a symbol name.")

        try:
            from tree_sitter import Parser
        except Exception as exc:
            raise SymbolResolutionError(f"tree_sitter package is unavailable: {exc}") from exc

        language = self._get_language(repo_root=repo_root)
        parser = Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(language)
        else:
            parser.language = language

        content_bytes = old_text.encode("utf-8", errors="replace")
        tree = parser.parse(content_bytes)
        matches: list[dict[str, Any]] = []

        normalized_kind = self._normalize_symbol_kind(symbol_kind)

        def walk(node: Any) -> None:
            info = self._build_symbol_info(node, old_text, content_bytes)
            if info is not None:
                if (
                    info["name"] == symbol
                    and self._kind_matches(normalized_kind, info)
                    and self._container_matches(info, container_name)
                ):
                    matches.append(info)
            for child in getattr(node, "children", []):
                walk(child)

        walk(tree.root_node)
        matches.sort(key=lambda item: (item["owner_name"] or "", item["kind"], item["start_line"], item["start_col"]))

        if not matches:
            kind_hint = "" if normalized_kind in {"auto", "unknown"} else f" ({normalized_kind})"
            owner_hint = f" in container '{container_name}'" if container_name else ""
            raise SymbolResolutionError(f"Python symbol '{symbol}'{kind_hint} was not found{owner_hint} in {path}.")

        if occurrence > len(matches):
            raise SymbolResolutionError(
                f"Python symbol '{symbol}' has {len(matches)} matches, occurrence={occurrence} requested. "
                f"Candidates: {[self._candidate_summary(item) for item in matches]}"
            )

        if len(matches) > 1 and container_name is None and occurrence == 1:
            raise SymbolResolutionError(
                f"Multiple Python symbols named '{symbol}' were found. Specify container_name, symbol_kind, or occurrence. "
                f"Candidates: {[self._candidate_summary(item) for item in matches]}"
            )

        selected = matches[occurrence - 1]
        return SymbolSpan(
            provider=self.name,
            symbol=selected["name"],
            symbol_kind=selected["kind"],
            container_name=selected["owner_name"],
            start_line=selected["start_line"],
            end_line=selected["end_line"],
            start_col=selected["start_col"],
            end_col=selected["end_col"],
            selected_text=selected["selected_text"],
            candidates=[self._candidate_summary(item) for item in matches],
        )

    def _get_language(self, repo_root: Path | None) -> Any:
        if self._language is not None:
            return self._language

        errors: list[str] = []

        try:
            self._language = self._load_from_angelica_code_parser(repo_root)
            return self._language
        except Exception as exc:
            errors.append(f"Angelica CodeParser: {exc}")

        try:
            self._language = self._load_from_tree_sitter_python_package()
            return self._language
        except Exception as exc:
            errors.append(f"tree_sitter_python package: {exc}")

        for lib_path in self._compiled_library_candidates(repo_root):
            try:
                self._language = self._load_from_shared_library(lib_path)
                return self._language
            except Exception as exc:
                errors.append(f"{lib_path}: {exc}")

        self._load_error = " | ".join(errors)
        raise SymbolResolutionError(f"Could not load Python Tree-sitter language. {self._load_error}")

    def _load_from_angelica_code_parser(self, repo_root: Path | None) -> Any:
        added: list[str] = []
        for root in self._candidate_roots(repo_root):
            root_s = str(root)
            if root_s not in sys.path:
                sys.path.insert(0, root_s)
                added.append(root_s)
        try:
            module = importlib.import_module("modules.code_parser")
            code_parser = module.CodeParser()
            language = code_parser._get_language(".py")
            if language is None:
                raise SymbolResolutionError("CodeParser returned no language for .py")
            return language
        finally:
            # Keep sys.path additions: provider may be reused and Angelica imports may need them.
            pass

    def _load_from_tree_sitter_python_package(self) -> Any:
        from tree_sitter import Language
        import tree_sitter_python

        raw_language = tree_sitter_python.language()
        try:
            return Language(raw_language)
        except TypeError:
            return raw_language

    def _load_from_shared_library(self, lib_path: Path) -> Any:
        if not lib_path.exists():
            raise FileNotFoundError(str(lib_path))
        from tree_sitter import Language

        # Older py-tree-sitter supports Language(path, name). Newer versions often
        # prefer grammar packages, but this remains useful for Angelica-style .so libs.
        try:
            return Language(str(lib_path), "python")
        except TypeError as exc:
            raise SymbolResolutionError(
                "This tree_sitter version does not support direct Language(path, name). "
                "Prefer Angelica CodeParser or tree_sitter_python package."
            ) from exc

    def _candidate_roots(self, repo_root: Path | None) -> list[Path]:
        roots: list[Path] = []
        env_root = os.environ.get("SMART_PASTER_ANGELICA_ROOT")
        if env_root:
            roots.append(Path(env_root).expanduser().resolve())
        if repo_root:
            roots.append(repo_root.resolve())
        roots.append(Path.cwd().resolve())
        unique: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            if root not in seen:
                unique.append(root)
                seen.add(root)
        return unique

    def _compiled_library_candidates(self, repo_root: Path | None) -> list[Path]:
        candidates: list[Path] = []
        env_lib = os.environ.get("SMART_PASTER_PYTHON_TS_LIB")
        if env_lib:
            candidates.append(Path(env_lib).expanduser().resolve())
        for root in self._candidate_roots(repo_root):
            candidates.extend(
                [
                    root / "libs" / "python.so",
                    root / "libs" / "tree-sitter-python.so",
                    root / "tree_sitter_libs" / "python.so",
                    root / "build" / "python.so",
                ]
            )
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in candidates:
            if path not in seen:
                unique.append(path)
                seen.add(path)
        return unique

    def _normalize_symbol_kind(self, symbol_kind: str | None) -> str:
        value = str(symbol_kind or "auto").strip().lower()
        aliases = {
            "": "auto",
            "any": "auto",
            "symbol": "auto",
            "def": "function",
            "async_function": "function",
            "method": "method",
            "class_definition": "class",
            "function_definition": "function",
        }
        return aliases.get(value, value)

    def _kind_matches(self, requested_kind: str, info: dict[str, Any]) -> bool:
        if requested_kind in {"auto", "unknown"}:
            return True
        if requested_kind == "method":
            return info["kind"] == "method"
        if requested_kind == "function":
            return info["kind"] == "function"
        if requested_kind in {"local_function", "nested_function"}:
            return info["kind"] == "local_function"
        return info["kind"] == requested_kind

    def _container_matches(self, info: dict[str, Any], container_name: str | None) -> bool:
        if not container_name:
            return True
        candidate = str(container_name).strip()
        if not candidate:
            return True
        return candidate == info["owner_name"] or candidate in info["owner_chain"]

    def _build_symbol_info(self, node: Any, content: str, content_bytes: bytes) -> dict[str, Any] | None:
        # Decorators wrap function_definition/class_definition in decorated_definition.
        actual = node
        span_node = node
        if getattr(node, "type", None) == "decorated_definition":
            for child in node.children:
                if child.type in {"function_definition", "class_definition"}:
                    actual = child
                    span_node = node
                    break
            else:
                return None

        if actual.type not in {"function_definition", "class_definition"}:
            return None

        name_node = actual.child_by_field_name("name") if hasattr(actual, "child_by_field_name") else None
        if name_node is None:
            return None
        name = content_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
        if not name:
            return None

        class_chain = self._find_owner_chain(actual, content_bytes, owner_type="class_definition")
        function_chain = self._find_owner_chain(actual, content_bytes, owner_type="function_definition")
        owner_chain = class_chain + function_chain
        owner_name = class_chain[0] if class_chain else None
        enclosing_function = function_chain[0] if function_chain else None
        if actual.type == "class_definition":
            kind = "class"
        elif owner_name:
            kind = "method"
        elif enclosing_function:
            kind = "local_function"
        else:
            kind = "function"

        selected_text = content_bytes[span_node.start_byte:span_node.end_byte].decode("utf-8", errors="replace")
        start_line = span_node.start_point[0] + 1
        start_col = span_node.start_point[1] + 1
        end_line = span_node.end_point[0] + 1
        end_col = span_node.end_point[1] + 1

        return {
            "name": name,
            "kind": kind,
            "owner_name": owner_name,
            "owner_chain": owner_chain,
            "enclosing_function": enclosing_function,
            "start_line": start_line,
            "end_line": max(start_line, end_line),
            "start_col": start_col,
            "end_col": end_col,
            "selected_text": selected_text,
        }

    def _find_owner_chain(self, node: Any, content_bytes: bytes, *, owner_type: str) -> list[str]:
        owners: list[str] = []
        current = getattr(node, "parent", None)
        while current is not None:
            actual = current
            if getattr(current, "type", None) == "decorated_definition":
                for child in current.children:
                    if child.type == owner_type:
                        actual = child
                        break
            if getattr(actual, "type", None) == owner_type:
                name_node = actual.child_by_field_name("name") if hasattr(actual, "child_by_field_name") else None
                if name_node is not None:
                    name = content_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    if name:
                        owners.append(name)
            current = getattr(current, "parent", None)
        return owners

    def _candidate_summary(self, item: dict[str, Any]) -> dict[str, object]:
        return {
            "name": item["name"],
            "kind": item["kind"],
            "owner_name": item["owner_name"],
            "start_line": item["start_line"],
            "end_line": item["end_line"],
            "enclosing_function": item.get("enclosing_function"),
        }
