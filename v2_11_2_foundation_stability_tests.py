from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse, urlencode, quote
import ast

from adaptive_engine import MasterySnapshot, STATUS_BUILDING, STATUS_FLUENT, STATUS_FOCUS
from fact_engine import APP_VERSION
from teacher_insights import BAND_HELP, BAND_KNOWN, BAND_LEARNING, BAND_SLOW, teacher_fact_band
from warmup import question_for_slot

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
STUDENT = (ROOT / "student_igniter_ui.py").read_text(encoding="utf-8")
LEARNING = (ROOT / "teacher_learning_ui.py").read_text(encoding="utf-8")
WARMUP_UI = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")



def _warmup_helpers():
    tree = ast.parse(WARMUP_UI)
    wanted = {"_warmup_name_list", "_warmup_grouping", "_warmup_outlook_url"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    ns = {"urlencode": urlencode, "quote": quote}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "teacher_warmup_ui_helpers", "exec"), ns)
    return ns["_warmup_grouping"], ns["_warmup_outlook_url"]


def run():
    checks = {}
    checks["foundation version"] = APP_VERSION == "2.11.2"

    # Architecture guard: the largest shared file is now meaningfully smaller and
    # the high-change teacher/student Igniter surfaces live behind module boundaries.
    checks["app.py reduced below 3000 lines"] = len(APP.splitlines()) < 3000
    checks["student Igniter extracted"] = "from student_igniter_ui import render_quick_warmup" in APP
    checks["learning data extracted"] = "from teacher_learning_ui import render_teacher_mastery_focus" in APP
    checks["teacher Warm-Up extracted"] = "from teacher_warmup_ui import render_teacher_warmup as _render_teacher_warmup_module" in APP
    checks["teacher Warm-Up keeps refresh contract"] = all(text in APP for text in [
        "refresh_control=_teacher_refresh_control",
        "finish_refresh=_finish_teacher_refresh",
    ])
    checks["app no longer owns teacher analytics implementation"] = "from teacher_insights import" not in APP
    checks["app no longer owns standards-picker implementation"] = "from indiana_math_standards import" not in APP

    # Student flow order remains explicit in the routing shell.
    daily_start = APP.index("def render_daily")
    daily_end = APP.index("def reset_practice_question", daily_start)
    daily = APP[daily_start:daily_end]
    checks["sign in precedes Igniter"] = daily.index("render_student_sign_in(store)") < daily.index("render_quick_warmup(store, day)")
    checks["Igniter precedes Daily heading"] = daily.index("render_quick_warmup(store, day)") < daily.index('st.markdown("## Daily 10")')
    checks["Igniter keeps explicit feedback"] = all(text in STUDENT for text in [
        'st.success("✅ Correct!")',
        'st.error(f"❌ Not quite. The answer is {answer_text}.")',
        'st.markdown("## 🧠 Igniter complete!")',
    ])

    # Shared question accessor must return a copy so a UI cannot mutate the stored plan.
    record = SimpleNamespace(question_one={"prompt": "Q1"}, question_two={"prompt": "Q2"})
    copied = question_for_slot(record, 1)
    copied["prompt"] = "changed"
    checks["question accessor is defensive"] = record.question_one["prompt"] == "Q1" and question_for_slot(record, 2)["prompt"] == "Q2"

    # Behavior guard: unfinished work stays out of reteach groups.
    students = [
        SimpleNamespace(student_id="s1", nickname="Student One"),
        SimpleNamespace(student_id="s2", nickname="Student Two"),
        SimpleNamespace(student_id="s3", nickname="Student Three"),
    ]
    rows = [
        SimpleNamespace(student_id="s1", question_slot=1, correct=False),
        SimpleNamespace(student_id="s1", question_slot=2, correct=False),
        SimpleNamespace(student_id="s2", question_slot=1, correct=False),  # unfinished
        SimpleNamespace(student_id="s3", question_slot=1, correct=True),
        SimpleNamespace(student_id="s3", question_slot=2, correct=False),
    ]
    warmup_grouping, warmup_outlook_url = _warmup_helpers()
    groups = warmup_grouping(students, rows)
    checks["unfinished remains separate"] = groups["unfinished"] == ["Student Two"] and "Student Two" not in groups["q1_support"]
    checks["missed-both priority preserved"] = groups["missed_both"] == ["Student One"]

    # Outlook remains a reviewable draft URL and round-trips line breaks/recipients.
    outlook = warmup_outlook_url("teacher@school.org", "support@school.org", "Igniter Results", "Line one\nLine two")
    parsed = parse_qs(urlparse(outlook).query)
    checks["Outlook draft round trips"] = (
        parsed.get("to") == ["teacher@school.org"]
        and parsed.get("cc") == ["support@school.org"]
        and parsed.get("body") == ["Line one\nLine two"]
        and "+" not in outlook
    )

    # Fact-fluency translation remains teacher-friendly and does not make limited
    # evidence an intervention label.
    learning = MasterySnapshot(a=3, b=4, evidence_count=1, correct_count=1, ema_accuracy=1.0, ema_seconds=8.0, correct_streak=1, status=STATUS_BUILDING)
    slow = MasterySnapshot(a=6, b=7, evidence_count=6, correct_count=6, ema_accuracy=0.95, ema_seconds=8.0, correct_streak=5, status=STATUS_BUILDING)
    help_fact = MasterySnapshot(a=7, b=8, evidence_count=3, correct_count=1, ema_accuracy=0.50, ema_seconds=5.0, correct_streak=0, status=STATUS_FOCUS)
    known = MasterySnapshot(a=5, b=6, evidence_count=5, correct_count=5, ema_accuracy=0.97, ema_seconds=3.5, correct_streak=4, status=STATUS_FLUENT)
    checks["limited evidence stays learning"] = teacher_fact_band(learning) == BAND_LEARNING
    checks["accurate slow remains slow"] = teacher_fact_band(slow) == BAND_SLOW
    checks["accuracy concern remains help"] = teacher_fact_band(help_fact) == BAND_HELP
    checks["fluent fact remains known"] = teacher_fact_band(known) == BAND_KNOWN

    # High-change modules should stay bounded rather than silently growing back into app.py.
    checks["learning module bounded"] = len(LEARNING.splitlines()) < 650
    checks["warmup module bounded"] = len(WARMUP_UI.splitlines()) < 700
    checks["stability contract shipped"] = (ROOT / "STABILITY_CONTRACT.md").exists()

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.11.2 foundation stability regression: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
