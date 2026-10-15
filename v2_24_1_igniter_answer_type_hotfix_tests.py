from pathlib import Path

from curriculum_question_types import COMPARE_QUESTION_TYPE, ORDER_QUESTION_TYPE
from fact_engine import APP_VERSION
from warmup import QUESTION_TYPES

ROOT = Path(__file__).resolve().parent
checks = []

def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)

check("release version", APP_VERSION == "2.24.4")
check("warmup compare type", COMPARE_QUESTION_TYPE in QUESTION_TYPES)
check("warmup order type", ORDER_QUESTION_TYPE in QUESTION_TYPES)

editor = (ROOT / "teacher_question_editor.py").read_text(encoding="utf-8")
check("editor defensive interactive injection", "for interactive_type in (COMPARE_QUESTION_TYPE, ORDER_QUESTION_TYPE)" in editor)
check("editor injects after number label", 'types.index("Number + Label") + 1' in editor)

warmup_ui = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
check("Igniter uses shared answer editor", "render_answer_editor(" in warmup_ui and "question_types=QUESTION_TYPES" in warmup_ui)

for filename in ("student_igniter_ui.py", "student_weekly_quiz_ui.py", "student_recovery_ui.py"):
    src=(ROOT/filename).read_text(encoding="utf-8")
    check(f"{filename} compare", "COMPARISON_SYMBOLS" in src)
    check(f"{filename} order", "render_order_tiles(" in src)

print(f"v2_24_1_igniter_answer_type_hotfix_tests: PASS ({len(checks)}/{len(checks)})")
