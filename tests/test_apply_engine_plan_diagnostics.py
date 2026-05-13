from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from smart_paster.apply_engine import ApplyEngine, exact_replace_plan
from smart_paster.domain import PatchBatch, PatchOperation
from smart_paster.errors import ApplyError, ValidationError
from smart_paster.modes import TargetMode


class ApplyEnginePlanDiagnosticsTests(unittest.TestCase):
    def test_plan_reports_all_files_with_exact_replace_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "a.txt").write_text("alpha\nold-a\nomega\n")
            (repo / "b.txt").write_text("alpha\nold-b\nomega\n")
            (repo / "c.txt").write_text("alpha\nold-c\nomega\n")

            batch = PatchBatch(
                operations=[
                    PatchOperation(
                        filename="a.txt",
                        mode=TargetMode.EXACT_REPLACE,
                        block_to_replace="missing-a",
                        replace_block="new-a",
                    ),
                    PatchOperation(
                        filename="b.txt",
                        mode=TargetMode.EXACT_REPLACE,
                        block_to_replace="missing-b",
                        replace_block="new-b",
                    ),
                    PatchOperation(
                        filename="c.txt",
                        mode=TargetMode.EXACT_REPLACE,
                        block_to_replace="old-c",
                        replace_block="new-c",
                    ),
                ]
            )

            with self.assertRaises(ValidationError) as ctx:
                ApplyEngine().plan(repo_root=repo, batch=batch)

            message = str(ctx.exception)
            self.assertIn("Plan validation failed", message)
            self.assertIn("operation 1, file a.txt", message)
            self.assertIn("operation 2, file b.txt", message)
            self.assertIn("exact_replace mismatch", message)
            self.assertNotIn("operation 3, file c.txt", message)

    def test_plan_reports_missing_target_file_with_operation_and_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            batch = PatchBatch(
                operations=[
                    PatchOperation(
                        filename="missing.txt",
                        mode=TargetMode.EXACT_REPLACE,
                        block_to_replace="old",
                        replace_block="new",
                    )
                ]
            )

            with self.assertRaises(ValidationError) as ctx:
                ApplyEngine().plan(repo_root=repo, batch=batch)

            message = str(ctx.exception)
            self.assertIn("operation 1, file missing.txt", message)
            self.assertIn("Target file does not exist", message)

    def test_plan_reports_ambiguous_exact_replace_with_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "dup.txt").write_text("same\nsame\n")
            batch = PatchBatch(
                operations=[
                    PatchOperation(
                        filename="dup.txt",
                        mode=TargetMode.EXACT_REPLACE,
                        block_to_replace="same",
                        replace_block="changed",
                    )
                ]
            )

            with self.assertRaises(ValidationError) as ctx:
                ApplyEngine().plan(repo_root=repo, batch=batch)

            message = str(ctx.exception)
            self.assertIn("operation 1, file dup.txt", message)
            self.assertIn("exact_replace ambiguous", message)
            self.assertIn("occurs 2 times", message)

    def test_exact_replace_plan_detects_already_applied_patch(self) -> None:
        text = "alpha\nnew\nomega\n"
        new_text, status = exact_replace_plan(text, "old", "new")

        self.assertEqual(new_text, text)
        self.assertEqual(status, "already_applied_exact_replace")

    def test_exact_replace_plan_distinguishes_missing_from_already_applied(self) -> None:
        with self.assertRaises(ApplyError) as ctx:
            exact_replace_plan("alpha\nomega\n", "old", "new")

        self.assertIn("exact_replace mismatch", str(ctx.exception))
        self.assertIn("replacement fragment occurrences=0", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
