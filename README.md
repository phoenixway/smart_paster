# Smart Paster

Clipboard-driven guarded patch applier for web-chat coding workflows.

## Design

Smart Paster separates responsibilities into small modules:

- `clipboard_parser.py`: extracts Smart Paster JSON from normal web-chat answers.
- `domain.py`: dataclasses for operations, batches, plans, results, symbol spans.
- `apply_engine.py`: validates and applies operations. GUI does not mutate files directly.
- `path_guard.py`: prevents absolute paths and `..` escapes.
- `providers/`: symbol-location backends.
  - `angelica_kotlin_provider.py`: optional adapter for Angelica `KotlinSymbolExtractor`.
  - `tree_sitter_python_provider.py`: optional Tree-sitter provider for Python functions/classes/methods.
  - `regex_provider.py`: dependency-free fallback for Python/Kotlin/Java/Go.
- `gui_tk.py`: thin Tkinter GUI.

This keeps the architecture clean: LLM proposes patches, Smart Paster validates and executes.

## Run

```bash
python3 run_smart_paster.py
```

or:

```bash
python3 -m smart_paster.main
```

## Install launcher

From the project root:

```bash
./install_launcher.sh
```

Then run from anywhere:

```bash
smart-paster
```

Manual variant:

```bash
cp launchers/smart-paster ~/.local/bin/smart-paster
chmod +x ~/.local/bin/smart-paster
```

The launcher defaults to:

```bash
~/studio/public/it/smart_paster
```

Override when needed:

```bash
export SMART_PASTER_HOME=/path/to/smart_paster
smart-paster
```

## Web-chat patch format

The answer can contain normal text plus a fenced JSON patch:

```json
{
  "smart_paster_version": 1,
  "atomic": true,
  "sequential_per_file": true,
  "operations": [
    {
      "mode": "exact_replace",
      "filename": "relative/path.py",
      "block_to_replace": "exact old block",
      "replace_block": "new block"
    }
  ]
}
```

Modes:

- `exact_replace`: requires `block_to_replace` and `replace_block`.
- `new_file`: creates a new file. Refuses existing files unless `allow_overwrite=true`.
- `full_file`: replaces full file content.
- `method`: replaces a function/method/symbol.

Method example:

```json
{
  "smart_paster_version": 1,
  "operations": [
    {
      "mode": "method",
      "filename": "app/src/main/java/com/example/Foo.kt",
      "symbol": "handleAction",
      "symbol_kind": "method",
      "container_name": "Foo",
      "occurrence": 1,
      "replace_block": "fun handleAction() {\n    println(\"ok\")\n}"
    }
  ]
}
```

## Tree-sitter providers

### Python provider

For `.py` method replacement, Smart Paster now tries a Tree-sitter Python provider before the regex fallback. Loading order:

1. Angelica `modules.code_parser.CodeParser` via `SMART_PASTER_ANGELICA_ROOT`, repo root, or current directory.
2. `tree_sitter_python` package, if installed.
3. A compiled shared library from `SMART_PASTER_PYTHON_TS_LIB` or common repo-local paths like `libs/python.so`.

Useful env vars:

```bash
export SMART_PASTER_ANGELICA_ROOT=/path/to/angelica-ai
export SMART_PASTER_PYTHON_TS_LIB=/path/to/python.so
```

If Tree-sitter loading fails, Smart Paster falls back to conservative regex matching.

### Angelica Kotlin provider

If Smart Paster runs inside the Angelica repo, or if this env var points to it:

```bash
export SMART_PASTER_ANGELICA_ROOT=/path/to/angelica-ai
```

then `.kt` method replacement first tries Angelica's Tree-sitter `KotlinSymbolExtractor`.
If unavailable, Smart Paster falls back to a conservative regex provider.

## Safety

- Absolute paths are refused.
- `../` path escapes are refused.
- Exact replace must match exactly once.
- Batch planning resolves all operations before writing.
- Multiple operations against the same file are applied sequentially in memory.
- Backups are created under `.smart-paster-backups` by default.
- Dry run is enabled by default in GUI.

## v3 notes

Added GUI/runtime diagnostics:

- **Open target** button opens the first target file from the last preview/apply plan, or the explicit Target file field.
- **Watch clipboard** checkbox polls clipboard and auto-loads text into Incoming when it contains a valid Smart Paster JSON patch or fenced `json` patch.
- **Dump** button writes a Markdown diagnostic file under `.smart-paster-dumps/` in the repo root and copies its path to the clipboard.
- Dry-run now performs a post-check guard: target files are snapshotted before `apply_plan(..., dry_run=True)` and compared afterwards. If any file changed, the GUI logs a critical guard violation.

Recommended bug workflow:

1. Copy the web-chat answer.
2. Confirm it auto-appears in Incoming, or click Paste.
3. Click Preview.
4. Click Apply with Dry run enabled.
5. If anything looks wrong, click Dump and paste/send the generated dump file.

Launcher install:

```bash
./install_launcher.sh
smart-paster
```

## v4 UI sync behavior

When Paste or Watch clipboard loads a legal Smart Paster JSON patch:

- Incoming is replaced with the clipboard text.
- Target file is synchronized from the first operation's `filename`.
- Target mode is synchronized from the first operation's `mode` when present.
- Symbol/method is synchronized from the first operation's `symbol`, or cleared.
- Preview runs automatically.

Patch paths are authoritative. The Target file field is a visible synchronized target/open-target aid, not a stale override over JSON.
For batch patches, the first operation is shown in Target file and all operations are shown in Preview/Dump.

## v5 notes

- The top controls now use wrapped grid layout so source modes and action buttons remain reachable on narrower windows.
- Added `docs/default_webchat_prompt.md`, a reusable prompt that tells a web-chat model how to return Smart Paster JSON patches and reminds you to provide exact repository-relative paths for editable files.

## v6 notes

- Added **Intro prompt** button in the action area.
- The button opens `docs/default_webchat_prompt.md` with `xdg-open`.
- Resolution order:
  1. `$SMART_PASTER_HOME/docs/default_webchat_prompt.md`
  2. project-root `docs/default_webchat_prompt.md` next to the package
  3. current working directory `docs/default_webchat_prompt.md`
- Diagnostic events are recorded for successful open, missing prompt file, and open failures.


## v7 test notes

- `Git diff` now prints both `git status --short` and `git diff --stat`, because untracked files do not appear in `git diff --stat`.
- Regex fallback symbol spans now handle files that end directly at EOF/trailing newline without producing an out-of-range final line.
- See `tests/smoke_core.py` for non-GUI smoke tests.

## v8 note

Python Tree-sitter provider now distinguishes top-level functions from nested/local functions.
A patch with `"symbol_kind": "function"` targets only top-level functions, while nested functions are reported as `local_function`.
This fixes cases like `normalize_name` appearing both at module level and inside another method.
