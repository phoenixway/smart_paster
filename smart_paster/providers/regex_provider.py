from __future__ import annotations

import re
from pathlib import Path

from smart_paster.domain import SymbolSpan
from smart_paster.errors import SymbolResolutionError
from smart_paster.providers.base import SymbolProvider
from smart_paster.utils import detect_language, line_col_from_offset, line_from_end_offset


class RegexFallbackSymbolProvider(SymbolProvider):
    name = "regex_fallback"

    def supports(self, path: Path) -> bool:
        return detect_language(path) in {"python", "kotlin", "java", "go"}

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
        lang = detect_language(path)
        if lang == "python":
            start, end = _find_python_def_span(
                old_text,
                symbol,
                occurrence=occurrence,
                symbol_kind=symbol_kind,
                container_name=container_name,
            )
        else:
            start, end = _find_braced_symbol_span(old_text, symbol, lang, occurrence=occurrence)
        start_line, start_col = line_col_from_offset(old_text, start)
        end_line = line_from_end_offset(old_text, end)
        _end_line_for_col, end_col = line_col_from_offset(old_text, max(start, end - 1))
        return SymbolSpan(
            provider=self.name,
            symbol=symbol,
            symbol_kind=symbol_kind or "auto",
            container_name=container_name,
            start_line=start_line,
            end_line=end_line,
            start_col=start_col,
            end_col=end_col,
            selected_text=old_text[start:end],
        )


def _find_python_def_span(
    text: str,
    symbol: str,
    occurrence: int = 1,
    symbol_kind: str | None = None,
    container_name: str | None = None,
) -> tuple[int, int]:
    lines = text.splitlines(keepends=True)
    pattern = re.compile(rf"^(?P<indent>[ \t]*)(?:async\s+def|def|class)\s+{re.escape(symbol)}\b")
    class_pattern = re.compile(r"^(?P<indent>[ \t]*)class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b")
    normalized_kind = str(symbol_kind or "auto").strip().lower()
    matches: list[tuple[int, int]] = []

    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)

    class_stack: list[tuple[str, int]] = []

    for i, line in enumerate(lines):
        raw_indent = re.match(r"^[ \t]*", line).group(0)
        indent = len(raw_indent.replace("\t", "    "))
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            while class_stack and indent <= class_stack[-1][1]:
                class_stack.pop()

        class_match = class_pattern.match(line)
        if class_match:
            class_stack.append((class_match.group("name"), indent))

        match = pattern.match(line)
        if not match:
            continue

        owner_class = class_stack[-1][0] if class_stack and indent > class_stack[-1][1] else None
        is_top_level = indent == 0
        is_method = owner_class is not None and not is_top_level

        if normalized_kind == "function" and not is_top_level:
            continue
        if normalized_kind == "method" and not is_method:
            continue
        if container_name and owner_class != container_name:
            continue

        start = offsets[i]
        end = len(text)
        for j in range(i + 1, len(lines)):
            next_stripped = lines[j].strip()
            if not next_stripped:
                continue
            current_indent = len(re.match(r"^[ \t]*", lines[j]).group(0).replace("\t", "    "))
            if current_indent <= indent and not lines[j].lstrip().startswith(("#", "@")):
                end = offsets[j]
                break
        matches.append((start, end))

    return _select_occurrence(matches, symbol, "python", occurrence)


def _find_braced_symbol_span(text: str, symbol: str, lang: str, occurrence: int = 1) -> tuple[int, int]:
    if lang == "kotlin":
        decl = re.compile(rf"(?m)^[ \t]*(?:public|private|protected|internal|override|suspend|inline|tailrec|operator|infix|open|final|abstract|data|sealed|class|fun|val|var|companion|object|enum|interface|annotation|value|expect|actual|external|const|lateinit|inner|constructor|init|where|\s)*\b(?:fun|class|object|interface)\s+{re.escape(symbol)}\b")
    elif lang == "java":
        decl = re.compile(rf"(?m)^[ \t]*(?:public|private|protected|static|final|abstract|synchronized|native|strictfp|default|\s)*[\w<>\[\], ?]+\s+{re.escape(symbol)}\s*\(")
    elif lang == "go":
        decl = re.compile(rf"(?m)^[ \t]*func\s+(?:\([^)]*\)\s*)?{re.escape(symbol)}\s*\(")
    else:
        raise SymbolResolutionError(f"Regex fallback does not support language: {lang}")

    matches = list(decl.finditer(text))
    selected_start, search_from = _select_occurrence(
        [(match.start(), match.end()) for match in matches], symbol, lang, occurrence
    )
    brace_start = text.find("{", search_from)
    if brace_start < 0:
        raise SymbolResolutionError(f"Symbol '{symbol}' declaration has no opening brace.")

    depth = 0
    in_string: str | None = None
    escape = False
    i = brace_start
    while i < len(text):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_string:
                in_string = None
            i += 1
            continue

        if ch in {'"', "'"}:
            in_string = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return selected_start, i + 1
        i += 1

    raise SymbolResolutionError(f"Could not find balanced closing brace for symbol '{symbol}'.")


def _select_occurrence(matches: list[tuple[int, int]], symbol: str, lang: str, occurrence: int) -> tuple[int, int]:
    if not matches:
        raise SymbolResolutionError(f"Symbol '{symbol}' was not found in {lang}.")
    if occurrence > len(matches):
        raise SymbolResolutionError(
            f"Symbol '{symbol}' has {len(matches)} matches in {lang}, occurrence={occurrence} requested."
        )
    if len(matches) > 1 and occurrence == 1:
        raise SymbolResolutionError(
            f"Symbol '{symbol}' matched {len(matches)} declarations in {lang}. Specify occurrence to disambiguate."
        )
    return matches[occurrence - 1]
