from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Allow running this file directly from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smart_paster.apply_engine import ApplyEngine
from smart_paster.clipboard_parser import parse_clipboard_text
from smart_paster.modes import TargetMode


SAMPLE = 'from __future__ import annotations\n\nfrom dataclasses import dataclass\nfrom typing import Iterable\n\n\ndef normalize_name(value: str) -> str:\n    """Normalize a display name for stable comparisons."""\n    cleaned = value.strip().lower()\n    return " ".join(cleaned.split())\n\n\ndef calculate_score(values: Iterable[int]) -> int:\n    total = 0\n    for value in values:\n        if value > 0:\n            total += value\n    return total\n\n\n@dataclass\nclass UserProfile:\n    user_id: int\n    name: str\n    active: bool = True\n\n    def duplicate_name(self) -> str:\n        return f"profile:{self.user_id}"\n\n\nclass AdminProfile(UserProfile):\n    def duplicate_name(self) -> str:\n        return f"admin:{self.user_id}"\n'


def fenced(obj: dict) -> str:
    return "Human explanation.\n\n```json\n" + json.dumps(obj, indent=2) + "\n```\nTests: pytest -q"


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.PIPE)
        target = root / "examples/fixtures/sample_symbols.py"
        target.parent.mkdir(parents=True)
        target.write_text(SAMPLE)
        subprocess.run(["git", "add", "examples/fixtures/sample_symbols.py"], cwd=root, check=True)

        engine = ApplyEngine()
        original = target.read_text()

        batch = parse_clipboard_text(
            fenced(
                {
                    "operations": [
                        {
                            "mode": "method",
                            "filename": "examples/fixtures/sample_symbols.py",
                            "symbol": "normalize_name",
                            "symbol_kind": "function",
                            "replace_block": "def normalize_name(value: str) -> str:\n    cleaned = value.strip().casefold()\n    return '-'.join(cleaned.split())",
                        }
                    ]
                }
            )
        )
        plan = engine.plan(repo_root=root, batch=batch, default_mode=TargetMode.EXACT_REPLACE)
        assert len(plan.changed) == 1

        dry = engine.apply_plan(repo_root=root, plan=plan, dry_run=True)
        assert dry.dry_run is True
        assert target.read_text() == original, "dry-run changed the file"

        real = engine.apply_plan(repo_root=root, plan=plan, dry_run=False, backup=True)
        assert len(real.written_files) == 1
        assert "casefold" in target.read_text()
        assert list((root / ".smart-paster-backups").glob("*.bak"))

        batch2 = parse_clipboard_text(
            json.dumps(
                {
                    "operations": [
                        {
                            "mode": "exact_replace",
                            "filename": "examples/fixtures/sample_symbols.py",
                            "block_to_replace": "casefold()",
                            "replace_block": "lower()",
                        },
                        {
                            "mode": "exact_replace",
                            "filename": "examples/fixtures/sample_symbols.py",
                            "block_to_replace": "'-'.join",
                            "replace_block": "' '.join",
                        },
                    ]
                }
            )
        )
        plan2 = engine.plan(repo_root=root, batch=batch2)
        engine.apply_plan(repo_root=root, plan=plan2, dry_run=False, backup=False)
        assert "casefold" not in target.read_text()
        assert "'-'.join" not in target.read_text()

        ambiguous = parse_clipboard_text(
            json.dumps(
                {
                    "operations": [
                        {
                            "mode": "method",
                            "filename": "examples/fixtures/sample_symbols.py",
                            "symbol": "duplicate_name",
                            "symbol_kind": "method",
                            "replace_block": "def duplicate_name(self) -> str:\n        return 'x'",
                        }
                    ]
                }
            )
        )
        try:
            engine.plan(repo_root=root, batch=ambiguous)
        except Exception as exc:
            assert "duplicate_name" in str(exc)
        else:
            raise AssertionError("expected ambiguity failure")

        print("ALL SMOKE TESTS PASSED")
        print("git status --short:")
        print(subprocess.run(["git", "status", "--short"], cwd=root, text=True, stdout=subprocess.PIPE).stdout)
        print("git diff --stat:")
        print(subprocess.run(["git", "diff", "--stat"], cwd=root, text=True, stdout=subprocess.PIPE).stdout)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
