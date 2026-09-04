from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from alternate_focus import ALT_FOCUS_SESSION_LENGTH, build_alternate_focus_plan, focus_candidate_pool
from alternate_followup import missed_question_items, skill_identity_for_question
from daily_modes import questions_for_mode
from fact_engine import APP_VERSION, CHALLENGE_VERSION, daily_facts_for_date
from fact_store import InMemoryFactStore
from teacher_command_center import summarize_routine_for_mode, routine_label_for_mode

ROOT = Path(__file__).resolve().parent
checks: list[str] = []


def check(label: str, value) -> None:
    if not value:
        raise AssertionError(label)
    checks.append(label)


check("v2.19 version", APP_VERSION == "2.19.3")
check("multiplication challenge unchanged", CHALLENGE_VERSION == "TDFC-DAILY-v1")
check("alternate Focus matches multiplication length", ALT_FOCUS_SESSION_LENGTH == 8)

modes = ("Addition Facts", "Subtraction Facts", "Division Facts", "Integers", "Mixed")
day = date(2026, 9, 2)

# Every alternate mode gets an eight-item deterministic Focus plan and current misses lead the plan.
for mode in modes:
    questions = questions_for_mode(day, mode)
    answers = [int(q["correct_answer"]) for q in questions]
    answers[0] += 1
    p1 = build_alternate_focus_plan(mode, questions, answers, [], student_id="student-a", date_key=day.isoformat())
    p2 = build_alternate_focus_plan(mode, questions, answers, [], student_id="student-a", date_key=day.isoformat())
    miss = missed_question_items(questions, answers, default_domain=None if mode == "Mixed" else mode)[0]
    check(f"{mode} Focus length is 8", len(p1) == 8)
    check(f"{mode} Focus is deterministic", p1 == p2)
    check(f"{mode} current miss is selected", miss["item_key"] in {x["item_key"] for x in p1})
    check(f"{mode} current miss is top priority", p1[0]["item_key"] == miss["item_key"])
    check(f"{mode} Focus items carry reasons", all(str(x.get("focus_reason") or "") for x in p1))
    check(f"{mode} Focus items have valid identities", all(skill_identity_for_question(x).domain for x in p1))

# Historical independent misses increase priority; coached Fix events do not.
add_questions = questions_for_mode(day, "Addition Facts")
add_answers = [int(q["correct_answer"]) for q in add_questions]
weak = focus_candidate_pool("Addition Facts")[-1]
ident = skill_identity_for_question(weak)
wrong_history = [SimpleNamespace(
    activity_type="daily", is_retry=False, domain=ident.domain, item_key=ident.item_key,
    skill_key=ident.skill_key, correct=False,
) for _ in range(5)]
weak_plan = build_alternate_focus_plan("Addition Facts", add_questions, add_answers, wrong_history, student_id="s", date_key=day.isoformat())
check("repeated independent miss becomes first Focus target", weak_plan[0]["item_key"] == ident.item_key)
fix_only = [SimpleNamespace(
    activity_type="fix_miss", is_retry=True, domain=ident.domain, item_key=ident.item_key,
    skill_key=ident.skill_key, correct=False,
) for _ in range(20)]
base_plan = build_alternate_focus_plan("Addition Facts", add_questions, add_answers, [], student_id="s", date_key=day.isoformat())
fix_plan = build_alternate_focus_plan("Addition Facts", add_questions, add_answers, fix_only, student_id="s", date_key=day.isoformat())
check("Fix corrections are not adaptive evidence", fix_plan == base_plan)
retry_only = [SimpleNamespace(
    activity_type="focus", is_retry=True, domain=ident.domain, item_key=ident.item_key,
    skill_key=ident.skill_key, correct=False,
) for _ in range(20)]
retry_plan = build_alternate_focus_plan("Addition Facts", add_questions, add_answers, retry_only, student_id="s", date_key=day.isoformat())
check("coached Focus retries are not adaptive evidence", retry_plan == base_plan)

# Mixed can focus on the true underlying need while remaining isolated from multiplication mastery.
mixed_questions = questions_for_mode(day, "Mixed")
mixed_answers = [int(q["correct_answer"]) for q in mixed_questions]
div_index = next(i for i, q in enumerate(mixed_questions) if q["category"] == "Division Facts")
mixed_answers[div_index] += 1
mixed_plan = build_alternate_focus_plan("Mixed", mixed_questions, mixed_answers, [], student_id="mix", date_key=day.isoformat())
check("Mixed routes current division miss into Focus", mixed_plan[0]["domain"] == "Division Facts")
check("Mixed plan stores real domains", all(item["domain"] in ("Multiplication","Addition Facts","Subtraction Facts","Division Facts","Integers") for item in mixed_plan))

# End-to-end store routine: Daily -> Fix -> Focus -> Done, for all five alternate modes.
def setup(mode: str):
    store = InMemoryFactStore()
    klass = store.create_class("Block 1")
    student = store.create_student(klass.class_id, "Falcon", "2468")
    challenge = store.get_or_create_challenge(day, CHALLENGE_VERSION, daily_facts_for_date(day))
    questions = questions_for_mode(day, mode)
    attempt = store.get_or_create_attempt(student.student_id, challenge.challenge_id, daily_mode=mode, custom_questions=questions)
    return store, klass, student, challenge, questions, attempt

for mode in modes:
    store, klass, student, challenge, questions, attempt = setup(mode)
    answers = [int(q["correct_answer"]) for q in questions]
    answers[0] += 1
    store.complete_custom_attempt(attempt.attempt_id, answers, 20.0)
    progress = store.get_alternate_learning_progress(student.student_id, challenge.challenge_id)
    check(f"{mode} Daily with miss is not done", progress is not None and progress.completed_at is None)
    misses = missed_question_items(questions, answers, default_domain=None if mode == "Mixed" else mode)
    store.record_alternate_fix_batch(attempt.attempt_id, [
        {"question_number": item["question_number"], "student_answer": item["correct_answer"]} for item in misses
    ])
    progress = store.get_alternate_learning_progress(student.student_id, challenge.challenge_id)
    check(f"{mode} Fix completes Step 2 only", progress.fix_completed_at is not None and progress.completed_at is None)
    history = store.recent_alternate_learning_events(student.student_id)
    plan = build_alternate_focus_plan(mode, questions, answers, history, student_id=student.student_id, date_key=day.isoformat())
    progress = store.set_alternate_focus_plan(student.student_id, challenge.challenge_id, mode, plan)
    check(f"{mode} Focus plan saved", len(progress.focus_plan) == 8)
    events = []
    for index, item in enumerate(plan, start=1):
        correct = int(item["correct_answer"])
        if index == 1:
            events.append({"client_event_id": f"{mode}:{index}:1", "activity_index": index, "student_answer": correct + 1, "response_seconds": 1.4, "is_retry": False})
            events.append({"client_event_id": f"{mode}:{index}:2", "activity_index": index, "student_answer": correct, "response_seconds": 0.8, "is_retry": True})
        else:
            events.append({"client_event_id": f"{mode}:{index}:1", "activity_index": index, "student_answer": correct, "response_seconds": 1.0, "is_retry": False})
    progress = store.record_alternate_focus_batch(attempt.attempt_id, events)
    focus_rows = store.alternate_learning_activity_rows(student.student_id, challenge.challenge_id, "focus")
    check(f"{mode} Focus completion marks routine Done", progress.focus_completed_at is not None and progress.completed_at is not None)
    check(f"{mode} Focus stores first attempts and retry", len(focus_rows) == 9 and sum(not row.is_retry for row in focus_rows) == 8)
    check(f"{mode} Focus first miss remains incorrect evidence", any(not row.is_retry and not row.correct for row in focus_rows))
    check(f"{mode} Focus correction is retry evidence", any(row.is_retry and row.correct for row in focus_rows))
    check(f"{mode} never writes multiplication mastery", store.get_mastery(student.student_id) == [])

# Perfect alternate Daily skips empty Fix but still requires Focus.
store, klass, student, challenge, questions, attempt = setup("Addition Facts")
answers = [int(q["correct_answer"]) for q in questions]
store.complete_custom_attempt(attempt.attempt_id, answers, 19.0)
progress = store.get_alternate_learning_progress(student.student_id, challenge.challenge_id)
check("perfect alternate Daily auto-completes Fix", progress.fix_completed_at is not None)
check("perfect alternate Daily does not skip Focus", progress.completed_at is None and progress.focus_completed_at is None)

# Server-side validation protects Focus evidence.
plan = build_alternate_focus_plan("Addition Facts", questions, answers, store.recent_alternate_learning_events(student.student_id), student_id=student.student_id, date_key=day.isoformat())
store.set_alternate_focus_plan(student.student_id, challenge.challenge_id, "Addition Facts", plan)
try:
    store.record_alternate_focus_batch(attempt.attempt_id, [{
        "client_event_id":"bad-retry", "activity_index":1, "student_answer":int(plan[0]["correct_answer"]),
        "response_seconds":1.0, "is_retry":True,
    }])
    rejected = False
except ValueError:
    rejected = True
check("Focus rejects retry without a first attempt", rejected)

# Mystery completion now waits for Focus, not just Fix.
store, klass, student, challenge, questions, attempt = setup("Division Facts")
answers = [int(q["correct_answer"]) for q in questions]
store.complete_custom_attempt(attempt.attempt_id, answers, 18.0)
check("Fix-only alternate day does not qualify Mystery", store.completed_mystery_days(student.student_id, day, through_day_number=3) == [])
plan = build_alternate_focus_plan("Division Facts", questions, answers, store.recent_alternate_learning_events(student.student_id), student_id=student.student_id, date_key=day.isoformat())
store.set_alternate_focus_plan(student.student_id, challenge.challenge_id, "Division Facts", plan)
events = [{"client_event_id":f"d:{i}","activity_index":i,"student_answer":int(q["correct_answer"]),"response_seconds":1.0,"is_retry":False} for i,q in enumerate(plan,1)]
store.record_alternate_focus_batch(attempt.attempt_id, events)
check("completed alternate Focus qualifies Mystery", store.completed_mystery_days(student.student_id, day, through_day_number=3) != [])

# Teacher Today now shows the same Fix/Focus stages as multiplication.
rows = [{"student_id":"a","status":"Complete"}]
fix_stage = SimpleNamespace(completed_at=None, fix_completed_at=None)
focus_stage = SimpleNamespace(completed_at=None, fix_completed_at="done")
done_stage = SimpleNamespace(completed_at="done", fix_completed_at="done")
check("alternate Today pending Fix label", routine_label_for_mode(rows[0], fix_stage, "Mixed") == "🟡 Fix Your Misses")
check("alternate Today pending Focus label", routine_label_for_mode(rows[0], focus_stage, "Mixed") == "🟡 Focus Practice")
check("alternate Today Done label", routine_label_for_mode(rows[0], done_stage, "Mixed") == "🟢 Done")
summary = summarize_routine_for_mode(rows, {"a":focus_stage}, "Mixed")
check("alternate Today counts Focus stage", summary["focus"] == 1 and summary["done"] == 0)

# UI/component contract mirrors multiplication: independent question first, model only after a miss.
student_ui = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
component = (ROOT / "alt_focus_component" / "index.html").read_text(encoding="utf-8")
focus_source = (ROOT / "alternate_focus.py").read_text(encoding="utf-8")
store_source = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
check("student UI declares alternate Focus component", '"tdfc_alt_focus_v2193"' in student_ui and "ALT_FOCUS_COMPONENT" in student_ui)
check("student UI builds adaptive plan", "build_alternate_focus_plan" in student_ui and "recent_alternate_learning_events" in student_ui)
check("student UI saves Focus evidence", "record_alternate_focus_batch" in student_ui)
check("student UI unlocks Mystery after Focus branch", student_ui.index("Next: Focus Practice") < student_ui.index("Today's Mystery Reward"))
check("finished banner includes Focus", "Focus Practice ✓" in student_ui)
check("Focus component begins with independent question", "initialPhase" in component and "FOCUS FACT" in component)
check("wrong first attempt opens coach", "state.phase='coach'" in component)
check("Focus model retains SEE CONNECT TURN", "SEE IT" in component and "CONNECT IT" in component and "YOUR TURN" in component)
check("Focus has Watch and Try Again", "▶ WATCH IT" in component and "TRY AGAIN →" in component)
check("Focus records retry flag", "is_retry:!!isRetry" in component)
check("Focus supports negative integer answers", "toggleMinus" in component and 'id="minus"' in component)
check("Focus keypad stays mounted between digits", "updateEntry()" in component)
check("Focus supports all v2.18 visual models", all(marker in component for marker in ("ten_frame","part_whole","equal_groups","integer_line","multiplication_array")))
check("adaptive planner ignores Fix evidence", 'activity == "fix_miss"' in focus_source)
check("adaptive planner ignores coached Focus retry evidence", 'activity == "focus" and bool(_get(row, "is_retry", False))' in focus_source)
check("alternate planner does not import multiplication adaptive engine", "adaptive_engine" not in focus_source)
check("Supabase stores Focus plan", "def set_alternate_focus_plan" in store_source)
check("Supabase stores Focus batch", "def record_alternate_focus_batch" in store_source)
check("Supabase can read recent alternate evidence", "def recent_alternate_learning_events" in store_source)

# v2.17 already reserved the storage needed by v2.19: no new migration.
migration = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_17.sql").read_text(encoding="utf-8")
check("v2.17 reserved focus_plan", "focus_plan jsonb" in migration)
check("v2.17 reserved focus completion", "focus_completed_at" in migration)
check("v2.17 reserved focus events", "'focus'" in migration)
check("v2.19 needs no SQL migration", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_19.sql").exists())

# Teacher visibility is additive and read-only.
teacher_ui = (ROOT / "teacher_intelligence_ui.py").read_text(encoding="utf-8")
check("Student Support shows alternate Focus progress", "Today's Focus Practice" in teacher_ui and "Focus questions complete" in teacher_ui)

# Protected multiplication surfaces remain byte-identical to v2.19.1.
expected_hashes = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "daily_modes.py": "2e6633604d9ea2f21b4054e38827eea1eec99f47e5562befa4c1e62f840f3b5e",
    "student_igniter_ui.py": "043f3905b3e37a926cbae66d40de5e9ff963b2af3676f6bc4678336ca08e39ed",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
}
for rel, expected in expected_hashes.items():
    check(f"protected unchanged {rel}", sha256((ROOT / rel).read_bytes()).hexdigest() == expected)

print(f"v2.19.1 Adaptive Focus Practice: PASS ({len(checks)}/{len(checks)} checks)")
