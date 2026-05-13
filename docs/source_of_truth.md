# Smart Paster source of truth

The canonical Smart Paster implementation is the repository package under `smart_paster/`.

The old single-file canvas MVP is archival only. Do not use it as an implementation source, patch source, or architectural authority for future work.

When asking an AI assistant for changes, provide the current repository files from disk and request Smart Paster JSON patches against repository-relative paths.

Preferred update format:

```json
{
  "smart_paster_version": 1,
  "operations": [
    {
      "mode": "exact_replace",
      "filename": "smart_paster/example.py",
      "block_to_replace": "old text",
      "replace_block": "new text"
    }
  ]
}
```

For large or sensitive files, prefer `full_file` only when the whole current file was provided to the assistant. For GUI/core self-updates, avoid `method` patches until the provider health report is clean.
