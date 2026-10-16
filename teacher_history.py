from __future__ import annotations

"""Pure summary helpers for the teacher Class History view."""

from collections import Counter, defaultdict
from datetime import date


def daily_rows_for_date(history, target_date: date) -> list[dict]:
    key = target_date.isoformat()
    return [dict(row) for row in history if str(row.get("challenge_date") or "") == key]


def rank_daily(rows) -> list[dict]:
    ranked = sorted(
        rows,
        key=lambda row: (
            -int(row.get("correct_count") or 0),
            float(row.get("timed_seconds") if row.get("timed_seconds") is not None else 10**9),
            str(row.get("completed_at") or ""),
            str(row.get("nickname") or "").casefold(),
        ),
    )[:10]
    return [dict(row, rank=index) for index, row in enumerate(ranked, start=1)]


def common_multiplication_misses(rows, *, limit: int = 5) -> list[dict]:
    counts: Counter[tuple[int, int]] = Counter()
    names: dict[tuple[int, int], set[str]] = defaultdict(set)
    for row in rows:
        if str(row.get("daily_mode") or "Multiplication") != "Multiplication":
            continue
        nickname = str(row.get("nickname") or "Student")
        for answer in row.get("answers") or []:
            if bool(answer.get("first_correct", answer.get("correct"))):
                continue
            a = int(answer.get("a") or 0)
            b = int(answer.get("b") or 0)
            if not a or not b:
                continue
            key = tuple(sorted((a, b)))
            counts[key] += 1
            names[key].add(nickname)
    result = []
    for (a, b), count in counts.most_common(limit):
        result.append({
            "Fact": f"{a} × {b}",
            "Misses": count,
            "Students": ", ".join(sorted(names[(a, b)], key=str.casefold)),
        })
    return result


def warmup_summary(students, rows) -> dict:
    student_ids = {str(student.student_id) for student in students}
    rows = [row for row in rows if str(row.student_id) in student_ids]
    by_slot = {1: [], 2: []}
    completed_ids = set()
    for row in rows:
        completed_ids.add(str(row.student_id))
        by_slot.setdefault(int(row.question_slot), []).append(row)
    result = {"completed": len(completed_ids), "roster": len(student_ids), "slots": {}}
    for slot in (1, 2):
        slot_rows = by_slot.get(slot, [])
        result["slots"][slot] = {
            "responses": len(slot_rows),
            "correct": sum(bool(row.correct) for row in slot_rows),
            "incorrect_ids": [str(row.student_id) for row in slot_rows if not bool(row.correct)],
        }
    return result
