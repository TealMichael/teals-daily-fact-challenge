from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib

from adaptive_engine import MasterySnapshot, complete_mastery_map
from fact_engine import APP_VERSION, CHALLENGE_VERSION
from fact_store import StudentRecord
from teacher_intelligence import (
    build_student_signals,
    class_fact_priorities,
    fragile_facts_for_student,
    progress_signals,
    recommended_teaching_move,
    repeated_miss_facts,
    suggested_small_groups,
    weekly_recap,
)

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
STORE = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
UI = (ROOT / "teacher_intelligence_ui.py").read_text(encoding="utf-8")
LOGIC = (ROOT / "teacher_intelligence.py").read_text(encoding="utf-8")

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

check("v2.15 version", APP_VERSION == "2.19.1")
check("student Daily contract unchanged", CHALLENGE_VERSION == "TDFC-DAILY-v1")

# Phase 2 navigation + teacher UI contract.
check("Learning has four Phase 2 tools", '["🧭 Next Steps", "📈 Learning Data", "🛠️ Student Support", "📅 Weekly Recap"]' in APP)
check("Learning defaults to Next Steps", 'st.session_state["teacher_learning_section"] = "🧭 Next Steps"' in APP)
check("Next Steps renderer wired", "render_teacher_next_steps(store)" in APP)
check("Weekly Recap renderer wired", "render_teacher_weekly_recap(store)" in APP)
check("Student Support gets learning snapshot", "render_student_learning_snapshot(store, class_record, students, student)" in APP)
check("teacher intelligence is read-only by contract", "never writes" in LOGIC.lower() and "set_student_focus_override" not in LOGIC)
check("bulk teacher history method exists", "def teacher_daily_history(" in STORE)
check("teacher history keeps alternate modes out of multiplication answers", 'if str(row.get("daily_mode") or "Multiplication") == "Multiplication"' in STORE)
check("teacher history uses bulk reads", all(token in STORE for token in ['table("daily_challenges")', 'table("daily_attempts")', 'table("daily_answers")']))
check("teacher history chunks large answer-ID reads", "range(0, len(multiplication_attempt_ids), 100)" in STORE)
check("Next Steps includes best teaching opportunity", "Best Teaching Opportunity" in UI)
check("Next Steps includes small groups", "Suggested Small Groups" in UI)
check("Next Steps includes students worth a look", "Students Worth a Look" in UI)
check("Weekly Recap separates multiplication fluency", "Other Daily 10 modes are listed separately from multiplication fluency" in UI)
check("Student Support includes recent results", "Recent Daily 10 results" in UI)
check("no v2.15 SQL migration", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_15.sql").exists())

# Build deterministic teacher evidence.
today = date(2026, 8, 31)
created = datetime(2026, 8, 1, tzinfo=timezone.utc)
students = [
    StudentRecord("s1", "c1", "Alpha", True, created, "1111"),
    StudentRecord("s2", "c1", "Bravo", True, created, "2222"),
    StudentRecord("s3", "c1", "Charlie", True, created, "3333"),
]

def snap(a, b, *, ev=0, corr=0, ema=None, sec=None, streak=0, practiced=None):
    return MasterySnapshot(a=a, b=b, evidence_count=ev, correct_count=corr, ema_accuracy=ema, ema_seconds=sec, correct_streak=streak, last_practiced_at=practiced)

base = {student.student_id: complete_mastery_map([]) for student in students}
# 7x8 is a true accuracy need for two students -> dynamic family/small-group signal.
for sid in ("s1", "s2"):
    base[sid][(7, 8)] = snap(7, 8, ev=6, corr=3, ema=.52, sec=5.2, streak=0, practiced=datetime(2026, 8, 31, tzinfo=timezone.utc))
# Bravo also has a stable-but-slow fact.
base["s2"][(6, 7)] = snap(6, 7, ev=8, corr=8, ema=.96, sec=8.4, streak=6, practiced=datetime(2026, 8, 31, tzinfo=timezone.utc))
# Charlie has historically strong evidence with a recently broken streak: fragile watch signal.
base["s3"][(6, 8)] = snap(6, 8, ev=6, corr=5, ema=.76, sec=4.5, streak=0, practiced=datetime(2026, 8, 31, tzinfo=timezone.utc))
# One newly secured signal during last week.
base["s3"][(4, 6)] = snap(4, 6, ev=5, corr=5, ema=.95, sec=4.0, streak=5, practiced=datetime(2026, 8, 27, tzinfo=timezone.utc))

# 10 multiplication dates: previous five and recent five. Alpha rises from 60% to 90%.
all_dates = [date(2026, 8, 17) + timedelta(days=i) for i in range(5)] + [date(2026, 8, 24) + timedelta(days=i) for i in range(5)]
history = []
for idx, day in enumerate(all_dates):
    for student in students:
        correct_target = 6 if student.student_id == "s1" and idx < 5 else 9 if student.student_id == "s1" else 8
        answers = []
        for q in range(10):
            fact = (7, 8) if q in (0, 1) else (2 + (q % 5), 3 + (q % 6))
            correct = q < correct_target
            # Bravo repeatedly misses 7x8 in the recent period.
            if student.student_id == "s2" and idx >= 5 and q in (0, 1):
                correct = False
            answers.append({"a": fact[0], "b": fact[1], "correct": correct, "first_correct": correct, "response_seconds": 4.0})
        history.append({
            "attempt_id": f"{student.student_id}-{day}", "student_id": student.student_id,
            "nickname": student.nickname, "challenge_date": day.isoformat(), "daily_mode": "Multiplication",
            "correct_count": sum(a["first_correct"] for a in answers), "timed_seconds": 45.0,
            "answers": answers,
        })
# Alternate Daily completion in last week must count as completion but not multiplication fact evidence.
history.append({
    "attempt_id": "s3-alt", "student_id": "s3", "nickname": "Charlie", "challenge_date": "2026-08-28",
    "daily_mode": "Integers", "correct_count": 10, "timed_seconds": 22.0, "answers": [],
})

repeated = repeated_miss_facts(history)
check("repeated miss detector finds Bravo", "s2" in repeated)
check("repeated miss detector identifies 7x8", any(item["fact"] == "7 × 8" for item in repeated["s2"]))
fragile = fragile_facts_for_student(base["s3"], today=today)
check("fragile retrieval signal finds Charlie 6x8", "6 × 8" in fragile)

signals = build_student_signals(students, base, history, today=today)
alpha = next(signal for signal in signals if signal.student_id == "s1")
check("meaningful progress compares two five-Daily windows", alpha.accuracy_change is not None and alpha.accuracy_change >= .25)
check("progress list surfaces Alpha", progress_signals(signals)[0].student_id == "s1")

priorities = class_fact_priorities(base, history, limit=5)
check("7x8 is top teaching opportunity", priorities and priorities[0]["fact"] == "7 × 8")
check("top priority has two current accuracy needs", priorities[0]["needs_help"] == 2)
check("recommended move is small-group actionable", "accuracy group" in recommended_teaching_move(priorities[0], class_size=30).lower())

groups = suggested_small_groups(signals, base)
check("dynamic fact-family group created", any(group["name"].startswith("Needs 7s") or group["name"].startswith("Needs 8s") for group in groups))
check("accuracy-first group created", any(group["name"] == "Accuracy First" for group in groups))

recap = weekly_recap(history, base, week_start=date(2026, 8, 24), class_size=3)
check("weekly recap counts alternate Daily completion", recap["daily_completions"] == 16)
check("weekly recap counts only multiplication attempts for fluency", recap["multiplication_attempts"] == 15)
check("weekly recap multiplication accuracy ignores perfect integer attempt", recap["multiplication_accuracy"] is not None and recap["multiplication_accuracy"] < .90)
check("weekly recap reports mode mix", recap["modes"].get("Integers") == 1 and recap["modes"].get("Multiplication") == 15)
check("weekly recap finds common misses", bool(recap["common_misses"]))
check("weekly recap finds improving Alpha", any(row["nickname"] == "Alpha" for row in recap["progress"]))
check("weekly recap has conservative newly-secured signal", recap["newly_secured_signal_count"] >= 1)

# Classroom-scale teacher-intelligence simulation: four 30-student classes.
scale_ok = True
for block in range(1, 5):
    roster = [StudentRecord(f"b{block}s{i}", f"b{block}", f"B{block}-{i:02d}", True, created, f"{i:04d}") for i in range(1, 31)]
    maps = {student.student_id: complete_mastery_map([]) for student in roster}
    rows = []
    for index, student in enumerate(roster):
        if index < 6:
            maps[student.student_id][(7, 8)] = snap(7, 8, ev=6, corr=3, ema=.52, sec=5.0, streak=0, practiced=datetime(2026, 8, 31, tzinfo=timezone.utc))
        elif index < 10:
            maps[student.student_id][(6, 7)] = snap(6, 7, ev=8, corr=8, ema=.96, sec=8.2, streak=6, practiced=datetime(2026, 8, 31, tzinfo=timezone.utc))
        answers = [{"a": 7, "b": 8, "correct": index >= 6, "first_correct": index >= 6, "response_seconds": 4.0}]
        answers += [{"a": 3, "b": 4, "correct": True, "first_correct": True, "response_seconds": 3.0} for _ in range(9)]
        rows.append({"attempt_id": f"scale-{student.student_id}", "student_id": student.student_id, "nickname": student.nickname, "challenge_date": "2026-08-31", "daily_mode": "Multiplication", "correct_count": sum(a["first_correct"] for a in answers), "timed_seconds": 40.0, "answers": answers})
        rows.append({"attempt_id": f"scale-alt-{student.student_id}", "student_id": student.student_id, "nickname": student.nickname, "challenge_date": "2026-08-28", "daily_mode": "Integers", "correct_count": 10, "timed_seconds": 20.0, "answers": []})
    block_signals = build_student_signals(roster, maps, rows, today=today)
    block_priorities = class_fact_priorities(maps, rows)
    block_groups = suggested_small_groups(block_signals, maps)
    scale_ok = scale_ok and len(block_signals) == 30 and bool(block_priorities) and block_priorities[0]["fact"] == "7 × 8" and len(block_groups) <= 5
check("4x30 instructional-intelligence simulation passes", scale_ok)

# Protect student-facing and previously stable teacher modules byte-for-byte from v2.14.3.
protected = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "daily_alt_component/index.html": "59554532996c5259a1159fd6cdf7ab602b516ea25285000715eb65af52b2c816",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "persistent_login_component/index.html": "fae94c44f25512d2c017b24e17e3be2d987f21604072ed4c061fbae1cc9f9585",
    "pin_entry_component/index.html": "18a89b45481f83f33fd93746bdf854ba0e4b216c0c1f0904e035f871d5d8c2b7",
    "student_igniter_ui.py": "043f3905b3e37a926cbae66d40de5e9ff963b2af3676f6bc4678336ca08e39ed",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "daily_modes.py": "2e6633604d9ea2f21b4054e38827eea1eec99f47e5562befa4c1e62f840f3b5e",
    "warmup.py": "e9dc2faabf9234c4463f84fc02c3453b4a1f5e37376cd8461d1adccc34bb816b",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
    "teacher_insights.py": "4fdf3516e75a8d697747f4d92aadd3f39c51a116e5990054c5eca4c66b0094a5",
}
for relative, expected in protected.items():
    actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    check(f"protected v2.14.3 surface unchanged: {relative}", actual == expected)

check("app architecture remains under 3000 lines", len(APP.splitlines()) < 3000)

print(f"v2.16.0 Instructional Intelligence regression: {len(checks)}/{len(checks)} checks passed")
