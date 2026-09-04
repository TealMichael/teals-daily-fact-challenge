from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from alternate_followup import skill_identity_for_question, missed_question_items
from daily_modes import questions_for_mode
from fact_engine import APP_VERSION, CHALLENGE_VERSION, daily_facts_for_date
from fact_store import InMemoryFactStore
from teacher_command_center import routine_label_for_mode, summarize_routine_for_mode

ROOT = Path(__file__).resolve().parent
checks: list[str] = []


def check(label: str, value) -> None:
    if not value:
        raise AssertionError(label)
    checks.append(label)


def setup(mode: str, day: date = date(2026, 9, 2)):
    store = InMemoryFactStore()
    klass = store.create_class("Block 1")
    student = store.create_student(klass.class_id, "Falcon", "2468")
    challenge = store.get_or_create_challenge(day, CHALLENGE_VERSION, daily_facts_for_date(day))
    questions = questions_for_mode(day, mode)
    attempt = store.get_or_create_attempt(
        student.student_id, challenge.challenge_id, daily_mode=mode, custom_questions=questions
    )
    return store, klass, student, challenge, questions, attempt


check("current version", APP_VERSION == "2.19.5")
check("multiplication challenge stays v1", CHALLENGE_VERSION == "TDFC-DAILY-v1")

# Skill identities are stable and useful for later teaching/focus layers.
identity_cases = [
    ({"prompt": "7 × 8", "category": "Multiplication"}, "Multiplication", "mul:7x8"),
    ({"prompt": "8 + 7", "category": "Addition Facts"}, "Addition Facts", "add:7+8"),
    ({"prompt": "15 − 7", "category": "Subtraction Facts"}, "Subtraction Facts", "sub:15-7"),
    ({"prompt": "42 ÷ 6", "category": "Division Facts"}, "Division Facts", "div:42/6"),
    ({"prompt": "-4 + 7", "category": "Integers"}, "Integers", "int:add:n_p"),
    ({"prompt": "5 − (-3)", "category": "Integers"}, "Integers", "int:sub:p_n"),
]
for question, domain, key in identity_cases:
    skill = skill_identity_for_question(question)
    check(f"skill domain {question['prompt']}", skill.domain == domain)
    check(f"skill key {question['prompt']}", skill.skill_key == key)

# Historical v2.13-style questions can still be identified from kind/default mode.
legacy = skill_identity_for_question({"prompt": "7+8", "kind": "addition"}, "Addition Facts")
check("legacy alternate question identity", legacy.skill_key == "add:7+8")

alt_modes = ["Addition Facts", "Subtraction Facts", "Division Facts", "Integers", "Mixed"]
for mode in alt_modes:
    store, klass, student, challenge, questions, attempt = setup(mode)
    correct = [int(q["correct_answer"]) for q in questions]
    perfect = store.complete_custom_attempt(attempt.attempt_id, correct, 20.0)
    progress = store.get_alternate_learning_progress(student.student_id, challenge.challenge_id)
    events = store.alternate_learning_activity_rows(student.student_id, challenge.challenge_id, "daily")
    check(f"{mode} perfect score saved", perfect.correct_count == 10)
    check(f"{mode} perfect auto-completes Fix only", progress is not None and progress.fix_completed_at is not None and progress.completed_at is None)
    check(f"{mode} stores ten isolated Daily events", len(events) == 10)
    check(f"{mode} does not write multiplication mastery", store.get_mastery(student.student_id) == [])

# A miss requires Fix Your Misses and completion happens only after correction.
for mode in alt_modes:
    store, klass, student, challenge, questions, attempt = setup(mode)
    values = [int(q["correct_answer"]) for q in questions]
    values[0] = values[0] + 1
    store.complete_custom_attempt(attempt.attempt_id, values, 18.0)
    progress = store.get_alternate_learning_progress(student.student_id, challenge.challenge_id)
    check(f"{mode} miss leaves follow-up pending", progress is not None and progress.completed_at is None)
    misses = missed_question_items(questions, values, default_domain=None if mode == "Mixed" else mode)
    check(f"{mode} exactly one miss identified", len(misses) == 1)
    try:
        store.record_alternate_fix_batch(
            attempt.attempt_id,
            [{"question_number": misses[0]["question_number"], "student_answer": misses[0]["correct_answer"] + 1}],
        )
        bad_rejected = False
    except ValueError:
        bad_rejected = True
    check(f"{mode} wrong Fix answer rejected server-side", bad_rejected)
    store.record_alternate_fix_batch(
        attempt.attempt_id,
        [{"question_number": misses[0]["question_number"], "student_answer": misses[0]["correct_answer"]}],
    )
    progress = store.get_alternate_learning_progress(student.student_id, challenge.challenge_id)
    fix_rows = store.alternate_learning_activity_rows(student.student_id, challenge.challenge_id, "fix_miss")
    check(f"{mode} corrected Fix completes Step 2 only", progress is not None and progress.fix_completed_at is not None and progress.completed_at is None)
    check(f"{mode} stores correction event", len(fix_rows) == 1 and fix_rows[0].correct and fix_rows[0].is_retry)
    check(f"{mode} correction remains out of mastery", store.get_mastery(student.student_id) == [])

# Mixed routes its ten items to the true five domains, two each, with zero mastery contamination.
store, klass, student, challenge, questions, attempt = setup("Mixed")
wrong = [int(q["correct_answer"]) + 1 for q in questions]
store.complete_custom_attempt(attempt.attempt_id, wrong, 25.0)
daily_events = store.alternate_learning_activity_rows(student.student_id, challenge.challenge_id, "daily")
counts = {name: sum(row.domain == name for row in daily_events) for name in (
    "Multiplication", "Addition Facts", "Subtraction Facts", "Division Facts", "Integers"
)}
check("Mixed routes exactly two events to every domain", all(value == 2 for value in counts.values()))
check("Mixed multiplication items do not enter mastery", store.get_mastery(student.student_id) == [])
misses = missed_question_items(questions, wrong)
store.record_alternate_fix_batch(
    attempt.attempt_id,
    [{"question_number": item["question_number"], "student_answer": item["correct_answer"]} for item in misses],
)
fix_events = store.alternate_learning_activity_rows(student.student_id, challenge.challenge_id, "fix_miss")
fix_counts = {name: sum(row.domain == name for row in fix_events) for name in counts}
check("Mixed Fix keeps two corrections in every true domain", all(value == 2 for value in fix_counts.values()))
check("Mixed all-domain Fix still leaves mastery untouched", store.get_mastery(student.student_id) == [])

# Mystery repair now requires alternate follow-up completion, not Daily completion alone.
store, klass, student, challenge, questions, attempt = setup("Addition Facts", date(2026, 8, 31))
values = [int(q["correct_answer"]) for q in questions]
values[0] += 1
store.complete_custom_attempt(attempt.attempt_id, values, 20.0)
check("alternate Daily alone does not qualify Mystery repair", store.completed_mystery_days(student.student_id, date(2026, 8, 31), through_day_number=1) == [])
misses = missed_question_items(questions, values, default_domain="Addition Facts")
store.record_alternate_fix_batch(attempt.attempt_id, [{"question_number": misses[0]["question_number"], "student_answer": misses[0]["correct_answer"]}])
check("alternate completed Fix still waits for Focus before Mystery repair", store.completed_mystery_days(student.student_id, date(2026, 8, 31), through_day_number=1) == [])

# Teacher Today now carries alternate students through Fix -> Focus -> Done.
rows = [
    {"student_id": "a", "status": "Complete"},
    {"student_id": "b", "status": "In progress"},
    {"student_id": "c", "status": "Not started"},
]
pending = SimpleNamespace(completed_at=None, fix_completed_at=None)
focus = SimpleNamespace(completed_at=None, fix_completed_at="done", focus_completed_at=None)
done = SimpleNamespace(completed_at="done", fix_completed_at="done", focus_completed_at="done")
summary = summarize_routine_for_mode(rows, {"a": pending}, "Mixed")
check("teacher Mixed pending completion shows Fix", summary["fix"] == 1 and summary["done"] == 0 and summary["focus"] == 0)
check("teacher Mixed pending label is Fix", routine_label_for_mode(rows[0], pending, "Mixed") == "🟡 Fix Your Misses")
summary = summarize_routine_for_mode(rows, {"a": focus}, "Mixed")
check("teacher Mixed completed Fix moves to Focus", summary["focus"] == 1 and summary["done"] == 0)
check("teacher Mixed Focus label is Focus", routine_label_for_mode(rows[0], focus, "Mixed") == "🟡 Focus Practice")
summary = summarize_routine_for_mode(rows, {"a": done}, "Mixed")
check("teacher Mixed completed Focus shows Done", summary["done"] == 1 and summary["focus"] == 0)
check("teacher Mixed done label is Done", routine_label_for_mode(rows[0], done, "Mixed") == "🟢 Done")

# Reset removes alternate follow-up state/evidence and does not need a mastery rebuild source.
store, klass, student, challenge, questions, attempt = setup("Division Facts")
values = [int(q["correct_answer"]) for q in questions]
store.complete_custom_attempt(attempt.attempt_id, values, 20.0)
check("alternate reset setup has progress", store.get_alternate_learning_progress(student.student_id, challenge.challenge_id) is not None)
store.reset_daily_attempt(student.student_id, challenge.challenge_id)
check("alternate reset clears progress", store.get_alternate_learning_progress(student.student_id, challenge.challenge_id) is None)
check("alternate reset clears events", store.alternate_learning_activity_rows(student.student_id, challenge.challenge_id) == [])

# Migration/storage contracts.
migration = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_17.sql").read_text(encoding="utf-8").lower()
schema = (ROOT / "SUPABASE_SCHEMA.sql").read_text(encoding="utf-8").lower()
for table in ("alternate_learning_progress", "alternate_learning_events"):
    check(f"migration creates {table}", f"create table if not exists public.{table}" in migration)
    check(f"schema includes {table}", f"create table if not exists public.{table}" in schema)
    check(f"schema RLS {table}", f"alter table public.{table} enable row level security" in schema)
check("migration backfills previously completed alternate Dailies", "on conflict (student_id, challenge_id) do nothing" in migration and "da.completed_at" in migration)
check("event storage has future Focus activity slot", "activity_type in ('daily','fix_miss','focus')" in migration)
check("event storage separates domain and skill", "domain text not null" in migration and "skill_key text not null" in migration and "item_key text not null" in migration)

# UI/component contracts.
student_ui = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
component = (ROOT / "alt_fix_component" / "index.html").read_text(encoding="utf-8")
store_source = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
check("alternate student UI declares Fix component", '"tdfc_alt_fix_v2194"' in student_ui and "ALT_FIX_COMPONENT" in student_ui)
check("alternate student UI waits for follow-up completion", "progress.completed_at is None" in student_ui and "record_alternate_fix_batch" in student_ui)
check("alternate student UI gives Mystery only after Focus branch", student_ui.index("Next: Focus Practice") < student_ui.index("Today's Mystery Reward"))
check("Fix component uses stable digit update", "function addDigit" in component and "updateEntry()" in component)
check("Fix component requires correction before advancing", "value!==Number(item.correct_answer)" in component)
check("Fix component does not render correct answer text", "${item.correct_answer}" not in component)
check("Supabase health checks alternate tables", 'table("alternate_learning_progress")' in store_source and 'table("alternate_learning_events")' in store_source)
check("Supabase has class alternate progress bulk read", "def class_alternate_learning_progress" in store_source)
check("Supabase reset removes alternate state", 'table("alternate_learning_events").delete()' in store_source and 'table("alternate_learning_progress").delete()' in store_source)

# Protected high-value multiplication/student surfaces remain byte-identical to v2.17.0.
expected_hashes = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "daily_modes.py": "f37b151fc44514f761f66f616434d26764df9719b0ab64d1865c9ee0d1881561",
    "student_igniter_ui.py": "043f3905b3e37a926cbae66d40de5e9ff963b2af3676f6bc4678336ca08e39ed",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
}
for rel, expected in expected_hashes.items():
    current = (ROOT / rel).read_bytes()
    check(f"protected unchanged {rel}", sha256(current).hexdigest() == expected)

print(f"v2.17.0 Follow-Up Foundation: PASS ({len(checks)}/{len(checks)} checks)")
