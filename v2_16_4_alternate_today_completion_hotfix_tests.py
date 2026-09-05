from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fact_engine import APP_VERSION
from teacher_command_center import (
    build_today_action_items,
    routine_label_for_mode,
    summarize_daily_status,
    summarize_routine_for_mode,
)

ROOT = Path(__file__).resolve().parent
TODAY = (ROOT / "teacher_today_ui.py").read_text()
ALT_MODES = ("Addition Facts", "Subtraction Facts", "Division Facts", "Integers", "Mixed")

checks = []
def check(label, value):
    if not value:
        raise AssertionError(label)
    checks.append(label)

check("current version", APP_VERSION == "2.19.7")
check("Today derives selected Daily mode", 'multiplication_routine = daily_mode == "Multiplication"' in TODAY)
check("alternate Today uses alternate progress query", "store.class_alternate_learning_progress" in TODAY)
check("alternate Today does not reuse multiplication progress", "if multiplication_routine:" in TODAY and "store.class_learning_progress" in TODAY)
check("follow-up names work for both routine types", "if progress_error is None:" in TODAY)
check("alternate Today explains full completion", "Done means Daily 10 + Fix Your Misses + Focus Practice are complete." in TODAY)
check("Today uses mode-aware routine helper", "summarize_routine_for_mode(status, progress_map, daily_mode)" in TODAY)
check("Where everyone is uses mode-aware label helper", "routine_label_for_mode(row, progress, daily_mode)" in TODAY)

rows = [
    {"student_id": "a", "nickname": "Alpha", "status": "Complete", "correct_count": 9, "timed_seconds": 20.0},
    {"student_id": "b", "nickname": "Beta", "status": "In progress", "correct_count": None, "timed_seconds": None},
    {"student_id": "c", "nickname": "Gamma", "status": "Not started", "correct_count": None, "timed_seconds": None},
]
daily_summary = summarize_daily_status(rows)
pending = SimpleNamespace(completed_at=None, fix_completed_at=None)
focus = SimpleNamespace(completed_at=None, fix_completed_at="done", focus_completed_at=None)
done = SimpleNamespace(completed_at="done", fix_completed_at="done", focus_completed_at="done")

for mode in ALT_MODES:
    summary = summarize_routine_for_mode(rows, {"a": pending}, mode)
    check(f"{mode}: completed Daily waits in Fix", summary["fix"] == 1 and summary["done"] == 0)
    check(f"{mode}: in-progress stays Daily", summary["daily"] == 1)
    check(f"{mode}: not-started remains separate", summary["not_started"] == 1)
    check(f"{mode}: pending label is Fix", routine_label_for_mode(rows[0], pending, mode) == "🟡 Fix Your Misses")
    focus_summary = summarize_routine_for_mode(rows, {"a": focus}, mode)
    check(f"{mode}: Fix complete moves to Focus", focus_summary["focus"] == 1 and focus_summary["done"] == 0)
    check(f"{mode}: Focus label is Focus", routine_label_for_mode(rows[0], focus, mode) == "🟡 Focus Practice")
    done_summary = summarize_routine_for_mode(rows, {"a": done}, mode)
    check(f"{mode}: follow-up complete is Done", done_summary["done"] == 1 and done_summary["fix"] == 0)
    check(f"{mode}: done label is Done", routine_label_for_mode(rows[0], done, mode) == "🟢 Done")
    actions = build_today_action_items(
        daily_summary=daily_summary,
        routine_summary=summary,
        warmup_assigned=False,
        warmup_finished=0,
        pending_prior_raffle=False,
        not_started_names=["Gamma"],
        follow_up_names=["Alpha"],
        warmup_missing_names=[],
    )
    check(f"{mode}: follow-up alert now appears", any("Follow-up practice remaining" in item["title"] for item in actions))

# Multiplication remains the original three-stage routine.
check("Multiplication Daily complete without progress needs Fix", routine_label_for_mode(rows[0], None, "Multiplication") == "🟡 Fix Your Misses")
fix_progress = SimpleNamespace(completed_at=None, fix_completed_at="done")
check("Multiplication Fix complete still needs Focus", routine_label_for_mode(rows[0], fix_progress, "Multiplication") == "🟡 Focus Practice")
check("Multiplication done remains Done", routine_label_for_mode(rows[0], done, "Multiplication") == "🟢 Done")

print(f"v2.16.4 alternate Today compatibility under v2.19: PASS ({len(checks)}/{len(checks)} checks)")
