Короткий діагноз: замінюємо локальний блок і створюємо новий файл.

```json
{
  "smart_paster_version": 1,
  "atomic": true,
  "sequential_per_file": true,
  "operations": [
    {
      "mode": "exact_replace",
      "filename": "src/example.py",
      "block_to_replace": "def old():\n    return 1\n",
      "replace_block": "def old():\n    return 2\n"
    },
    {
      "mode": "new_file",
      "filename": "src/new_file.py",
      "replace_block": "def hello():\n    return 'world'\n"
    },
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

Tests:

```bash
pytest -q tests
```
