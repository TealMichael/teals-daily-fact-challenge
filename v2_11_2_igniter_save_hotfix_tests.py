"""Regression protection for the teacher Igniter save path.

The v2.11.2 foundation extraction accidentally called a nonexistent helper
(`preparequestion_for_slot`) when Save Warm-Up was pressed.  The form rendered
normally, so source-only/page-load tests did not catch it.  Keep this guard
close to the teacher UI module so future extractions cannot silently break
saving again.
"""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")


def test_teacher_warmup_module_parses():
    ast.parse(SOURCE)


def test_save_uses_imported_prepare_helper_for_both_questions():
    assert "prepare_question as prepare_warmup_question" in SOURCE
    assert "question_for_slot" in SOURCE
    assert SOURCE.count("prepare_warmup_question(slot=") >= 2


def test_removed_broken_foundation_helper_name():
    assert "preparequestion_for_slot" not in SOURCE


if __name__ == "__main__":
    tests = [
        test_teacher_warmup_module_parses,
        test_save_uses_imported_prepare_helper_for_both_questions,
        test_removed_broken_foundation_helper_name,
    ]
    for test in tests:
        test()
    print(f"Igniter save hotfix regression: {len(tests)}/{len(tests)} passed")
