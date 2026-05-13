from __future__ import annotations

from enum import Enum


class TargetMode(str, Enum):
    NEW_FILE = "new_file"
    EXACT_REPLACE = "exact_replace"
    METHOD = "method"
    FULL_FILE = "full_file"

    @classmethod
    def from_raw(cls, value: str | None, default: "TargetMode" | None = None) -> "TargetMode":
        if not value:
            if default is None:
                raise ValueError("Target mode is required")
            return default
        raw = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "new": cls.NEW_FILE,
            "new_file": cls.NEW_FILE,
            "create": cls.NEW_FILE,
            "create_file": cls.NEW_FILE,
            "exact": cls.EXACT_REPLACE,
            "exact_replace": cls.EXACT_REPLACE,
            "replace": cls.EXACT_REPLACE,
            "block": cls.EXACT_REPLACE,
            "block_replace": cls.EXACT_REPLACE,
            "method": cls.METHOD,
            "method_replace": cls.METHOD,
            "symbol": cls.METHOD,
            "symbol_replace": cls.METHOD,
            "full": cls.FULL_FILE,
            "file": cls.FULL_FILE,
            "full_file": cls.FULL_FILE,
            "replace_file": cls.FULL_FILE,
        }
        if raw not in aliases:
            raise ValueError(f"Unsupported target mode: {value}")
        return aliases[raw]


class SourceMode(str, Enum):
    AUTO = "auto"
    SPECIAL_JSON = "special_json"
    METHOD_BLOCK = "method_block"
    REPLACE_FRAGMENT = "replace_fragment"
    FULL_FILE_BLOCK = "full_file_block"
    DIFF = "diff"
