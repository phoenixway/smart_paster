from __future__ import annotations

import json
import re
from typing import Any

from .domain import PatchBatch, PatchOperation
from .errors import ParseError, ValidationError
from .modes import SourceMode, TargetMode
from .utils import normalize_newlines


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _coerce_occurrence(value: Any) -> int:
    try:
        occurrence = int(value)
    except Exception:
        occurrence = 1
    return max(1, occurrence)


def operation_from_mapping(data: dict[str, Any], source_kind: str) -> PatchOperation:
    if not isinstance(data, dict):
        raise ValidationError("Patch operation must be an object.")

    filename = _first_present(data, ("filename", "file", "path"))
    if not filename:
        raise ValidationError("Patch operation does not contain filename/file/path.")

    replace_block = _first_present(data, ("replace_block", "replace block", "replace", "new", "content"))
    block_to_replace = _first_present(data, ("block_to_replace", "block to replace", "find", "old"))
    symbol = _first_present(data, ("symbol", "method", "function"))
    mode_raw = _first_present(data, ("mode", "target_mode", "operation"))
    symbol_kind = _first_present(data, ("symbol_kind", "kind"))
    container_name = _first_present(data, ("container_name", "class_name", "owner", "container"))
    occurrence = _coerce_occurrence(data.get("occurrence", 1))
    allow_overwrite = bool(data.get("allow_overwrite", False))

    mode = TargetMode.from_raw(str(mode_raw), default=None) if mode_raw else None

    if replace_block is None:
        raise ValidationError("Patch operation does not contain replace_block/replace/new/content.")

    return PatchOperation(
        filename=str(filename),
        mode=mode,
        replace_block=str(replace_block),
        block_to_replace=str(block_to_replace) if block_to_replace is not None else None,
        symbol=str(symbol) if symbol else None,
        symbol_kind=str(symbol_kind) if symbol_kind else None,
        container_name=str(container_name) if container_name else None,
        occurrence=occurrence,
        allow_overwrite=allow_overwrite,
        source_kind=source_kind,
    )


def parse_special_json(text: str) -> PatchBatch:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValidationError("Special JSON must be an object.")

    version = int(data.get("smart_paster_version", 1))
    atomic = bool(data.get("atomic", True))
    sequential_per_file = bool(data.get("sequential_per_file", True))
    raw_operations = data.get("operations") or data.get("ops") or data.get("patches")

    if raw_operations is None:
        operations = [operation_from_mapping(data, source_kind="special_json")]
    else:
        if not isinstance(raw_operations, list):
            raise ValidationError("Batch field operations/ops/patches must be a list.")
        if not raw_operations:
            raise ValidationError("Batch contains no operations.")
        operations = [operation_from_mapping(op, source_kind="special_json_batch") for op in raw_operations]

    return PatchBatch(
        operations=operations,
        smart_paster_version=version,
        atomic=atomic,
        sequential_per_file=sequential_per_file,
        source_kind="special_json_batch" if len(operations) > 1 else "special_json",
    )


def _strip_single_json_fence(text: str) -> str | None:
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text.strip(), flags=re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return None


def extract_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []

    # Prefer fenced json blocks from normal web-chat answers.
    for match in re.finditer(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE):
        candidates.append(match.group(1).strip())

    stripped = text.strip()
    fenced = _strip_single_json_fence(stripped)
    if fenced and fenced not in candidates:
        candidates.append(fenced)

    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)

    # Last resort: grab the first object that visibly advertises operations/version.
    marker = re.search(r"\{[\s\S]*?(?:smart_paster_version|operations|ops|patches)[\s\S]*\}", text)
    if marker:
        candidates.append(marker.group(0).strip())

    return candidates


def parse_replace_fragment(text: str) -> PatchBatch:
    pattern = re.compile(
        r"BEGIN REPLACE\s*\n"
        r"FILE:\s*(?P<file>.+?)\s*\n"
        r"FIND:\s*\n(?P<find>.*?)\n"
        r"REPLACE:\s*\n(?P<replace>.*?)\n"
        r"END REPLACE",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise ParseError("No BEGIN REPLACE block found.")
    return PatchBatch([
        PatchOperation(
            filename=match.group("file").strip(),
            mode=TargetMode.EXACT_REPLACE,
            block_to_replace=match.group("find"),
            replace_block=match.group("replace"),
            source_kind="replace_fragment",
        )
    ])


def parse_full_file_block(text: str) -> PatchBatch:
    pattern = re.compile(r"BEGIN FILE:\s*(?P<file>.+?)\s*\n(?P<content>.*?)\nEND FILE", re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise ParseError("No BEGIN FILE block found.")
    return PatchBatch([
        PatchOperation(
            filename=match.group("file").strip(),
            mode=TargetMode.FULL_FILE,
            replace_block=match.group("content"),
            source_kind="full_file_block",
        )
    ])


def parse_method_block(text: str) -> PatchBatch:
    pattern = re.compile(
        r"BEGIN METHOD_REPLACE\s*\n"
        r"FILE:\s*(?P<file>.+?)\s*\n"
        r"SYMBOL:\s*(?P<symbol>.+?)\s*\n"
        r"(?:SYMBOL_KIND:\s*(?P<kind>.+?)\s*\n)?"
        r"(?:CONTAINER:\s*(?P<container>.+?)\s*\n)?"
        r"(?:OCCURRENCE:\s*(?P<occurrence>\d+)\s*\n)?"
        r"REPLACE:\s*\n(?P<replace>.*?)\n"
        r"END METHOD_REPLACE",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise ParseError("No BEGIN METHOD_REPLACE block found.")
    return PatchBatch([
        PatchOperation(
            filename=match.group("file").strip(),
            mode=TargetMode.METHOD,
            symbol=match.group("symbol").strip(),
            symbol_kind=(match.group("kind") or "").strip() or None,
            container_name=(match.group("container") or "").strip() or None,
            occurrence=_coerce_occurrence(match.group("occurrence") or 1),
            replace_block=match.group("replace"),
            source_kind="method_block",
        )
    ])


def parse_clipboard_text(text: str, source_mode: SourceMode = SourceMode.AUTO) -> PatchBatch:
    text = normalize_newlines(text)

    if source_mode == SourceMode.SPECIAL_JSON:
        candidate = _strip_single_json_fence(text) or text.strip()
        return parse_special_json(candidate)
    if source_mode == SourceMode.REPLACE_FRAGMENT:
        return parse_replace_fragment(text)
    if source_mode == SourceMode.METHOD_BLOCK:
        return parse_method_block(text)
    if source_mode == SourceMode.FULL_FILE_BLOCK:
        return parse_full_file_block(text)
    if source_mode == SourceMode.DIFF:
        raise ParseError("Unified diff apply is intentionally not implemented. Use JSON patches or exact replace blocks.")

    # AUTO: fenced JSON first, then legacy blocks.
    errors: list[str] = []
    for candidate in extract_json_candidates(text):
        try:
            return parse_special_json(candidate)
        except Exception as exc:
            errors.append(str(exc))

    for parser in (parse_replace_fragment, parse_method_block, parse_full_file_block):
        try:
            return parser(text)
        except Exception as exc:
            errors.append(str(exc))

    raise ParseError("Could not auto-detect a Smart Paster patch. " + " | ".join(errors[-3:]))
