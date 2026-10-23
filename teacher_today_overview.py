from __future__ import annotations

"""Read-only, teacher-facing lesson completion and reteaching summaries.

Today tracks the required Igniter/Friday Quiz, not Daily 10 leaderboard work.
Only active, non-test roster students count; unfinished work is never a miss.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from standards_recovery import (
    combine_standards_evidence,
    mastery_evidence_status,
    question_standard_metadata,
)
from weekly_quiz import QUIZ_QUESTION_COUNT, quiz_is_friday


@dataclass
class TodayLesson:
    class_record: Any
    students: list
    kind: str = "None"
    assignment: Any = None
    question_count: int = 0
    rows: list = field(default_factory=list)
    completed_ids: set[str] = field(default_factory=set)
    error: bool = False

    @property
    def total(self) -> int:
        return len(self.students)

    @property
    def complete(self) -> int | None:
        if self.error or self.assignment is None:
            return None
        return len(self.completed_ids)


def _real_rows(lesson: TodayLesson, records: list) -> None:
    active = {str(student.student_id) for student in lesson.students}
    assignment_id = str(
        lesson.assignment.quiz_id if lesson.kind == "Quiz" else lesson.assignment.warmup_set_id
    )
    assignment_key = "quiz_id" if lesson.kind == "Quiz" else "warmup_set_id"
    lesson.rows = [
        row for row in records
        if str(row.class_id) == str(lesson.class_record.class_id)
        and str(row.student_id) in active
        and str(getattr(row, assignment_key, "")) == assignment_id
        and 1 <= int(row.question_slot) <= lesson.question_count
    ]
    by_student: dict[str, set[int]] = defaultdict(set)
    for row in lesson.rows:
        by_student[str(row.student_id)].add(int(row.question_slot))
    lesson.completed_ids = {
        sid for sid, slots in by_student.items()
        if len(slots) == lesson.question_count
    }


def load_today_lessons(store, day: date, classes: list) -> list[TodayLesson]:
    """Bounded classroom reads; one answer read for all Igniters and one for quizzes."""
    ids = [str(item.class_id) for item in classes]
    loader = getattr(store, "list_students_for_classes", None)
    if callable(loader):
        rosters = loader(ids)
    else:
        rosters = {cid: store.list_students(cid) for cid in ids}
    lessons = [TodayLesson(record, list(rosters.get(str(record.class_id), []))) for record in classes]

    for lesson in lessons:
        cid = str(lesson.class_record.class_id)
        try:
            if quiz_is_friday(day):
                quiz = store.get_weekly_quiz_set(cid, day)
                if quiz is not None:
                    lesson.kind, lesson.assignment, lesson.question_count = "Quiz", quiz, QUIZ_QUESTION_COUNT
                    continue
            warmup = store.get_warmup_set(cid, day)
            if warmup is not None:
                lesson.kind, lesson.assignment, lesson.question_count = "Igniter", warmup, 2
        except Exception:
            # On Friday a failed quiz lookup must not masquerade as an Igniter day.
            lesson.error = True

    for kind, method in (("Igniter", "list_warmup_answers"), ("Quiz", "list_weekly_quiz_answers_range")):
        group = [lesson for lesson in lessons if lesson.kind == kind and not lesson.error]
        if not group:
            continue
        try:
            rows = getattr(store, method)(day, day)
        except Exception:
            for lesson in group:
                lesson.error = True
            continue
        for lesson in group:
            _real_rows(lesson, rows)
    return lessons


def today_reteach(lesson: TodayLesson) -> list[dict]:
    """One row per tagged standard, using incorrect *completed* assignments only."""
    if lesson.error or lesson.assignment is None:
        return []
    students = {str(row.student_id): row.nickname for row in lesson.students}
    groups: dict[str, dict] = {}
    for answer in lesson.rows:
        sid = str(answer.student_id)
        if sid not in lesson.completed_ids or bool(answer.correct):
            continue
        if lesson.kind == "Quiz":
            questions = tuple(getattr(lesson.assignment, "questions", ()) or ())
            slot = int(answer.question_slot)
            if not 1 <= slot <= len(questions):
                continue
            code, desc = question_standard_metadata(questions[slot - 1])
        else:
            code = str(getattr(answer, "standard_code", "") or "").strip()
            desc = str(getattr(answer, "standard_description", "") or "").strip()
        if not code:
            continue
        group = groups.setdefault(code, {"code": code, "description": desc, "names": set()})
        if not group["description"]:
            group["description"] = desc
        group["names"].add(students[sid])
    return [
        {"code": row["code"], "description": row["description"],
         "names": sorted(row["names"], key=str.casefold)}
        for row in sorted(groups.values(), key=lambda row: (-len(row["names"]), row["code"]))
    ]


def recent_mastery_checkins(store, lesson: TodayLesson, day: date, *, limit: int = 3) -> list[dict]:
    """Conservative, labeled fallback based on repeated independent past misses.

    Uses the same combined Igniter/Quiz/Recovery evidence as the Mastery Tracker.
    A single wrong answer never creates a historical 'needs help' recommendation.
    """
    end = day - timedelta(days=1)
    # Match Learning > Standards Mastery Tracker's school-year evidence window.
    year = day.year if day.month >= 8 else day.year - 1
    start = date(year, 8, 1)
    cid = str(lesson.class_record.class_id)
    if not lesson.students:
        return []
    warmups = store.list_warmup_answers(start, end, class_id=cid)
    quizzes = store.list_weekly_quiz_sets(start, end, class_id=cid)
    quiz_answers = store.list_weekly_quiz_answers_range(start, end, class_id=cid)
    try:
        recoveries = store.list_standard_recovery_answers(start, end, class_id=cid)
    except Exception:
        recoveries = []
    evidence = combine_standards_evidence(
        warmup_rows=warmups, quiz_sets=quizzes, quiz_answers=quiz_answers,
        recovery_rows=recoveries,
    )
    active = {str(student.student_id): student.nickname for student in lesson.students}
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for row in evidence:
        sid = str(row.student_id)
        if sid in active:
            grouped[(str(row.standard_code), sid)].append(row)
    recommendations: dict[str, dict] = {}
    for (code, sid), checks in grouped.items():
        missed_dates = {row.activity_date for row in checks if not row.correct}
        if len(missed_dates) < 2 or mastery_evidence_status(checks) != "Developing":
            continue
        latest = max(checks, key=lambda row: (row.activity_date, row.answered_at))
        entry = recommendations.setdefault(
            code, {"code": code, "description": latest.standard_description,
                   "names": set(), "misses": 0, "last": ""},
        )
        entry["names"].add(active[sid])
        entry["misses"] += len(missed_dates)
        entry["last"] = max(entry["last"], str(latest.activity_date))
    ranked = sorted(
        recommendations.values(),
        key=lambda row: (-len(row["names"]), -row["misses"], row["last"], row["code"]),
    )
    return [
        {"code": row["code"], "description": row["description"],
         "names": sorted(row["names"], key=str.casefold)}
        for row in ranked[:limit]
    ]
