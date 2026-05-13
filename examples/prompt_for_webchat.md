Return a normal explanation, then exactly one fenced ```json block containing a Smart Paster patch.

Schema:

{
  "smart_paster_version": 1,
  "atomic": true,
  "sequential_per_file": true,
  "operations": [
    {
      "mode": "exact_replace | new_file | full_file | method",
      "filename": "relative/path/from/repo/root",
      "block_to_replace": "required only for exact_replace; exact old block",
      "symbol": "required only for method",
      "symbol_kind": "optional: auto|function|composable|class|enum|object|interface|method|property",
      "container_name": "optional owner/class/container for method mode",
      "occurrence": 1,
      "replace_block": "new content"
    }
  ]
}

Rules:
- Do not output unified diff.
- Do not use absolute paths.
- Do not use ../.
- For exact_replace, copy block_to_replace exactly from the original file.
- Prefer method mode for full function/method replacement.
- Prefer exact_replace for small localized edits.
- Prefer new_file for creating files.
