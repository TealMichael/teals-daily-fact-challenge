from __future__ import annotations

"""Pure teacher-only instructional intelligence for v2.15.

This module interprets evidence that already exists in the app. It never writes
mastery, changes a student's Focus plan, or alters the student experience.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from typing import Mapping, Sequence

from adaptive_engine import MasterySnapshot
from teacher_insights import (
    BAND_HELP,
    BAND_KNOWN,
    BAND_SLOW,
    StudentFluencySummary,
    summarize_student_fluency,
    teacher_fact_band,
)


@dataclass(frozen=True)
class StudentSignal:
    student_id: str
    nickname: str
    summary: StudentFluencySummary
    repeated_misses: tuple[str, ...]
    fragile_facts: tuple[str, ...]
    recent_accuracy: float | None
    prior_accuracy: float | None
    accuracy_change: float | None


def _as_date(value) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _fact_label(a: int, b: int) -> str:
    a, b = sorted((int(a), int(b)))
    return f"{a} × {b}"


def _multiplication_answers(history: Sequence[Mapping], *, start: date | None = None, end: date | None = None) -> list[dict]:
    rows: list[dict] = []
    for attempt in history:
        if str(attempt.get("daily_mode") or "Multiplication") != "Multiplication":
            continue
        attempt_day = _as_date(attempt.get("challenge_date"))
        if attempt_day is None or (start and attempt_day < start) or (end and attempt_day > end):
            continue
        for answer in attempt.get("answers") or ():
            row = dict(answer)
            row["student_id"] = str(attempt.get("student_id") or "")
            row["nickname"] = str(attempt.get("nickname") or "")
            row["challenge_date"] = attempt_day
            row["attempt_id"] = str(attempt.get("attempt_id") or "")
            rows.append(row)
    return rows


def _recent_periods(history: Sequence[Mapping]) -> tuple[set[date], set[date]]:
    dates = sorted({
        _as_date(row.get("challenge_date")) for row in history
        if str(row.get("daily_mode") or "Multiplication") == "Multiplication"
        and _as_date(row.get("challenge_date")) is not None
    })
    recent = set(dates[-5:])
    prior = set(dates[-10:-5])
    return recent, prior


def _student_period_accuracy(history: Sequence[Mapping], student_id: str, period: set[date]) -> tuple[float | None, int]:
    if not period:
        return None, 0
    answers = [
        row for row in _multiplication_answers(history)
        if row["student_id"] == str(student_id) and row["challenge_date"] in period
    ]
    if not answers:
        return None, 0
    correct = sum(bool(row.get("first_correct", row.get("correct"))) for row in answers)
    return correct / len(answers), len(answers)


def repeated_miss_facts(history: Sequence[Mapping], *, min_misses: int = 2, start: date | None = None, end: date | None = None) -> dict[str, list[dict]]:
    """Return repeated independent Daily misses grouped by student."""
    counts: dict[tuple[str, int, int], dict] = {}
    for row in _multiplication_answers(history, start=start, end=end):
        if bool(row.get("first_correct", row.get("correct"))):
            continue
        a, b = sorted((int(row.get("a") or 0), int(row.get("b") or 0)))
        key = (row["student_id"], a, b)
        item = counts.setdefault(key, {
            "student_id": row["student_id"], "nickname": row["nickname"],
            "a": a, "b": b, "fact": _fact_label(a, b), "misses": 0, "last_date": row["challenge_date"],
        })
        item["misses"] += 1
        if row["challenge_date"] > item["last_date"]:
            item["last_date"] = row["challenge_date"]
    by_student: dict[str, list[dict]] = defaultdict(list)
    for item in counts.values():
        if int(item["misses"]) >= min_misses:
            by_student[str(item["student_id"])].append(item)
    for rows in by_student.values():
        rows.sort(key=lambda item: (-int(item["misses"]), item["fact"]))
    return dict(by_student)


def fragile_facts_for_student(full_map: Mapping[tuple[int, int], MasterySnapshot], *, today: date) -> list[str]:
    """Conservative watch signal: strong historical accuracy with a broken recent streak.

    This is deliberately called fragile rather than "lost mastery" because the app
    stores the current aggregate, not historical mastery-state snapshots.
    """
    cutoff = today - timedelta(days=14)
    rows = []
    for snapshot in full_map.values():
        if snapshot.evidence_count < 5 or snapshot.accuracy is None or snapshot.accuracy < 0.80:
            continue
        if snapshot.correct_streak > 1 or teacher_fact_band(snapshot) == BAND_KNOWN:
            continue
        practiced = snapshot.last_practiced_at.date() if snapshot.last_practiced_at else None
        if practiced is None or practiced < cutoff:
            continue
        rows.append(snapshot)
    rows.sort(key=lambda row: (row.correct_streak, row.ema_accuracy if row.ema_accuracy is not None else 1.0, row.a, row.b))
    return [_fact_label(row.a, row.b) for row in rows[:5]]


def build_student_signals(students, full_by_student: Mapping[str, Mapping[tuple[int, int], MasterySnapshot]], history: Sequence[Mapping], *, today: date) -> list[StudentSignal]:
    repeated = repeated_miss_facts(history, start=today - timedelta(days=14), end=today)
    recent_period, prior_period = _recent_periods(history)
    signals = []
    for student in students:
        sid = str(student.student_id)
        full_map = full_by_student[sid]
        summary = summarize_student_fluency(sid, student.nickname, full_map.values())
        recent_accuracy, recent_n = _student_period_accuracy(history, sid, recent_period)
        prior_accuracy, prior_n = _student_period_accuracy(history, sid, prior_period)
        change = None
        if recent_accuracy is not None and prior_accuracy is not None and recent_n >= 10 and prior_n >= 10:
            change = recent_accuracy - prior_accuracy
        signals.append(StudentSignal(
            student_id=sid,
            nickname=str(student.nickname),
            summary=summary,
            repeated_misses=tuple(item["fact"] for item in repeated.get(sid, [])[:5]),
            fragile_facts=tuple(fragile_facts_for_student(full_map, today=today)),
            recent_accuracy=recent_accuracy,
            prior_accuracy=prior_accuracy,
            accuracy_change=change,
        ))
    return signals


def class_fact_priorities(full_by_student: Mapping[str, Mapping[tuple[int, int], MasterySnapshot]], history: Sequence[Mapping], *, limit: int = 5) -> list[dict]:
    if not full_by_student:
        return []
    history_dates = [d for d in (_as_date(row.get("challenge_date")) for row in history) if d is not None]
    latest = max(history_dates) if history_dates else None
    recent_answers = _multiplication_answers(
        history, start=None if latest is None else latest - timedelta(days=14), end=latest
    )
    miss_counts: dict[tuple[int, int], int] = defaultdict(int)
    miss_students: dict[tuple[int, int], set[str]] = defaultdict(set)
    student_fact_misses: dict[tuple[str, int, int], int] = defaultdict(int)
    for row in recent_answers:
        if bool(row.get("first_correct", row.get("correct"))):
            continue
        a, b = sorted((int(row.get("a") or 0), int(row.get("b") or 0)))
        key = (a, b)
        miss_counts[key] += 1
        miss_students[key].add(row["student_id"])
        student_fact_misses[(row["student_id"], a, b)] += 1

    first = next(iter(full_by_student.values()))
    result = []
    for key in sorted(first):
        needs_help_names = []
        slow_names = []
        for sid, student_map in full_by_student.items():
            band = teacher_fact_band(student_map[key])
            if band == BAND_HELP:
                needs_help_names.append(str(sid))
            elif band == BAND_SLOW:
                slow_names.append(str(sid))
        repeated_students = sum(1 for sid in full_by_student if student_fact_misses[(sid, key[0], key[1])] >= 2)
        recent_students = len(miss_students.get(key, set()))
        score = len(needs_help_names) * 20 + repeated_students * 8 + recent_students * 3 + len(slow_names) * 2
        if score <= 0:
            continue
        result.append({
            "a": key[0], "b": key[1], "fact": _fact_label(*key),
            "needs_help": len(needs_help_names), "slow": len(slow_names),
            "recent_miss_students": recent_students, "recent_misses": miss_counts.get(key, 0),
            "repeated_students": repeated_students, "score": score,
        })
    return sorted(result, key=lambda row: (-row["score"], -row["needs_help"], -row["repeated_students"], row["fact"]))[:limit]


def recommended_teaching_move(priority: Mapping | None, *, class_size: int) -> str:
    if not priority:
        return "No class-wide multiplication gap is strong enough to interrupt the normal Daily + Focus routine."
    help_count = int(priority.get("needs_help") or 0)
    repeated = int(priority.get("repeated_students") or 0)
    slow = int(priority.get("slow") or 0)
    fact = str(priority.get("fact") or "this fact")
    concern = max(help_count, repeated)
    if class_size and concern >= max(5, int(class_size * 0.20)):
        return f"Give the whole class a 3-minute strategy/retrieval reminder on {fact}, then let adaptive practice do the rest."
    if concern >= 2:
        return f"Pull a short accuracy group for {fact}; this does not need a whole-class lesson yet."
    if slow >= 3:
        return f"Accuracy on {fact} looks fairly stable; use a brief retrieval/speed routine rather than reteaching the concept."
    return f"Keep {fact} in adaptive practice and watch for one more independent miss before intervening."


def suggested_small_groups(signals: Sequence[StudentSignal], full_by_student: Mapping[str, Mapping[tuple[int, int], MasterySnapshot]], *, limit: int = 5) -> list[dict]:
    by_id = {signal.student_id: signal for signal in signals}
    groups: list[dict] = []

    # Dynamic family groups: only surface a family if at least two students have
    # a genuine accuracy need somewhere in that family.
    family_students: dict[int, set[str]] = defaultdict(set)
    for sid, fact_map in full_by_student.items():
        for (a, b), snapshot in fact_map.items():
            if teacher_fact_band(snapshot) != BAND_HELP:
                continue
            family_students[a].add(str(sid))
            family_students[b].add(str(sid))
    ranked_families = [(family, ids) for family, ids in sorted(family_students.items(), key=lambda item: (-len(item[1]), item[0])) if len(ids) >= 2]
    if ranked_families:
        family, ids = ranked_families[0]
        merged_family = None
        merged_ids = set(ids)
        if len(ranked_families) > 1:
            family_two, ids_two = ranked_families[1]
            overlap = len(ids & ids_two) / max(1, min(len(ids), len(ids_two)))
            if overlap >= 0.75:
                merged_family = family_two
                merged_ids |= ids_two
        names = sorted((by_id[sid].nickname for sid in merged_ids if sid in by_id), key=str.casefold)
        label = f"Needs {family}s/{merged_family}s" if merged_family is not None else f"Needs {family}s"
        groups.append({"name": label, "reason": "Repeated accuracy needs in this fact family", "names": names[:8]})
        if merged_family is None and len(ranked_families) > 1:
            family_two, ids_two = ranked_families[1]
            names_two = sorted((by_id[sid].nickname for sid in ids_two if sid in by_id), key=str.casefold)
            groups.append({"name": f"Needs {family_two}s", "reason": "Repeated accuracy needs in this fact family", "names": names_two[:8]})

    accuracy_first = [s for s in signals if s.summary.needs_help >= 2 or len(s.repeated_misses) >= 2]
    accuracy_first.sort(key=lambda s: (-s.summary.needs_help, -len(s.repeated_misses), s.nickname.casefold()))
    if accuracy_first:
        groups.append({
            "name": "Accuracy First", "reason": "Multiple repeated misses; reteach before asking for speed",
            "names": [s.nickname for s in accuracy_first[:8]],
        })

    speed_ready = [s for s in signals if s.summary.needs_help == 0 and s.summary.slow >= 2]
    speed_ready.sort(key=lambda s: (-s.summary.slow, s.nickname.casefold()))
    if speed_ready:
        groups.append({
            "name": "Speed Ready", "reason": "Accurate retrieval is established; fluency is the next step",
            "names": [s.nickname for s in speed_ready[:8]],
        })

    nearly = [
        s for s in signals
        if s.summary.needs_help == 0 and 30 <= s.summary.known < 45 and s.summary.evidence_facts >= 35
    ]
    nearly.sort(key=lambda s: (-s.summary.known, s.summary.slow, s.nickname.casefold()))
    if nearly:
        groups.append({
            "name": "Nearly Fluent", "reason": "Strong overall map with a small number of facts still developing",
            "names": [s.nickname for s in nearly[:8]],
        })

    # De-duplicate exact group names and keep the teacher page intentionally short.
    seen = set(); output = []
    for group in groups:
        if group["name"] in seen or not group["names"]:
            continue
        seen.add(group["name"]); output.append(group)
    return output[:limit]


def progress_signals(signals: Sequence[StudentSignal], *, min_gain: float = 0.10) -> list[StudentSignal]:
    return sorted(
        [s for s in signals if s.accuracy_change is not None and s.accuracy_change >= min_gain],
        key=lambda s: (-(s.accuracy_change or 0.0), s.nickname.casefold()),
    )


def watch_signals(signals: Sequence[StudentSignal]) -> list[StudentSignal]:
    return sorted(
        [s for s in signals if s.repeated_misses or s.fragile_facts],
        key=lambda s: (-len(s.repeated_misses), -len(s.fragile_facts), s.nickname.casefold()),
    )


def weekly_recap(history: Sequence[Mapping], full_by_student: Mapping[str, Mapping[tuple[int, int], MasterySnapshot]], *, week_start: date, class_size: int) -> dict:
    week_end = week_start + timedelta(days=4)
    previous_start = week_start - timedelta(days=7)
    previous_end = previous_start + timedelta(days=4)
    attempts = [row for row in history if (d := _as_date(row.get("challenge_date"))) is not None and week_start <= d <= week_end]
    previous_attempts = [row for row in history if (d := _as_date(row.get("challenge_date"))) is not None and previous_start <= d <= previous_end]
    mult_answers = _multiplication_answers(history, start=week_start, end=week_end)
    prev_answers = _multiplication_answers(history, start=previous_start, end=previous_end)

    def acc(rows):
        return None if not rows else sum(bool(row.get("first_correct", row.get("correct"))) for row in rows) / len(rows)

    accuracy = acc(mult_answers)
    previous_accuracy = acc(prev_answers)
    trend = None if accuracy is None or previous_accuracy is None else accuracy - previous_accuracy
    mult_attempts = [row for row in attempts if str(row.get("daily_mode") or "Multiplication") == "Multiplication"]
    times = [float(row.get("timed_seconds") or 0.0) for row in mult_attempts if row.get("timed_seconds") is not None]

    miss_map: dict[tuple[int, int], dict] = {}
    for row in mult_answers:
        if bool(row.get("first_correct", row.get("correct"))):
            continue
        a, b = sorted((int(row.get("a") or 0), int(row.get("b") or 0)))
        item = miss_map.setdefault((a, b), {"fact": _fact_label(a, b), "misses": 0, "students": set()})
        item["misses"] += 1; item["students"].add(row["student_id"])
    common_misses = sorted(
        ({"fact": item["fact"], "misses": item["misses"], "students": len(item["students"])} for item in miss_map.values()),
        key=lambda item: (-item["students"], -item["misses"], item["fact"]),
    )[:5]

    # Progress is an exact comparison of independent Daily retrievals between
    # the chosen week and the preceding school week.
    progress = []
    student_ids = {str(row.get("student_id") or "") for row in attempts + previous_attempts}
    nickname_by_id = {str(row.get("student_id") or ""): str(row.get("nickname") or "") for row in history}
    for sid in student_ids:
        current_rows = [r for r in mult_answers if r["student_id"] == sid]
        old_rows = [r for r in prev_answers if r["student_id"] == sid]
        if len(current_rows) < 10 or len(old_rows) < 10:
            continue
        current_acc = acc(current_rows); old_acc = acc(old_rows)
        gain = (current_acc or 0.0) - (old_acc or 0.0)
        if gain >= 0.10:
            progress.append({"nickname": nickname_by_id.get(sid) or sid, "gain": gain, "accuracy": current_acc})
    progress.sort(key=lambda row: (-row["gain"], row["nickname"].casefold()))

    # This is intentionally labeled a signal rather than an exact historical
    # transition: the current mastery table does not keep past status snapshots.
    newly_secured = []
    for sid, fact_map in full_by_student.items():
        for snapshot in fact_map.values():
            practiced = snapshot.last_practiced_at.date() if snapshot.last_practiced_at else None
            if teacher_fact_band(snapshot) == BAND_KNOWN and practiced is not None and week_start <= practiced <= week_end and snapshot.evidence_count <= 7:
                newly_secured.append((sid, _fact_label(snapshot.a, snapshot.b)))

    modes: dict[str, int] = defaultdict(int)
    for row in attempts:
        modes[str(row.get("daily_mode") or "Multiplication")] += 1

    return {
        "week_start": week_start, "week_end": week_end,
        "daily_completions": len(attempts), "students_with_completion": len({str(row.get("student_id")) for row in attempts}),
        "class_size": class_size, "multiplication_attempts": len(mult_attempts),
        "multiplication_accuracy": accuracy, "accuracy_trend": trend,
        "median_multiplication_time": None if not times else float(median(times)),
        "common_misses": common_misses, "progress": progress[:8],
        "newly_secured_signal_count": len(newly_secured), "modes": dict(sorted(modes.items())),
    }


def student_recommendation(signal: StudentSignal) -> str:
    if signal.summary.needs_help:
        start = ", ".join(signal.summary.start_facts[:3]) or "the repeated misses"
        return f"Accuracy first: start with {start}. Keep the teaching brief, then let Focus Practice reinforce it."
    if signal.fragile_facts:
        return f"Recheck {', '.join(signal.fragile_facts[:3])}. These facts have strong older evidence but a recently broken correct streak."
    if signal.summary.slow >= 2:
        return "Accuracy looks stable. Use short retrieval practice rather than reteaching the multiplication strategy."
    if signal.summary.known >= 30:
        return "This student is close to broad fluency. Keep the normal Daily + Focus routine and target only the remaining developing facts."
    return "Keep gathering independent retrieval evidence; there is not enough stable data to justify an extra intervention yet."
