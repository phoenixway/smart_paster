from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import platform
import traceback


class DiagnosticLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def add(self, event: str, **data: Any) -> None:
        self.events.append(
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "event": event,
                "data": _jsonable(data),
            }
        )

    def add_exception(self, event: str, exc: BaseException, **data: Any) -> None:
        self.add(
            event,
            error_type=type(exc).__name__,
            error=str(exc),
            traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            **data,
        )

    def tail_text(self, limit: int = 80) -> str:
        rows = self.events[-limit:]
        return "\n".join(
            f"[{row['ts']}] {row['event']}: {json.dumps(row['data'], ensure_ascii=False, sort_keys=True)}"
            for row in rows
        )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def build_dump_text(
    *,
    repo_root: Path,
    input_text: str,
    output_text: str,
    settings: dict[str, Any],
    log: DiagnosticLog,
    git_status: str,
    git_diff_stat: str,
    plan_summary: dict[str, Any] | None = None,
) -> str:
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "platform": {
            "python": platform.python_version(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "repo_root": str(repo_root),
        "settings": _jsonable(settings),
        "plan_summary": _jsonable(plan_summary),
        "events": log.events,
    }
    return "\n".join(
        [
            "# Smart Paster diagnostic dump",
            "",
            "## Metadata",
            "```json",
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
            "## Git status --short",
            "```text",
            git_status.rstrip(),
            "```",
            "",
            "## Git diff --stat",
            "```text",
            git_diff_stat.rstrip(),
            "```",
            "",
            "## Incoming text",
            "```text",
            input_text.rstrip(),
            "```",
            "",
            "## Preview / log pane",
            "```text",
            output_text.rstrip(),
            "```",
            "",
        ]
    )
