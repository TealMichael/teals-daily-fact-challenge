from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib

from alternate_focus import build_alternate_focus_plan
from daily_modes import questions_for_mode
from fact_engine import APP_VERSION
from fact_store import InMemoryFactStore, AlternateLearningEventRecord

ROOT = Path(__file__).resolve().parent
CHECKS = 0


def check(label: str, condition: bool) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1


def section(source: str, start_name: str, next_name: str) -> str:
    starts = [token for token in (f"def {start_name}", f"    def {start_name}") if token in source]
    if not starts:
        raise ValueError(f"missing start {start_name}")
    start = min(source.index(token) for token in starts)
    candidates = []
    for token in (f"\ndef {next_name}", f"\n    def {next_name}"):
        try:
            candidates.append(source.index(token, start))
        except ValueError:
            pass
    if not candidates:
        raise ValueError(f"missing end {next_name}")
    return source[start:min(candidates)]


check("v2.19.9 version", APP_VERSION == "2.19.9")

app = (ROOT / "app.py").read_text(encoding="utf-8")
alt_ui = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
igniter = (ROOT / "student_igniter_ui.py").read_text(encoding="utf-8")
supa = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")

# 1) Completed Igniter bypass: after completion is known, later Daily/Fix/Focus
# reruns return before either warm-up database read.
quick = section(igniter, "render_quick_warmup", "question_for_slot") if False else igniter[igniter.index("def render_quick_warmup"):]
check("Igniter completion cache is date/student/class scoped", 'warmup_complete::{student_id}::{class_id}::{day.isoformat()}' in quick)
check("Igniter completion bypass precedes warmup-set read", quick.index("if st.session_state.get(complete_cache_key, False):") < quick.index("store.get_warmup_set"))
check("completed Igniter persists bypass before Daily", "st.session_state[complete_cache_key] = True" in quick)

# 2) Alternate Daily reruns reuse only immutable challenge/setup context. The
# attempt itself is deliberately re-read so Teacher → Reopen Daily remains live.
# Multiplication is excluded from this cache and keeps its proven first-load path.
load_ctx = section(app, "load_student_daily_context", "load_leaderboard_context")
check("alternate context cache exists", "alt_day_context::" in app)
check("speed pass never caches alternate attempt objects", "alt_attempt::" not in app and "alt_attempt::" not in alt_ui)
check("cached alternate path rechecks authoritative attempt", "store.get_attempt_for_student" in load_ctx)
check("alternate cache returns only non-multiplication attempts", '!= "Multiplication"' in load_ctx)
check("support reset is detected when cached attempt is gone", "if attempt is not None:" in load_ctx and "else:" in load_ctx)
check("reset path rereads strict configured mode", "A support reset/reopen was detected" in load_ctx and "strict=True" in load_ctx)
check("reset path can create a fresh configured attempt", load_ctx.count("store.get_or_create_attempt") >= 2 and "questions_for_mode" in load_ctx)
check("fresh path still starts with established challenge loader", "day, facts, challenge = ensure_today(store)" in load_ctx)
check("multiplication attempts are not put in alternate cache", 'if str(getattr(attempt, "daily_mode", None) or "Multiplication") != "Multiplication":' in load_ctx)

# 3) Alternate completed-Daily / follow-up state stays in the student session
# after successful writes instead of immediately re-reading the same rows. Progress
# is attempt-scoped so a reopened Daily cannot inherit the deleted attempt's state.
check("applied Daily evidence skips redundant repair read", 'getattr(attempt, "learning_evidence_applied_at", None) is not None' in alt_ui)
check("alternate progress is session cached", "alt_progress::" in alt_ui and "_cache_progress" in alt_ui)
check("alternate progress cache is attempt scoped", 'return f"alt_progress::{attempt.attempt_id}"' in alt_ui)
check("Fix completion updates cached progress", "progress = store.record_alternate_fix_batch" in alt_ui and "_cache_progress(attempt, progress)" in alt_ui)
check("Focus completion updates cached progress", "progress = store.record_alternate_focus_batch" in alt_ui)

# 4) Focus history downloads only scoring fields, still newest-first and same 500 cap.
check("student Focus uses slim evidence helper", "recent_alternate_focus_evidence" in alt_ui and "recent_alternate_learning_events(attempt.student_id" not in alt_ui)
slim = section(supa, "recent_alternate_focus_evidence", "mark_alternate_focus_complete")
check("Focus evidence query selects only planner fields", '.select("activity_type,is_retry,domain,item_key,skill_key,correct,created_at")' in slim)
check("Focus evidence preserves newest-first ordering", '.order("created_at", desc=True)' in slim)

# 5) Normal successful alternate writes avoid immediate verification round trips.
mark_fix = section(supa, "mark_alternate_fix_complete", "set_alternate_focus_plan")
set_plan = section(supa, "set_alternate_focus_plan", "recent_alternate_learning_events")
mark_focus = section(supa, "mark_alternate_focus_complete", "_ensure_alternate_followup_for_attempt")
record_fix = section(supa, "record_alternate_fix_batch", "record_alternate_focus_batch")
record_focus = section(supa, "record_alternate_focus_batch", "rebuild_mastery")
complete_custom = section(supa, "complete_custom_attempt", "ensure_daily_learning_evidence")
check("Fix-complete write has no immediate read-back", mark_fix.count("get_or_create_alternate_learning_progress") == 1)
check("Focus-plan write has no immediate read-back", set_plan.count("get_or_create_alternate_learning_progress") == 1)
check("Focus-complete write has no immediate read-back", mark_focus.count("get_or_create_alternate_learning_progress") == 1)
check("Fix batch no longer reruns full Daily evidence repair", "ensure_alternate_followup_state" not in record_fix)
check("Focus batch loads saved Focus rows only once", record_focus.count("alternate_learning_activity_rows") == 1)
check("Focus batch combines existing + returned upsert rows", "rows = list(existing) + list(saved)" in record_focus)
check("alternate Daily completion reuses in-hand attempt", "completed_attempt = replace(" in complete_custom and "_ensure_alternate_followup_for_attempt(completed_attempt, repair_fix=False)" in complete_custom)

# 6) Test Student no longer reloads class list + sandbox student on every rerun.
test_mode = section(app, "render_teacher_test_student_mode", "render_teacher")
check("Test Student class record is session cached", 'teacher_test_student_class_record' in test_mode)
check("Test Student student record is session cached", 'teacher_test_student_record' in test_mode)
check("Test Student reads are fallback-only", 'if class_record is None or' in test_mode and 'if student is None or' in test_mode)

# Functional equivalence: the lightweight history feed must generate the exact
# same Focus plan as the full event records.
store = InMemoryFactStore()
student_id = "student-speed"
now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
rows = [
    AlternateLearningEventRecord(
        event_id=f"e{i}", student_id=student_id, challenge_id="c", attempt_id="a",
        daily_mode="Mixed", activity_type=activity, activity_index=i,
        domain=domain, skill_key=skill, skill_label=skill, item_key=item,
        prompt="x", student_answer=answer, correct_answer=answer,
        correct=correct, is_retry=retry, created_at=now - timedelta(minutes=i),
        response_seconds=None, client_event_id=f"client-{i}",
    )
    for i, (activity, retry, domain, skill, item, correct, answer) in enumerate([
        ("daily", False, "Addition Facts", "sum:10", "add:4:6", False, 10),
        ("focus", False, "Division Facts", "division:7", "div:42:7", False, 6),
        ("focus", True, "Division Facts", "division:7", "div:42:7", True, 6),
        ("daily", False, "Integers", "integer:subtract_negative", "int:5--5", False, 10),
        ("daily", False, "Multiplication", "mult:8", "mult:8:9", True, 72),
    ], start=1)
]
store.alternate_learning_events.extend(rows)
full = store.recent_alternate_learning_events(student_id, limit=500)
light = store.recent_alternate_focus_evidence(student_id, limit=500)
questions = questions_for_mode(date(2026, 9, 4), "Mixed")
answers = [int(q["correct_answer"]) for q in questions]
answers[0] += 1
plan_full = build_alternate_focus_plan("Mixed", questions, answers, full, student_id=student_id, date_key="2026-09-04")
plan_light = build_alternate_focus_plan("Mixed", questions, answers, light, student_id=student_id, date_key="2026-09-04")
check("slim Focus evidence produces identical plan", plan_full == plan_light)

# UI/teaching components are intentionally unchanged in this server-side speed pass.
EXPECTED_COMPONENTS = {
    "daily_alt_component/index.html": "332ee7265c450b00d4848a059f000439dba2089c4ec765bf18f41e2bed734c4d",
    "alt_fix_component/index.html": "6a60d52ce0775250b54477c2cafb909f3cf5e4cb6fe53d51795ca30aacda64d4",
    "alt_focus_component/index.html": "3fbc588093066e786dd4e579f9a4f0659d5480c5108f632a63f109ffd3460a86",
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
}
for rel, expected in EXPECTED_COMPONENTS.items():
    actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    check(f"unchanged protected/UI source: {rel}", actual == expected)

print(f"v2.19.9 Student Speed Pass: PASS ({CHECKS}/{CHECKS} checks)")
