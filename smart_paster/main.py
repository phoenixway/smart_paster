from __future__ import annotations

from .gui_tk import SmartPasterApp


def main() -> int:
    app = SmartPasterApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
