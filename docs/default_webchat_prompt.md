# Smart Paster default web-chat prompt

Use this prompt when you want a web-chat model to edit this repository through Smart Paster.

Copy this whole block into the chat, then add the task, exact file paths, and relevant file contents or excerpts below it.

```text
You are helping me edit a local code repository. I will apply your answer with a local tool named Smart Paster.

Important repository rules:
- I will provide exact repository-relative file paths for every file you may change.
- Use only the files and paths I explicitly provide.
- Do not invent file paths.
- Do not use absolute paths.
- Do not use ../ path traversal.
- Prefer minimal, localized edits.
- Preserve existing style unless I explicitly ask for refactoring.
- If you need more context, say exactly which repository-relative files or symbols you need.

Your answer format:
- You may write a short explanation in normal text.
- Put all machine-applicable changes in exactly one fenced JSON block marked as json.
- Do not use unified diff for Smart Paster changes.
- Do not put comments inside the JSON.
- JSON must be valid.

Smart Paster JSON schema:
{
  "smart_paster_version": 1,
  "operations": [
    {
      "mode": "exact_replace | method | full_file | new_file",
      "filename": "repository/relative/path.ext",
      "block_to_replace": "required only for exact_replace; copy the old block exactly",
      "replace_block": "new block, full method, full file, or new file content",
      "symbol": "required for method mode",
      "symbol_kind": "optional; function | method | class | property | object | interface | enum | auto",
      "container_name": "optional but recommended when replacing class methods",
      "occurrence": 1,
      "allow_overwrite": false
    }
  ]
}

Mode selection rules:
- Use exact_replace for a small localized edit when you can copy the old block exactly.
- Use method for replacing a whole function/method/class-like symbol. Provide symbol. For class methods, also provide container_name.
- Use full_file only when the entire existing file should be replaced.
- Use new_file only for creating a file that does not already exist. If overwriting is intentional, set allow_overwrite=true and explain why.

Batch rules:
- Multiple operations are allowed in one JSON block.
- If multiple operations touch the same file, order them in the exact sequence they should be applied.
- Keep operations small and reviewable.

After the JSON block, optionally include tests to run in a bash block.
```

## Minimal example

```json
{
  "smart_paster_version": 1,
  "operations": [
    {
      "mode": "exact_replace",
      "filename": "smart_paster/example.py",
      "block_to_replace": "def old_name():\n    return 'old'\n",
      "replace_block": "def old_name():\n    return 'new'\n"
    }
  ]
}
```

## Method replacement example

```json
{
  "smart_paster_version": 1,
  "operations": [
    {
      "mode": "method",
      "filename": "smart_paster/gui_tk.py",
      "symbol": "preview",
      "symbol_kind": "method",
      "container_name": "SmartPasterApp",
      "occurrence": 1,
      "replace_block": "def preview(self) -> None:\n    ...\n"
    }
  ]
}
```

## Task template

```text
Task:
<describe the change>

Exact files you may edit:
- path/to/file1.py
- path/to/file2.py

Files/context:
```text
<paste relevant excerpts or whole files here>
```

Return a short explanation plus one Smart Paster JSON block.
```
