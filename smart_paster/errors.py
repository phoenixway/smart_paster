from __future__ import annotations


class SmartPasterError(Exception):
    """Base error for guarded patch parsing/applying failures."""


class ParseError(SmartPasterError):
    """Incoming clipboard text could not be parsed as a patch."""


class ValidationError(SmartPasterError):
    """Patch is structurally valid but unsafe or incomplete."""


class ApplyError(SmartPasterError):
    """Patch could not be applied safely."""


class SymbolResolutionError(SmartPasterError):
    """No symbol provider could locate the requested symbol exactly."""
