from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from adaptive_engine import MasterySnapshot, STATUS_BUILDING, STATUS_FLUENT, STATUS_FOCUS, STATUS_UNKNOWN
from fact_engine import APP_VERSION
from teacher_insights import (
    BAND_HELP,
    BAND_KNOWN,
    BAND_LEARNING,
    BAND_SLOW,
    pull_reason,
    rank_students_to_pull,
    standard_student_history,
    summarize_student_fluency,
    teacher_fact_band,
)

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
LEARNING_UI = (ROOT / "teacher_learning_ui.py").read_text(encoding="utf-8")
WARMUP_UI = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
STUDENT_IGNITER = (ROOT / "student_igniter_ui.py").read_text(encoding="utf-8")
SUPABASE = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")


def section(name: str, next_name: str | None = None, source: str = APP) -> str:
    start = source.index(f"def {name}")
    end = source.index(f"\ndef {next_name}", start) if next_name else len(source)
    return source[start:end]


def snap(a, b, evidence, correct, acc, seconds, streak, status):
    return MasterySnapshot(
        a=a, b=b, evidence_count=evidence, correct_count=correct,
        ema_accuracy=acc, ema_seconds=seconds, correct_streak=streak, status=status,
    )


def run():
    checks = {}
    checks["version 2.11.2"] = APP_VERSION == "2.19.0"

    known = snap(2, 2, 5, 5, 0.96, 3.2, 5, STATUS_FLUENT)
    slow = snap(3, 4, 6, 6, 0.95, 8.0, 5, STATUS_BUILDING)
    help_fact = snap(7, 8, 4, 1, 0.42, 4.0, 0, STATUS_FOCUS)
    too_little = snap(6, 6, 1, 1, 1.0, 2.0, 1, STATUS_UNKNOWN)
    developing = snap(4, 6, 3, 2, 0.76, 4.1, 1, STATUS_BUILDING)

    checks["known band"] = teacher_fact_band(known) == BAND_KNOWN
    checks["accurate slow band"] = teacher_fact_band(slow) == BAND_SLOW
    checks["repeated misses band"] = teacher_fact_band(help_fact) == BAND_HELP
    checks["too little evidence neutral"] = teacher_fact_band(too_little) == BAND_LEARNING
    checks["ordinary building is not intervention"] = teacher_fact_band(developing) == BAND_LEARNING

    summary = summarize_student_fluency("s1", "Student A", [known, slow, help_fact, too_little, developing])
    checks["student summary separates known slow help"] = (summary.known, summary.slow, summary.needs_help) == (1, 1, 1)
    checks["typical time uses stable accurate facts"] = 3.2 < summary.typical_correct_seconds < 8.0
    checks["start facts puts accuracy need first"] = summary.start_facts[0] == "7×8"
    checks["pull reason plain language"] = "repeated miss" in pull_reason(summary)

    no_pull = summarize_student_fluency("s2", "Student B", [known, too_little, developing])
    ranked = rank_students_to_pull([no_pull, summary])
    checks["building-only student not pulled"] = [row.student_id for row in ranked] == ["s1"]

    now = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    students = [SimpleNamespace(student_id="s1", nickname="Student A"), SimpleNamespace(student_id="s2", nickname="Student B")]
    answers = [
        SimpleNamespace(student_id="s1", standard_code="5.NS.3", correct=True, warmup_date="2026-08-17", answered_at=now, question_slot=1),
        SimpleNamespace(student_id="s1", standard_code="5.NS.3", correct=False, warmup_date="2026-08-18", answered_at=now, question_slot=2),
        SimpleNamespace(student_id="s2", standard_code="5.NS.3", correct=True, warmup_date="2026-08-18", answered_at=now, question_slot=1),
    ]
    history = standard_student_history(students, answers, "5.NS.3")
    by_id = {row["student_id"]: row for row in history}
    checks["standard history preserves multiple dates"] = by_id["s1"]["checks"] == 2 and by_id["s1"]["history"] == "✅ ❌"
    checks["standard history calculates accuracy"] = by_id["s1"]["correct"] == 1 and by_id["s1"]["accuracy"] == 0.5
    checks["standard history includes all current students"] = set(by_id) == {"s1", "s2"}

    learning = section("render_teacher_mastery_focus", source=LEARNING_UI)
    checks["learning page has two simple views"] = all(text in learning for text in ["⚡ Fact Fluency", "📚 Standards Tracker"])
    checks["old four-view wall removed"] = all(text not in learning for text in ["What Should I Teach?", "Who Needs Help?"])
    checks["teacher nav renamed"] = '"📈 Learning Data"' in APP

    fluency = section("_render_teacher_fact_fluency", "_render_teacher_standards_tracker", LEARNING_UI)
    checks["fluency leads with students to pull"] = "#### 🎯 Students to Pull" in fluency
    checks["fluency uses response time"] = "Typical correct recall" in fluency and "Accurate, Still Slow" in fluency
    checks["fluency retains detailed drilldown"] = "🔎 Fact & student detail" in fluency
    checks["advanced controls retained but collapsed"] = "⚙️ Detailed Fact Map & Focus Settings" in fluency

    standards = section("_render_teacher_standards_tracker", "render_teacher_mastery_focus", LEARNING_UI)
    checks["standards dropdown"] = 'st.selectbox(\n        "Indiana standard"' in standards
    checks["standards student history"] = "#### Student History" in standards and "One Student's History" in standards
    checks["standards avoids mastery overclaim"] = "not an automatic score" in standards
    checks["standards uses school-year evidence"] = "_school_year_start(today)" in standards and "store.list_warmup_answers(start_date, today" in standards

    warmup_teacher = section("render_teacher_warmup", source=WARMUP_UI)
    checks["warmup has true refresh button"] = 'refresh_control(key="teacher_warmup_refresh")' in warmup_teacher
    checks["warmup refresh finishes after result read"] = warmup_teacher.index("_warmup_class_snapshot") < warmup_teacher.index("finish_refresh()")

    student_warmup = section("render_quick_warmup", source=STUDENT_IGNITER)
    checks["question feedback says correct"] = 'st.success("✅ Correct!")' in student_warmup
    checks["question feedback says not quite"] = 'st.error(f"❌ Not quite. The answer is {answer_text}.")' in student_warmup
    checks["completion is neutral info"] = 'st.markdown("## 🧠 Igniter complete!")' in student_warmup and 'st.info("Both questions are finished. Ready for your Daily 10!")' in student_warmup
    checks["q2 feedback shown before completion"] = student_warmup.index("if completed:") < student_warmup.index('st.markdown("## 🧠 Igniter complete!")')

    checks["supabase warmup history paginates"] = 'page_size = 1000' in SUPABASE and '.range(offset, offset + page_size - 1)' in SUPABASE

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.11 afterschool teacher data regression: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
