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

check("v2.16.4 version", APP_VERSION == "2.16.4")
check("Today derives selected Daily mode", 'multiplication_routine = daily_mode == "Multiplication"' in TODAY)
check("alternate Today skips multiplication progress query", "if multiplication_routine:" in TODAY and "store.class_learning_progress" in TODAY)
check("follow-up names are multiplication-only", "if multiplication_routine and progress_error is None:" in TODAY)
check("alternate Today explains no follow-up", "This mode has no follow-up practice." in TODAY)
check("Today uses mode-aware routine helper", "summarize_routine_for_mode(status, progress_map, daily_mode)" in TODAY)
check("Where everyone is uses mode-aware label helper", "routine_label_for_mode(row, progress, daily_mode)" in TODAY)

rows = [
    {"student_id": "a", "nickname": "Alpha", "status": "Complete", "correct_count": 10, "timed_seconds": 20.0},
    {"student_id": "b", "nickname": "Beta", "status": "In progress", "correct_count": None, "timed_seconds": None},
    {"student_id": "c", "nickname": "Gamma", "status": "Not started", "correct_count": None, "timed_seconds": None},
]
daily_summary = summarize_daily_status(rows)

for mode in ALT_MODES:
    summary = summarize_routine_for_mode(rows, {}, mode)
    check(f"{mode}: completed Daily is fully done", summary["done"] == 1)
    check(f"{mode}: in-progress stays Daily", summary["daily"] == 1)
    check(f"{mode}: no Fix Misses invented", summary["fix"] == 0)
    check(f"{mode}: no Focus Practice invented", summary["focus"] == 0)
    check(f"{mode}: not-started remains separate", summary["not_started"] == 1)
    check(f"{mode}: complete label is Done", routine_label_for_mode(rows[0], None, mode) == "🟢 Done")
    check(f"{mode}: in-progress label is Daily 10", routine_label_for_mode(rows[1], None, mode) == "🟡 Daily 10")
    check(f"{mode}: not-started label is clean", routine_label_for_mode(rows[2], None, mode) == "⚪ Not started")
    actions = build_today_action_items(
        daily_summary=daily_summary,
        routine_summary=summary,
        warmup_assigned=False,
        warmup_finished=0,
        pending_prior_raffle=False,
        not_started_names=["Gamma"],
        follow_up_names=[],
        warmup_missing_names=[],
    )
    titles = [item["title"] for item in actions]
    check(f"{mode}: no follow-up alert", not any("Follow-up practice" in title for title in titles))

# Multiplication keeps the existing three-stage contract.
check(
    "Multiplication complete Daily without progress still needs Fix Misses",
    routine_label_for_mode(rows[0], None, "Multiplication") == "🟡 Fix Your Misses",
)
fix_progress = SimpleNamespace(completed_at=None, fix_completed_at="done")
check(
    "Multiplication Fix complete still needs Focus",
    routine_label_for_mode(rows[0], fix_progress, "Multiplication") == "🟡 Focus Practice",
)
done_progress = SimpleNamespace(completed_at="done", fix_completed_at="done")
check(
    "Multiplication full routine remains Done",
    routine_label_for_mode(rows[0], done_progress, "Multiplication") == "🟢 Done",
)
mult_summary = summarize_routine_for_mode(
    [rows[0]], {"a": SimpleNamespace(completed_at=None, fix_completed_at=None)}, "Multiplication"
)
check("Multiplication still reports Fix stage", mult_summary["fix"] == 1 and mult_summary["done"] == 0)

print(f"v2.16.4 alternate Today completion hotfix: PASS ({len(checks)}/{len(checks)} checks)")
