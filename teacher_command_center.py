from __future__ import annotations

"""Teacher-only helpers for the v2.14 command center.

This module intentionally owns no student routing or student persistence.  It
uses the existing ``app_settings`` table for lightweight teacher-day metadata
such as attendance exceptions, so v2.14 does not require a database migration.
"""

from datetime import date
from typing import Iterable, Mapping


def teacher_absence_setting_key(day: date | str, class_id: str) -> str:
    day_key = day.isoformat() if isinstance(day, date) else str(day)
    return f"teacher_absences::{day_key}::{str(class_id)}"


def load_absent_student_ids(store, day: date | str, class_id: str) -> set[str]:
    """Return teacher-marked absences for one class/day.

    Older/malformed values are treated as empty rather than taking down Today.
    """
    try:
        value = store.get_app_setting(teacher_absence_setting_key(day, class_id))
    except Exception:
        return set()
    if isinstance(value, Mapping):
        value = value.get("student_ids", [])
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(item) for item in value if str(item).strip()}


def save_absent_student_ids(store, day: date | str, class_id: str, student_ids: Iterable[str]) -> None:
    cleaned = sorted({str(item) for item in student_ids if str(item).strip()})
    key = teacher_absence_setting_key(day, class_id)
    if cleaned:
        store.set_app_setting(key, cleaned)
    else:
        store.delete_app_setting(key)


def eligible_absence_student_ids(status_rows: Iterable[Mapping]) -> set[str]:
    """Only students who have not started may be marked absent today.

    This keeps attendance exceptions teacher-only: an opened/in-progress or
    completed Daily is never hidden from teacher counts by an attendance flag.
    """
    result: set[str] = set()
    for row in status_rows:
        sid = str(row.get("student_id") or "")
        if sid and str(row.get("status") or "") == "Not started":
            result.add(sid)
    return result


def normalize_absent_student_ids(status_rows: Iterable[Mapping], requested_ids: Iterable[str]) -> set[str]:
    allowed = eligible_absence_student_ids(status_rows)
    return {str(item) for item in requested_ids if str(item) in allowed}


def present_status_rows(status_rows: Iterable[Mapping], absent_ids: Iterable[str]) -> list[dict]:
    absent = {str(item) for item in absent_ids}
    return [dict(row) for row in status_rows if str(row.get("student_id")) not in absent]


def summarize_daily_status(status_rows: Iterable[Mapping], absent_ids: Iterable[str] = ()) -> dict[str, int]:
    rows = [dict(row) for row in status_rows]
    absent = {str(item) for item in absent_ids}
    present = [row for row in rows if str(row.get("student_id")) not in absent]
    return {
        "enrolled": len(rows),
        "absent": sum(str(row.get("student_id")) in absent for row in rows),
        "present": len(present),
        "complete": sum(str(row.get("status") or "") == "Complete" for row in present),
        "in_progress": sum(str(row.get("status") or "") == "In progress" for row in present),
        "not_started": sum(str(row.get("status") or "") == "Not started" for row in present),
    }


def summarize_learning_routine(status_rows: Iterable[Mapping], progress_map: Mapping, absent_ids: Iterable[str] = ()) -> dict[str, int]:
    """Summarize where present students are in the full Daily learning routine."""
    absent = {str(item) for item in absent_ids}
    result = {"done": 0, "daily": 0, "fix": 0, "focus": 0, "not_started": 0}
    for row in status_rows:
        sid = str(row.get("student_id") or "")
        if sid in absent:
            continue
        progress = progress_map.get(sid)
        if progress is not None and getattr(progress, "completed_at", None):
            result["done"] += 1
        elif str(row.get("status") or "") == "Not started":
            result["not_started"] += 1
        elif str(row.get("status") or "") != "Complete":
            result["daily"] += 1
        elif progress is not None and getattr(progress, "fix_completed_at", None):
            result["focus"] += 1
        else:
            result["fix"] += 1
    return result


def _action_name_line(names: Iterable[str], fallback: str) -> str:
    cleaned = [str(name).strip() for name in names if str(name).strip()]
    return ", ".join(cleaned) if cleaned else fallback


def build_today_action_items(
    *,
    daily_summary: Mapping[str, int],
    routine_summary: Mapping[str, int],
    warmup_assigned: bool,
    warmup_finished: int,
    pending_prior_raffle: bool,
    not_started_names: Iterable[str] = (),
    follow_up_names: Iterable[str] = (),
    warmup_missing_names: Iterable[str] = (),
) -> list[dict[str, str]]:
    """Return concise teacher follow-ups with the student names already visible."""
    actions: list[dict[str, str]] = []
    present = int(daily_summary.get("present", 0))
    not_started = int(daily_summary.get("not_started", 0))
    started = int(daily_summary.get("complete", 0)) + int(daily_summary.get("in_progress", 0))
    if not_started and started:
        actions.append({
            "icon": "⚪",
            "title": f"Daily 10 not started · {not_started}",
            "detail": _action_name_line(not_started_names, "Open the class list below to see who has not started."),
            "route": "Student Support",
        })
    follow_up = int(routine_summary.get("fix", 0)) + int(routine_summary.get("focus", 0))
    if follow_up:
        actions.append({
            "icon": "🟡",
            "title": f"Follow-up practice remaining · {follow_up}",
            "detail": _action_name_line(follow_up_names, "Fix Your Misses or Focus Practice is still open."),
            "route": "Student Support",
        })
    if warmup_assigned and 0 < warmup_finished < present:
        remaining = max(0, present - int(warmup_finished))
        actions.append({
            "icon": "🧠",
            "title": f"Warm-Up not finished · {remaining}",
            "detail": _action_name_line(warmup_missing_names, "Open Warm-Up to review the remaining students."),
            "route": "Warm-Up",
        })
    if pending_prior_raffle:
        actions.append({
            "icon": "🎟️",
            "title": "Last week's Weekly Mystery raffle needs a drawing",
            "detail": "You can draw it without changing this week's Mystery.",
            "route": "Weekly Mystery",
        })
    if not actions and present:
        actions.append({
            "icon": "✅",
            "title": "All clear for now",
            "detail": "Nothing needs your attention right now.",
            "route": "",
        })
    return actions
