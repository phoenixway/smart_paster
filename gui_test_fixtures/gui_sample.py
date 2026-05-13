from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def normalize_name(value: str) -> str:
    """Normalize a display name."""
    cleaned = value.strip().lower()
    return " ".join(cleaned.split())


def calculate_score(values: Iterable[int]) -> int:
    total = 0
    for value in values:
        if value > 0:
            total += value
    return total


def duplicate_name() -> str:
    return "top-level"


@dataclass
class UserProfile:
    user_id: int
    name: str
    active: bool = True

    @property
    def display_name(self) -> str:
        return normalize_name(self.name).title()

    def duplicate_name(self) -> str:
        return f"profile:{self.user_id}"

    def calculate_score(self, values: Iterable[int]) -> int:
        base = calculate_score(values)
        if self.active:
            return base + 10
        return base

    def method_with_nested_function(self, raw: str) -> str:
        def normalize_name(value: str) -> str:
            return value.strip()

        return normalize_name(raw).upper()
