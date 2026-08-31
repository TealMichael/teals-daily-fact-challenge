from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
import hashlib

from fact_engine import APP_VERSION, CHALLENGE_VERSION
from fact_store import InMemoryFactStore
from teacher_command_center import (
    build_today_action_items,
    eligible_absence_student_ids,
    load_absent_student_ids,
    normalize_absent_student_ids,
    present_status_rows,
    save_absent_student_ids,
    summarize_daily_status,
    summarize_learning_routine,
    teacher_absence_setting_key,
)

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TODAY = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")

checks: list[str] = []
def check(name: str, condition: bool) -> None:
    assert condition, name
    checks.append(name)


check("v2.16.0 version", APP_VERSION == "2.16.1")
check("multiplication challenge untouched", CHALLENGE_VERSION == "TDFC-DAILY-v1")
check("v2.14 requires no SQL migration", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_14.sql").exists())

# Teacher-only attendance metadata uses the existing app_settings persistence.
store = InMemoryFactStore()
klass = store.create_class("Block 1")
students = [store.create_student(klass.class_id, f"Student {i}", f"24{i:02d}"[-4:]) for i in range(1, 4)]
day = date(2026, 8, 27)
status = [
    {"student_id": students[0].student_id, "nickname": students[0].nickname, "status": "Complete", "correct_count": 10, "timed_seconds": 20.0},
    {"student_id": students[1].student_id, "nickname": students[1].nickname, "status": "Not started", "correct_count": None, "timed_seconds": None},
    {"student_id": students[2].student_id, "nickname": students[2].nickname, "status": "In progress", "correct_count": None, "timed_seconds": None},
]
check("absence setting is day and class scoped", teacher_absence_setting_key(day, klass.class_id).startswith("teacher_absences::2026-08-27::"))
check("completed student cannot become teacher-count absence", students[0].student_id not in eligible_absence_student_ids(status))
check("in-progress student cannot become teacher-count absence", students[2].student_id not in eligible_absence_student_ids(status))
requested = {students[0].student_id, students[1].student_id}
normalized = normalize_absent_student_ids(status, requested)
check("absence normalization keeps only unfinished student", normalized == {students[1].student_id})
save_absent_student_ids(store, day, klass.class_id, normalized)
check("absence persistence round trip", load_absent_student_ids(store, day, klass.class_id) == normalized)
summary = summarize_daily_status(status, normalized)
check("attendance adjusted present denominator", summary == {"enrolled": 3, "absent": 1, "present": 2, "complete": 1, "in_progress": 1, "not_started": 0})
check("present status excludes teacher-marked absence", {row["student_id"] for row in present_status_rows(status, normalized)} == {students[0].student_id, students[2].student_id})
save_absent_student_ids(store, day, klass.class_id, set())
check("clearing absences removes setting", load_absent_student_ids(store, day, klass.class_id) == set())

class Progress:
    def __init__(self, *, completed=False, fix=False):
        self.completed_at = "done" if completed else None
        self.fix_completed_at = "fix" if fix else None

progress = {
    students[0].student_id: Progress(completed=True),
    students[2].student_id: Progress(),
}
routine = summarize_learning_routine(status, progress, {students[1].student_id})
check("learning routine respects absence", routine == {"done": 1, "daily": 1, "fix": 0, "focus": 0, "not_started": 0})
actions = build_today_action_items(
    daily_summary=summary,
    routine_summary={"done": 0, "daily": 0, "fix": 1, "focus": 1, "not_started": 0},
    warmup_assigned=False,
    warmup_finished=0,
    pending_prior_raffle=True,
)
check("command center surfaces follow-up work", any("Follow-up practice remaining" in item["title"] for item in actions))
check("command center does not nag when no Warm-Up is assigned", not any("No Warm-Up" in item["title"] for item in actions))
check("command center surfaces missed raffle", any("raffle" in item["title"].lower() for item in actions))
partial_actions = build_today_action_items(
    daily_summary={"present": 4, "complete": 1, "in_progress": 1, "not_started": 2},
    routine_summary={"done": 0, "daily": 0, "fix": 0, "focus": 0, "not_started": 2},
    warmup_assigned=True, warmup_finished=2, pending_prior_raffle=False,
)
check("command center flags partial Daily start", any("Daily 10 not started" in item["title"] for item in partial_actions))
check("command center flags partial Warm-Up completion", any("Warm-Up not finished" in item["title"] for item in partial_actions))

# Classroom-scale attendance metadata stays class-scoped and never changes roster records.
scale_store = InMemoryFactStore()
scale_classes = [scale_store.create_class(f"Block {i}") for i in range(1, 5)]
for class_record in scale_classes:
    roster = [scale_store.create_student(class_record.class_id, f"{class_record.class_name}-{i:02d}", f"{i:04d}") for i in range(1, 31)]
    absent = {student.student_id for student in roster[:3]}
    save_absent_student_ids(scale_store, day, class_record.class_id, absent)
check("4x30 attendance settings remain class-scoped", all(len(load_absent_student_ids(scale_store, day, item.class_id)) == 3 for item in scale_classes))
check("attendance settings never deactivate students", all(len(scale_store.list_students(item.class_id)) == 30 for item in scale_classes))

# Navigation grouping keeps daily tools prominent while retaining every old teacher destination.
check("primary teacher nav keeps everyday tools one tap away", '["📊 Today", "🧠 Warm-Up", "📈 Learning", "🕵️ Weekly Mystery", "⚙️ Manage"]' in APP)
check("learning tools are grouped", all(label in APP for label in ["📈 Learning Data", "🛠️ Student Support"]))
check("administrative tools are grouped", '["👥 Classes & Rosters", "🖥️ Clock", "🧪 Test Student"]' in APP)
check("daily setup remains tucked with classes", '["👥 Rosters", "🎯 Daily 10 Setup"]' in APP)
check("Today has all-class snapshot", "All Classes" in TODAY and '"Open class"' in TODAY)
check("Today has action center", "Quick follow-ups" in TODAY and "build_today_action_items" in TODAY)
check("Today exposes quick teacher routes", all(label in TODAY for label in ["today_go_warmup", "today_go_support", "today_go_mystery", "today_go_daily_setup"]))
check("Today does not require attendance maintenance", "Attendance exceptions" not in TODAY and "Save attendance exceptions" not in TODAY)
check("refresh timestamp uses Indiana timezone", 'datetime.now(DAILY_TIMEZONE)' in APP)
check("class-list terminal failure no longer crashes Today", "Classes could not load just now" in TODAY)
check("student support has confirmed reopen", "Reopen with a fresh Daily attempt" in APP and "confirm_reopen_daily" in APP)
check("student support uses archive semantics", "Archive student" in APP and "Archiving keeps the student's history and PIN" in APP)

# The most sensitive student files remain byte-for-byte v2.13.2.
protected_files = {
    "daily_sprint_component/index.html": "f7abd3d565c20c89ebba833362229eeaa1a8706904d7abc7f3395acecc990fdb",
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
    "persistent_login.py": "bace7a3ae337c5cb651afe16face0262ebae482d56e1b435de1e997293a289f2",
}
for relative, expected in protected_files.items():
    actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    check(f"protected file unchanged: {relative}", actual == expected)

# app.py mixes teacher and student routing, so protect the critical student functions independently.
student_function_hashes = {
    "render_daily": "ed784a9f63014a658ae82ffded297209daa252aecd581e8ee37edc3723cea712",
    "handle_persistent_student_login": "2a71443811fa5ca321b1da2c573f8d7c489b136d8ce786164988ef0b5d5ce00d",
    "render_header": "209effe42c82db72f5593b1037669399f853c4e96dc47fc0eac0ed1a70d2d8a3",
}
tree = ast.parse(APP)
functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
for name, expected in student_function_hashes.items():
    segment = ast.get_source_segment(APP, functions[name])
    actual = hashlib.sha256(segment.encode("utf-8")).hexdigest()
    check(f"student app function unchanged: {name}", actual == expected)

print(f"v2.14.2 Teacher Command Center: {len(checks)}/{len(checks)} checks passed")
