from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_question_bank_derives_essential_metadata_from_bank_json():
    import indiana_question_bank as bank
    rows = bank.all_questions()
    expected = {str(row["standard_code"]) for row in rows if row.get("essential")}
    assert bank.essential_codes() == frozenset(expected)
    assert bank.bank_summary()["essential_standards"] == len(expected) == 42


def test_teacher_question_bank_does_not_import_new_essential_exports_from_standards():
    source = (ROOT / "teacher_question_bank_ui.py").read_text(encoding="utf-8")
    assert "from indiana_math_standards import BY_CODE, is_essential_standard" not in source
    assert "is_essential_standard," in source


def test_question_bank_module_only_requires_legacy_by_code_export():
    source = (ROOT / "indiana_question_bank.py").read_text(encoding="utf-8")
    assert "from indiana_math_standards import BY_CODE" in source
    assert "from indiana_math_standards import BY_CODE, ESSENTIAL_CODES" not in source
    assert "from indiana_math_standards import BY_CODE, ESSENTIAL_CODES, is_essential_standard" not in source
