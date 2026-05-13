from __future__ import annotations

import os
import subprocess
import tkinter as tk
from tkinter import ttk


DARK_BG = "#1e1e1e"
DARK_PANEL = "#252526"
DARK_FIELD = "#111827"
DARK_FG = "#e5e7eb"
DARK_MUTED = "#cbd5e1"
DARK_SELECTION = "#374151"
DARK_ACCENT = "#3b82f6"

LIGHT_BG = "#f5f5f5"
LIGHT_PANEL = "#f3f4f6"
LIGHT_FIELD = "#ffffff"
LIGHT_FG = "#111827"
LIGHT_MUTED = "#374151"
LIGHT_SELECTION = "#c7d2fe"
LIGHT_ACCENT = "#2563eb"


def theme_override_mode() -> str:
    return os.environ.get("SMART_PASTER_THEME", "system").strip().lower()


def system_theme_watching_enabled() -> bool:
    return theme_override_mode() in {"", "auto", "system"}


def resolve_theme() -> str:
    """Return 'dark' or 'light'.

    Priority:
    1. SMART_PASTER_THEME=dark/light/system
    2. GNOME color-scheme via gsettings
    3. light fallback
    """
    requested = theme_override_mode()
    if requested in {"dark", "light"}:
        return requested

    if requested not in {"", "auto", "system"}:
        return "light"

    scheme = _gnome_color_scheme()
    if "prefer-dark" in scheme:
        return "dark"
    return "light"


def _gnome_color_scheme() -> str:
    try:
        proc = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=1.0,
        )
    except Exception:
        return ""
    return proc.stdout.strip().strip("'").strip('"')


def apply_system_theme(root: tk.Misc) -> str:
    theme = resolve_theme()
    apply_theme(root, theme)
    return theme


def apply_theme(root: tk.Misc, theme: str) -> None:
    if theme == "dark":
        apply_dark_theme(root)
    else:
        apply_light_theme(root)


def apply_dark_theme(root: tk.Misc) -> None:
    style = ttk.Style(root)
    _safe_theme_use(style)

    root.configure(background=DARK_BG)
    root.option_add("*Background", DARK_BG)
    root.option_add("*Foreground", DARK_FG)
    root.option_add("*insertBackground", DARK_FG)
    root.option_add("*selectBackground", DARK_SELECTION)
    root.option_add("*selectForeground", DARK_FG)

    style.configure(".", background=DARK_BG, foreground=DARK_FG, fieldbackground=DARK_FIELD)
    style.configure("TFrame", background=DARK_BG)
    style.configure("TLabelframe", background=DARK_BG, foreground=DARK_FG)
    style.configure("TLabelframe.Label", background=DARK_BG, foreground=DARK_FG)
    style.configure("TLabel", background=DARK_BG, foreground=DARK_FG)
    style.configure("TButton", background=DARK_PANEL, foreground=DARK_FG)
    style.map("TButton", background=[("active", DARK_SELECTION)], foreground=[("active", DARK_FG)])
    style.configure("TCheckbutton", background=DARK_BG, foreground=DARK_FG)
    style.map("TCheckbutton", background=[("active", DARK_BG)], foreground=[("active", DARK_FG)])
    style.configure("TRadiobutton", background=DARK_BG, foreground=DARK_FG)
    style.map("TRadiobutton", background=[("active", DARK_BG)], foreground=[("active", DARK_FG)])
    style.configure("TEntry", fieldbackground=DARK_FIELD, foreground=DARK_FG, insertcolor=DARK_FG)
    style.configure("TNotebook", background=DARK_BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=DARK_PANEL, foreground=DARK_MUTED, padding=(10, 4))
    style.map(
        "TNotebook.Tab",
        background=[("selected", DARK_SELECTION), ("active", DARK_SELECTION)],
        foreground=[("selected", DARK_FG), ("active", DARK_FG)],
    )
    style.configure("TPanedwindow", background=DARK_BG)

    _apply_text_theme(root, dark=True)


def apply_light_theme(root: tk.Misc) -> None:
    style = ttk.Style(root)
    _safe_theme_use(style)

    root.configure(background=LIGHT_BG)
    root.option_add("*Background", LIGHT_BG)
    root.option_add("*Foreground", LIGHT_FG)
    root.option_add("*insertBackground", LIGHT_FG)
    root.option_add("*selectBackground", LIGHT_SELECTION)
    root.option_add("*selectForeground", LIGHT_FG)

    style.configure(".", background=LIGHT_BG, foreground=LIGHT_FG, fieldbackground=LIGHT_FIELD)
    style.configure("TFrame", background=LIGHT_BG)
    style.configure("TLabelframe", background=LIGHT_BG, foreground=LIGHT_FG)
    style.configure("TLabelframe.Label", background=LIGHT_BG, foreground=LIGHT_FG)
    style.configure("TLabel", background=LIGHT_BG, foreground=LIGHT_FG)
    style.configure("TButton", background=LIGHT_PANEL, foreground=LIGHT_FG)
    style.map("TButton", background=[("active", LIGHT_SELECTION)], foreground=[("active", LIGHT_FG)])
    style.configure("TCheckbutton", background=LIGHT_BG, foreground=LIGHT_FG)
    style.map("TCheckbutton", background=[("active", LIGHT_BG)], foreground=[("active", LIGHT_FG)])
    style.configure("TRadiobutton", background=LIGHT_BG, foreground=LIGHT_FG)
    style.map("TRadiobutton", background=[("active", LIGHT_BG)], foreground=[("active", LIGHT_FG)])
    style.configure("TEntry", fieldbackground=LIGHT_FIELD, foreground=LIGHT_FG, insertcolor=LIGHT_FG)
    style.configure("TNotebook", background=LIGHT_BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=LIGHT_PANEL, foreground=LIGHT_MUTED, padding=(10, 4))
    style.map(
        "TNotebook.Tab",
        background=[("selected", LIGHT_SELECTION), ("active", LIGHT_SELECTION)],
        foreground=[("selected", LIGHT_FG), ("active", LIGHT_FG)],
    )
    style.configure("TPanedwindow", background=LIGHT_BG)

    _apply_text_theme(root, dark=False)


def _safe_theme_use(style: ttk.Style) -> None:
    try:
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass


def _apply_text_theme(widget: tk.Misc, *, dark: bool) -> None:
    if isinstance(widget, tk.Text):
        if dark:
            widget.configure(
                background=DARK_FIELD,
                foreground=DARK_FG,
                insertbackground=DARK_FG,
                selectbackground=DARK_SELECTION,
                selectforeground=DARK_FG,
                borderwidth=1,
                highlightthickness=1,
                highlightbackground=DARK_SELECTION,
                highlightcolor=DARK_ACCENT,
            )
        else:
            widget.configure(
                background=LIGHT_FIELD,
                foreground=LIGHT_FG,
                insertbackground=LIGHT_FG,
                selectbackground=LIGHT_SELECTION,
                selectforeground=LIGHT_FG,
                borderwidth=1,
                highlightthickness=1,
                highlightbackground="#d1d5db",
                highlightcolor=LIGHT_ACCENT,
            )

    for child in widget.winfo_children():
        _apply_text_theme(child, dark=dark)
