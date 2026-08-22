from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from adaptive_engine import MasterySnapshot, STATUS_BUILDING, STATUS_FOCUS, update_snapshot
from fact_engine import Fact
from fact_store import InMemoryFactStore
from teacher_insights import BAND_HELP, BAND_LEARNING, BAND_SLOW, teacher_fact_band

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
COMPONENT = (ROOT / "daily_sprint_component" / "index.html").read_text(encoding="utf-8")
SUPABASE = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
SCHEMA = (ROOT / "SUPABASE_SCHEMA.sql").read_text(encoding="utf-8")
MIGRATION = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_11_2_DATA_TRUST.sql").read_text(encoding="utf-8")


def _snapshot(*, evidence, correct, ema_accuracy, ema_seconds, streak, status=STATUS_BUILDING):
    return MasterySnapshot(
        a=7,
        b=8,
        evidence_count=evidence,
        correct_count=correct,
        ema_accuracy=ema_accuracy,
        ema_seconds=ema_seconds,
        correct_streak=streak,
        status=status,
    )


def _daily_fixture():
    store = InMemoryFactStore()
    classroom = store.create_class("Block A", "BLOCKA")
    student = store.create_student(classroom.class_id, "Sample Student", "1234")
    facts = [
        Fact(2, 2, "core"), Fact(2, 3, "core"), Fact(2, 4, "core"), Fact(2, 5, "core"),
        Fact(3, 3, "core"), Fact(3, 4, "core"), Fact(3, 5, "core"), Fact(4, 4, "core"),
        Fact(4, 5, "core"), Fact(5, 5, "core"),
    ]
    challenge = store.get_or_create_challenge(date(2026, 8, 24), "TDFC-DAILY-v1", facts)
    attempt = store.get_or_create_attempt(student.student_id, challenge.challenge_id)
    return store, student, challenge, attempt, facts


def run():
    checks = {}

    # 1. One miss cannot become a teacher red flag. Repeated independent misses can.
    one_miss = _snapshot(
        evidence=2, correct=1, ema_accuracy=0.35, ema_seconds=3.0, streak=1, status=STATUS_FOCUS
    )
    repeated_misses = _snapshot(
        evidence=3, correct=1, ema_accuracy=0.50, ema_seconds=3.0, streak=1, status=STATUS_FOCUS
    )
    recovered = _snapshot(
        evidence=6, correct=4, ema_accuracy=0.72, ema_seconds=3.5, streak=3, status=STATUS_BUILDING
    )
    checks["single miss is not Needs Help"] = teacher_fact_band(one_miss) == BAND_LEARNING
    checks["two independent misses can be Needs Help"] = teacher_fact_band(repeated_misses) == BAND_HELP
    checks["three-correct recovery streak clears red"] = teacher_fact_band(recovered) != BAND_HELP

    # 4. One classroom interruption should not create a slow label. Use the
    # real adaptive EMA calculation rather than a hand-built snapshot.
    one_pause = None
    for seconds in (3.0, 3.0, 30.0, 3.0, 3.0, 3.0):
        one_pause = update_snapshot(
            one_pause, a=7, b=8, correct=True, response_seconds=seconds
        )
    consistently_slow = None
    for seconds in (8.0, 8.0, 8.0, 8.0, 8.0, 8.0):
        consistently_slow = update_snapshot(
            consistently_slow, a=7, b=8, correct=True, response_seconds=seconds
        )
    checks["one pause does not create yellow"] = teacher_fact_band(one_pause) != BAND_SLOW
    checks["repeated slow accurate evidence can create yellow"] = teacher_fact_band(consistently_slow) == BAND_SLOW

    # 2. The browser keeps final/editable answers and a separate immutable first-answer array.
    checks["component stores first answer separately"] = all(token in COMPONENT for token in [
        "firstAnswers:Array(10).fill(null)",
        "if(firstSubmission){ current.firstAnswers[current.index]=value; }",
        "first_answers:current.firstAnswers",
    ])
    checks["app passes first answers to store"] = all(token in APP for token in [
        'raw_first_answers = component_result.get("first_answers")',
        "first_answers=list(zip(facts, first_values))",
    ])

    store, student, challenge, attempt, facts = _daily_fixture()
    final_answers = [(fact, fact.product) for fact in facts]
    first_answers = list(final_answers)
    first_answers[0] = (facts[0], facts[0].product + 1)  # first try wrong, later edited to correct
    completed = store.complete_full_attempt(
        attempt.attempt_id,
        final_answers,
        42.0,
        response_seconds=[None] + [3.0] * 9,
        first_answers=first_answers,
    )
    saved = store.get_answers(attempt.attempt_id)
    q1 = saved[0]
    q1_mastery = {row.key: row for row in store.get_mastery(student.student_id)}[facts[0].key]
    checks["official Daily score still uses final answers"] = completed.correct_count == 10 and q1.correct
    checks["first answer persists separately"] = q1.first_student_answer == facts[0].product + 1 and q1.first_correct is False
    checks["mastery uses first answer instead of edited final"] = q1_mastery.evidence_count == 1 and q1_mastery.correct_count == 0

    # 3. A completed attempt with missing post-save evidence repairs itself and does not double-count.
    store.mastery = {}
    store.learning_progress = {}
    store.attempts[attempt.attempt_id] = replace(completed, learning_evidence_applied_at=None)
    repaired = store.ensure_daily_learning_evidence(attempt.attempt_id)
    repaired_mastery = {row.key: row for row in store.get_mastery(student.student_id)}
    first_count = repaired_mastery[facts[0].key].evidence_count
    again = store.ensure_daily_learning_evidence(attempt.attempt_id)
    second_count = {row.key: row for row in store.get_mastery(student.student_id)}[facts[0].key].evidence_count
    checks["repair sets completion-evidence marker"] = repaired.learning_evidence_applied_at is not None
    checks["repair restores learning progress"] = store.get_learning_progress(student.student_id, challenge.challenge_id) is not None
    checks["repair uses first-answer evidence"] = repaired_mastery[facts[0].key].correct_count == 0
    checks["repair is idempotent"] = first_count == 1 and second_count == 1 and again.learning_evidence_applied_at is not None

    # Production persistence contracts for first-answer evidence + repair marker.
    checks["health check verifies data-trust migration"] = all(token in SUPABASE for token in [
        'select("attempt_id,learning_evidence_applied_at")',
        'select("answer_id,first_student_answer,first_correct")',
    ])
    checks["Supabase stores first-answer fields"] = all(token in SUPABASE for token in [
        '"first_student_answer": int(first_value)',
        '"first_correct": int(first_value) == fact.product',
        "def ensure_daily_learning_evidence",
        '"learning_evidence_applied_at": utc_now().isoformat()',
    ])
    checks["rebuild mastery prefers first correctness"] = 'row.get("first_correct")' in SUPABASE
    checks["schema includes first-answer columns"] = "first_student_answer integer" in SCHEMA and "first_correct boolean" in SCHEMA
    checks["schema includes repair marker"] = "learning_evidence_applied_at timestamptz" in SCHEMA
    checks["migration is backward compatible"] = all(token in MIGRATION for token in [
        "add column if not exists first_student_answer integer",
        "add column if not exists first_correct boolean",
        "add column if not exists learning_evidence_applied_at timestamptz",
        "set learning_evidence_applied_at = completed_at",
    ])

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed data-trust checks: " + ", ".join(failed))
    print(f"v2.11.2 data trust regression: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
