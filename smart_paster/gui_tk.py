from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .apply_engine import ApplyEngine
from .clipboard_parser import parse_clipboard_text
from .diagnostics import DiagnosticLog, build_dump_text
from .diff_preview import unified_preview
from .modes import SourceMode, TargetMode
from .utils import discover_git_root, is_git_worktree, run_command


class SmartPasterApp(tk.Tk):
    """Tkinter GUI shell for Smart Paster.

    The GUI is intentionally thin: parsing/planning/apply live in the package
    core. This file owns layout, clipboard handling, and diagnostics UI.
    """

    BUTTON_WRAP_COLUMNS = 4
    RADIO_WRAP_COLUMNS = 3

    def __init__(self) -> None:
        super().__init__()
        self.title("Smart Paster")
        self.geometry("1180x780")
        self.minsize(760, 600)

        cwd = Path.cwd().resolve()
        git_root = discover_git_root(cwd) or cwd
        self.engine = ApplyEngine()
        self.last_plan = None
        self.diagnostics = DiagnosticLog()
        self._last_clipboard_text = ""

        self.repo_root_var = tk.StringVar(value=str(git_root))
        self.target_path_var = tk.StringVar(value="")
        self.symbol_var = tk.StringVar(value="")
        self.target_mode_var = tk.StringVar(value=TargetMode.EXACT_REPLACE.value)
        self.source_mode_var = tk.StringVar(value=SourceMode.AUTO.value)
        self.dry_run_var = tk.BooleanVar(value=True)
        self.backup_var = tk.BooleanVar(value=True)
        self.auto_watch_clipboard_var = tk.BooleanVar(value=True)

        self._build_ui()
        self.diagnostics.add("app_started", repo_root=str(git_root))
        self.after(900, self.poll_clipboard)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=8)
        root.pack(fill=tk.BOTH, expand=True)

        # Top controls are grouped into a horizontal paned area. When the window
        # gets narrow, each group wraps its internal controls instead of pushing
        # buttons off-screen.
        controls = ttk.Frame(root)
        controls.pack(fill=tk.X, pady=(0, 8))
        controls.columnconfigure(0, weight=3)
        controls.columnconfigure(1, weight=2)

        target = ttk.LabelFrame(controls, text="Target")
        target.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        target.columnconfigure(1, weight=1)

        source = ttk.LabelFrame(controls, text="Source / Actions")
        source.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        source.columnconfigure(0, weight=1)

        self._build_target_controls(target)
        self._build_source_controls(source)

        pane = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(pane, text="Incoming text / clipboard")
        right = ttk.LabelFrame(pane, text="Preview / log")
        pane.add(left, weight=1)
        pane.add(right, weight=1)

        self.input_text = scrolledtext.ScrolledText(left, wrap=tk.NONE, undo=True)
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.output_text = scrolledtext.ScrolledText(right, wrap=tk.NONE, undo=True)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.log(
            "Paste a web-chat answer containing a fenced ```json Smart Paster patch.\n"
            "Valid patches synchronize Target fields and auto-preview.\n"
            "Use Dump when something smells odd: it writes a diagnostic report.\n"
        )

    def _build_target_controls(self, parent: ttk.LabelFrame) -> None:
        ttk.Label(parent, text="Repo root:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(parent, textvariable=self.repo_root_var).grid(row=0, column=1, sticky="ew", padx=6, pady=4)
        ttk.Button(parent, text="Browse", command=self.choose_repo_root).grid(row=0, column=2, padx=6, pady=4)

        ttk.Label(parent, text="Target file:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(parent, textvariable=self.target_path_var).grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        ttk.Button(parent, text="Pick", command=self.choose_target_file).grid(row=1, column=2, padx=6, pady=4)

        ttk.Label(parent, text="Symbol:").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(parent, textvariable=self.symbol_var).grid(row=2, column=1, sticky="ew", padx=6, pady=4)

        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=6, pady=(4, 6))
        self._grid_radios(
            mode_frame,
            self.target_mode_var,
            [
                ("New file", TargetMode.NEW_FILE.value),
                ("Exact replace", TargetMode.EXACT_REPLACE.value),
                ("Method", TargetMode.METHOD.value),
                ("Full file", TargetMode.FULL_FILE.value),
            ],
            columns=2,
        )

    def _build_source_controls(self, parent: ttk.LabelFrame) -> None:
        source_mode_frame = ttk.Frame(parent)
        source_mode_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        self._grid_radios(
            source_mode_frame,
            self.source_mode_var,
            [
                ("Auto", SourceMode.AUTO.value),
                ("Special JSON", SourceMode.SPECIAL_JSON.value),
                ("Method block", SourceMode.METHOD_BLOCK.value),
                ("Fragment", SourceMode.REPLACE_FRAGMENT.value),
                ("Diff", SourceMode.DIFF.value),
                ("Full file", SourceMode.FULL_FILE_BLOCK.value),
            ],
            columns=2,
        )

        checks = ttk.Frame(parent)
        checks.grid(row=1, column=0, sticky="ew", padx=6, pady=(2, 4))
        for index, widget in enumerate(
            [
                ttk.Checkbutton(checks, text="Dry run", variable=self.dry_run_var),
                ttk.Checkbutton(checks, text="Backup", variable=self.backup_var),
                ttk.Checkbutton(checks, text="Watch clipboard", variable=self.auto_watch_clipboard_var),
            ]
        ):
            widget.grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 12), pady=2)

        buttons = ttk.Frame(parent)
        buttons.grid(row=2, column=0, sticky="ew", padx=6, pady=(4, 6))
        self._grid_buttons(
            buttons,
            [
                ("Paste", self.paste_clipboard),
                ("Preview", self.preview),
                ("Apply", self.apply),
                ("Open target", self.open_target),
                ("Intro prompt", self.open_intro_prompt),
                ("Git diff", self.show_git_diff),
                ("Dump", self.dump_diagnostics),
                ("Clear", self.clear_text),
            ],
            columns=self.BUTTON_WRAP_COLUMNS,
        )

    def _grid_radios(self, parent: ttk.Frame, variable: tk.StringVar, items: list[tuple[str, str]], *, columns: int) -> None:
        for index, (label, value) in enumerate(items):
            row, col = divmod(index, columns)
            ttk.Radiobutton(parent, text=label, value=value, variable=variable).grid(
                row=row, column=col, sticky="w", padx=(0, 12), pady=2
            )
        for col in range(columns):
            parent.columnconfigure(col, weight=1)

    def _grid_buttons(self, parent: ttk.Frame, items: list[tuple[str, object]], *, columns: int) -> None:
        for index, (label, command) in enumerate(items):
            row, col = divmod(index, columns)
            ttk.Button(parent, text=label, command=command).grid(row=row, column=col, sticky="ew", padx=3, pady=3)
        for col in range(columns):
            parent.columnconfigure(col, weight=1)

    def choose_repo_root(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.repo_root_var.get() or str(Path.cwd()))
        if selected:
            self.repo_root_var.set(str(Path(selected).resolve()))
            self.diagnostics.add("choose_repo_root", repo_root=self.repo_root_var.get())

    def choose_target_file(self) -> None:
        repo = Path(self.repo_root_var.get()).resolve()
        selected = filedialog.askopenfilename(initialdir=str(repo))
        if selected:
            path = Path(selected).resolve()
            try:
                self.target_path_var.set(str(path.relative_to(repo)))
            except ValueError:
                self.target_path_var.set(str(path))
            self.diagnostics.add("choose_target_file", target=self.target_path_var.get())

    def paste_clipboard(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            messagebox.showerror("Clipboard", "Clipboard is empty or not text.")
            return
        self.load_incoming_text(text, trigger="paste_button", auto_preview=True)

    def load_incoming_text(self, text: str, *, trigger: str, auto_preview: bool) -> None:
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", text)
        self._last_clipboard_text = text

        try:
            batch = parse_clipboard_text(text, SourceMode.AUTO)
        except Exception as exc:
            self.diagnostics.add("incoming_text_loaded", trigger=trigger, chars=len(text), legal_patch=False, error=str(exc))
            self.log(f"Loaded incoming text from {trigger}; no legal Smart Paster patch detected.\n")
            return

        self.sync_ui_from_batch(batch, trigger=trigger)
        self.diagnostics.add(
            "incoming_patch_loaded",
            trigger=trigger,
            chars=len(text),
            operations=len(batch.operations),
            first_filename=batch.operations[0].filename if batch.operations else None,
        )
        self.log(f"Loaded valid Smart Paster patch from {trigger}; UI target fields synchronized.\n")
        if auto_preview:
            self.preview()

    def sync_ui_from_batch(self, batch, *, trigger: str) -> None:
        if not batch.operations:
            return

        first = batch.operations[0]
        self.target_path_var.set(first.filename)

        if first.mode is not None:
            self.target_mode_var.set(first.mode.value)

        if first.symbol:
            self.symbol_var.set(first.symbol)
        else:
            self.symbol_var.set("")

        self.diagnostics.add(
            "ui_synced_from_patch",
            trigger=trigger,
            operations=len(batch.operations),
            target_path=first.filename,
            target_mode=first.mode.value if first.mode else None,
            symbol=first.symbol,
        )

    def poll_clipboard(self) -> None:
        try:
            if self.auto_watch_clipboard_var.get():
                try:
                    text = self.clipboard_get()
                except tk.TclError:
                    text = ""
                if text and text != self._last_clipboard_text and self._clipboard_text_is_legal_patch(text):
                    self.load_incoming_text(text, trigger="clipboard_watcher", auto_preview=True)
        finally:
            self.after(900, self.poll_clipboard)

    def _clipboard_text_is_legal_patch(self, text: str) -> bool:
        try:
            parse_clipboard_text(text, SourceMode.AUTO)
            return True
        except Exception:
            return False

    def clear_text(self) -> None:
        self.input_text.delete("1.0", tk.END)
        self.output_text.delete("1.0", tk.END)
        self.diagnostics.add("clear_text")

    def log(self, message: str) -> None:
        self.output_text.insert(tk.END, message)
        if not message.endswith("\n"):
            self.output_text.insert(tk.END, "\n")
        self.output_text.see(tk.END)

    def get_input(self) -> str:
        return self.input_text.get("1.0", tk.END).rstrip("\n")

    def build_plan(self):
        repo_root = Path(self.repo_root_var.get()).resolve()
        batch = parse_clipboard_text(self.get_input(), SourceMode(self.source_mode_var.get()))
        self.sync_ui_from_batch(batch, trigger="build_plan")

        # JSON/patch paths are authoritative. The Target file field is synchronized
        # from the patch and used for visibility/open-target, not as a stale override.
        plan = self.engine.plan(
            repo_root=repo_root,
            batch=batch,
            default_mode=TargetMode(self.target_mode_var.get()),
            ui_target_override=None,
            ui_symbol_override=None,
        )
        self.diagnostics.add("plan_built", operations=len(plan.operations), changed=len(plan.changed), summary=self.plan_summary(plan))
        return plan

    def preview(self) -> None:
        try:
            plan = self.build_plan()
            self.last_plan = plan
            self.output_text.delete("1.0", tk.END)
            self.log(f"Operations: {len(plan.operations)}")
            self.log(f"Changed operations: {len(plan.changed)}")
            for index, op in enumerate(plan.operations, start=1):
                self.log(f"\n=== Operation {index}: {op.rel_name} ===")
                self.log(f"Source kind: {op.operation.source_kind}")
                self.log(f"Mode: {(op.operation.mode or TargetMode(self.target_mode_var.get())).value}")
                if op.provider_name:
                    self.log(f"Symbol provider: {op.provider_name}")
                self.log(f"Old size: {len(op.old_text)} bytes")
                self.log(f"New size: {len(op.new_text)} bytes")
                self.log("\n--- Preview diff ---\n")
                diff = unified_preview(op.old_text, op.new_text, op.rel_name)
                self.log(diff if diff.strip() else "No changes.")
        except Exception as exc:
            self.diagnostics.add_exception("preview_failed", exc)
            self.output_text.delete("1.0", tk.END)
            self.log(f"ERROR: {exc}")
            messagebox.showerror("Preview failed", str(exc))

    def apply(self) -> None:
        try:
            plan = self.build_plan()
            self.last_plan = plan
            repo_root = Path(self.repo_root_var.get()).resolve()
            self.output_text.delete("1.0", tk.END)
            self.log(f"Operations: {len(plan.operations)}")
            self.log(f"Dry run: {self.dry_run_var.get()}")

            before_disk = self._snapshot_existing_targets(plan)
            result = self.engine.apply_plan(
                repo_root=repo_root,
                plan=plan,
                dry_run=self.dry_run_var.get(),
                backup=self.backup_var.get(),
            )
            self.diagnostics.add(
                "apply_plan_returned",
                dry_run=result.dry_run,
                written_files=[str(p) for p in result.written_files],
                backups=[str(b.backup_path) for b in result.backups],
            )

            if result.dry_run:
                violations = self._check_dry_run_unchanged(before_disk)
                self.log("Dry run is enabled. No files written.\n")
                if violations:
                    self.log("CRITICAL: dry-run disk-change guard detected changed files!\n")
                    for path in violations:
                        self.log(f"Changed unexpectedly: {path}")
                    self.diagnostics.add("dry_run_guard_violation", files=[str(p) for p in violations])
                else:
                    self.log("Dry-run guard: target files unchanged on disk.\n")
                for op in plan.changed:
                    self.log(f"\n=== {op.rel_name} ===")
                    self.log(unified_preview(op.old_text, op.new_text, op.rel_name))
                self.show_git_diff(append=True)
                return

            for backup in result.backups:
                self.log(f"Backup: {backup.backup_path.relative_to(repo_root)}")
            for path in result.written_files:
                self.log(f"Wrote: {path.relative_to(repo_root)}")
            self.show_git_diff(append=True)
        except Exception as exc:
            self.diagnostics.add_exception("apply_failed", exc)
            self.output_text.delete("1.0", tk.END)
            self.log(f"ERROR: {exc}")
            messagebox.showerror("Apply failed", str(exc))

    def _snapshot_existing_targets(self, plan) -> dict[Path, str]:
        snapshot: dict[Path, str] = {}
        for op in plan.operations:
            if op.target_path.exists() and op.target_path not in snapshot:
                snapshot[op.target_path] = op.target_path.read_text()
        return snapshot

    def _check_dry_run_unchanged(self, before_disk: dict[Path, str]) -> list[Path]:
        changed: list[Path] = []
        for path, before in before_disk.items():
            if not path.exists() or path.read_text() != before:
                changed.append(path)
        return changed

    def show_git_diff(self, append: bool = False) -> None:
        repo_root = Path(self.repo_root_var.get()).resolve()
        if not append:
            self.output_text.delete("1.0", tk.END)

        if not is_git_worktree(repo_root):
            self.diagnostics.add("git_worktree_summary", is_git_worktree=False, repo_root=str(repo_root))
            self.log("\n--- git status --short ---")
            self.log(f"Not a git worktree: {repo_root}")
            self.log("Git status/diff are unavailable. The apply may still have written files.")
            self.log("\n--- Smart Paster last plan diff ---")
            self.log(self.last_plan_diff_text())
            return

        status_code, status_out, status_err = run_command(["git", "status", "--short"], cwd=repo_root)
        diff_code, diff_out, diff_err = run_command(["git", "diff", "--stat"], cwd=repo_root)
        self.diagnostics.add(
            "git_worktree_summary",
            is_git_worktree=True,
            status_code=status_code,
            status_stdout=status_out,
            status_stderr=status_err,
            diff_code=diff_code,
            diff_stdout=diff_out,
            diff_stderr=diff_err,
        )

        self.log("\n--- git status --short ---")
        self.log(status_out if status_out.strip() else "No git status changes.")
        if status_err.strip():
            self.log(status_err)

        self.log("\n--- git diff --stat ---")
        self.log(diff_out if diff_out.strip() else "No git diff stat. Note: untracked files only appear in git status, not git diff.")
        if diff_err.strip():
            self.log(diff_err)

    def last_plan_diff_text(self) -> str:
        if not self.last_plan or not self.last_plan.changed:
            return "No last changed plan is available."
        chunks: list[str] = []
        for index, op in enumerate(self.last_plan.changed, start=1):
            chunks.append(f"\n=== Operation {index}: {op.rel_name} ===\n")
            diff = unified_preview(op.old_text, op.new_text, op.rel_name)
            chunks.append(diff if diff.strip() else "No changes.\n")
        return "".join(chunks)

    def open_target(self) -> None:
        try:
            target = self.resolve_open_target()
            if not target.exists():
                messagebox.showwarning("Open target", f"Target does not exist yet:\n{target}")
                self.diagnostics.add("open_target_missing", target=str(target))
                return
            subprocess.Popen(["xdg-open", str(target)])
            self.diagnostics.add("open_target", target=str(target))
            self.log(f"Opened target: {target}\n")
        except Exception as exc:
            self.diagnostics.add_exception("open_target_failed", exc)
            messagebox.showerror("Open target failed", str(exc))

    def resolve_open_target(self) -> Path:
        if self.last_plan and self.last_plan.operations:
            return self.last_plan.operations[0].target_path
        repo_root = Path(self.repo_root_var.get()).resolve()
        raw = self.target_path_var.get().strip()
        if not raw:
            plan = self.build_plan()
            self.last_plan = plan
            if plan.operations:
                return plan.operations[0].target_path
            raise RuntimeError("No target file available.")
        candidate = Path(raw)
        return candidate if candidate.is_absolute() else (repo_root / candidate).resolve()

    def open_intro_prompt(self) -> None:
        try:
            prompt_path = self.resolve_intro_prompt_path()
            if not prompt_path.exists():
                messagebox.showwarning("Intro prompt", f"Intro prompt file was not found:\n{prompt_path}")
                self.diagnostics.add("open_intro_prompt_missing", path=str(prompt_path))
                return
            subprocess.Popen(["xdg-open", str(prompt_path)])
            self.diagnostics.add("open_intro_prompt", path=str(prompt_path))
            self.log(f"Opened intro prompt: {prompt_path}\n")
        except Exception as exc:
            self.diagnostics.add_exception("open_intro_prompt_failed", exc)
            messagebox.showerror("Open intro prompt failed", str(exc))

    def resolve_intro_prompt_path(self) -> Path:
        candidates: list[Path] = []
        home = os.environ.get("SMART_PASTER_HOME")
        if home:
            candidates.append(Path(home).expanduser().resolve() / "docs" / "default_webchat_prompt.md")
        candidates.append(Path(__file__).resolve().parents[1] / "docs" / "default_webchat_prompt.md")
        candidates.append(Path.cwd().resolve() / "docs" / "default_webchat_prompt.md")

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0] if candidates else Path("docs/default_webchat_prompt.md").resolve()

    def dump_diagnostics(self) -> None:
        try:
            repo_root = Path(self.repo_root_var.get()).resolve()
            if is_git_worktree(repo_root):
                status_code, git_status, status_err = run_command(["git", "status", "--short"], cwd=repo_root)
                diff_code, git_diff_stat, diff_err = run_command(["git", "diff", "--stat"], cwd=repo_root)
            else:
                status_code, diff_code = 128, 128
                git_status = ""
                status_err = f"Not a git worktree: {repo_root}"
                git_diff_stat = self.last_plan_diff_text()
                diff_err = ""
            plan_summary = None
            try:
                plan = self.build_plan()
                self.last_plan = plan
                plan_summary = self.plan_summary(plan)
            except Exception as exc:
                self.diagnostics.add_exception("dump_plan_build_failed", exc)

            settings = {
                "repo_root": self.repo_root_var.get(),
                "target_path": self.target_path_var.get(),
                "symbol": self.symbol_var.get(),
                "target_mode": self.target_mode_var.get(),
                "source_mode": self.source_mode_var.get(),
                "dry_run": self.dry_run_var.get(),
                "backup": self.backup_var.get(),
                "watch_clipboard": self.auto_watch_clipboard_var.get(),
            }
            dump_text = build_dump_text(
                repo_root=repo_root,
                input_text=self.get_input(),
                output_text=self.output_text.get("1.0", tk.END),
                settings=settings,
                log=self.diagnostics,
                git_status=(git_status or status_err),
                git_diff_stat=(git_diff_stat or diff_err),
                plan_summary=plan_summary,
            )
            dump_dir = repo_root / ".smart-paster-dumps"
            dump_dir.mkdir(exist_ok=True)
            dump_path = dump_dir / f"smart_paster_dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            dump_path.write_text(dump_text)
            self.diagnostics.add("dump_written", path=str(dump_path), status_code=status_code, diff_code=diff_code)
            self.log(f"Diagnostic dump written: {dump_path}\n")
            try:
                self.clipboard_clear()
                self.clipboard_append(str(dump_path))
                self.log("Dump path copied to clipboard.\n")
            except Exception:
                pass
        except Exception as exc:
            self.diagnostics.add_exception("dump_failed", exc)
            messagebox.showerror("Dump failed", str(exc))

    def plan_summary(self, plan) -> dict[str, object]:
        return {
            "operations": [
                {
                    "rel_name": op.rel_name,
                    "source_kind": op.operation.source_kind,
                    "mode": op.operation.mode.value if op.operation.mode else None,
                    "symbol": op.operation.symbol,
                    "symbol_kind": op.operation.symbol_kind,
                    "container_name": op.operation.container_name,
                    "occurrence": op.operation.occurrence,
                    "provider_name": op.provider_name,
                    "old_size": len(op.old_text),
                    "new_size": len(op.new_text),
                    "changed": op.old_text != op.new_text,
                }
                for op in plan.operations
            ]
        }
