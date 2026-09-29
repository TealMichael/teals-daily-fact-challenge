from __future__ import annotations

"""Pure Monday standards-recovery planning and standards-evidence helpers.

Recovery uses only anonymous app IDs and the built-in Indiana Question Bank.
It does not contain student names, roster data, or external/AI calls.
"""

from dataclasses import dataclass
from datetime import date, timedelta, datetime
import hashlib
from typing import Iterable, Mapping, Sequence

from indiana_math_standards import BY_CODE as INDIANA_STANDARD_BY_CODE
from indiana_question_bank import editor_question, question_by_id, questions_for_standard
from weekly_quiz import QUIZ_QUESTION_COUNT

RECOVERY_MAX_QUESTIONS = 3
RECOVERY_GRADES = frozenset({5, 6, 7})


@dataclass(frozen=True)
class StandardsEvidenceRecord:
    student_id: str
    class_id: str
    activity_date: str
    standard_code: str
    standard_description: str
    source: str
    prompt: str
    correct: bool
    answered_at: datetime
    source_slot: int | None = None


def previous_friday_for_recovery(day: date) -> date | None:
    """Recovery is intentionally Monday-only and points to the prior Friday."""
    return day - timedelta(days=3) if day.weekday() == 0 else None


def question_standard_metadata(question: Mapping) -> tuple[str, str]:
    """Return a valid Grade 5–7 standard, inferring old bank-tagged quizzes."""
    raw = dict(question or {})
    code = str(raw.get("standard_code") or "").strip()
    description = str(raw.get("standard_description") or "").strip()

    if not code:
        bank_row = question_by_id(str(raw.get("bank_question_id") or ""))
        if bank_row is not None:
            code = str(bank_row.get("standard_code") or "").strip()
            description = str(bank_row.get("standard_description") or "").strip()

    standard = INDIANA_STANDARD_BY_CODE.get(code)
    if standard is None or int(standard.grade) not in RECOVERY_GRADES:
        return "", ""
    return standard.code, description or standard.description


def _stable_question_for_standard(
    code: str,
    *,
    student_id: str,
    source_quiz_id: str,
    recovery_date: date,
    exclude_ids: Iterable[str] = (),
) -> dict | None:
    excluded = {str(value or "").strip() for value in exclude_ids if str(value or "").strip()}
    candidates = [
        dict(row) for row in questions_for_standard(code)
        if str(row.get("id") or "") not in excluded
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda row: str(row.get("id") or ""))
    seed = f"{student_id}|{source_quiz_id}|{code}|{recovery_date.isoformat()}"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big", signed=False) % len(candidates)
    return candidates[index]


def build_recovery_plan(
    quiz,
    answers: Sequence,
    *,
    student_id: str,
    recovery_date: date,
    max_questions: int = RECOVERY_MAX_QUESTIONS,
) -> tuple[dict, ...]:
    """Build up to one new bank question per distinct missed Friday standard.

    A full five-question Friday quiz is required. Untagged questions do not
    create Recovery work. Distinct standards are kept in Friday quiz order.
    """
    answers_by_slot = {int(row.question_slot): row for row in answers}
    if len(answers_by_slot) < QUIZ_QUESTION_COUNT:
        return ()

    quiz_questions = tuple(getattr(quiz, "questions", ()) or ())
    if len(quiz_questions) < QUIZ_QUESTION_COUNT:
        return ()

    # Exclude every bank question the student saw Friday for each standard, not
    # only missed questions, so Recovery never repeats the exact Friday item.
    seen_bank_ids: dict[str, set[str]] = {}
    for question in quiz_questions:
        code, _ = question_standard_metadata(question)
        bank_id = str(dict(question).get("bank_question_id") or "").strip()
        if code and bank_id:
            seen_bank_ids.setdefault(code, set()).add(bank_id)

    missed_codes: list[tuple[str, str]] = []
    seen_codes: set[str] = set()
    for slot in range(1, QUIZ_QUESTION_COUNT + 1):
        answer = answers_by_slot.get(slot)
        if answer is None or bool(answer.correct):
            continue
        question = dict(quiz_questions[slot - 1])
        code, description = question_standard_metadata(question)
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        missed_codes.append((code, description))
        if len(missed_codes) >= max(0, int(max_questions)):
            break

    plan: list[dict] = []
    for code, description in missed_codes:
        bank_row = _stable_question_for_standard(
            code,
            student_id=str(student_id),
            source_quiz_id=str(getattr(quiz, "quiz_id", "")),
            recovery_date=recovery_date,
            exclude_ids=seen_bank_ids.get(code, ()),
        )
        if bank_row is None:
            continue
        question = editor_question(bank_row)
        plan.append({
            "standard_code": code,
            "standard_description": description,
            "bank_question_id": str(bank_row.get("id") or ""),
            "question": question,
        })
    return tuple(plan)


def mastery_evidence_status(rows: Sequence[StandardsEvidenceRecord]) -> str:
    """Conservative evidence label; never treats one Recovery answer as mastery."""
    ordered = sorted(rows, key=lambda row: (row.activity_date, row.answered_at))
    if not ordered:
        return "Not Yet Assessed"
    if len(ordered) < 3:
        return "Developing"
    accuracy = sum(bool(row.correct) for row in ordered) / len(ordered)
    recent_two = ordered[-2:]
    recent_three = ordered[-3:]
    if len(ordered) >= 5 and accuracy >= 0.85 and all(row.correct for row in recent_three):
        return "Strong"
    if accuracy >= 0.75 and all(row.correct for row in recent_two):
        return "Proficient"
    return "Developing"


def combine_standards_evidence(
    *,
    warmup_rows: Sequence,
    quiz_sets: Sequence,
    quiz_answers: Sequence,
    recovery_rows: Sequence,
) -> tuple[StandardsEvidenceRecord, ...]:
    """Normalize Igniter, Friday Quiz, and Recovery results for one tracker."""
    evidence: list[StandardsEvidenceRecord] = []

    for row in warmup_rows:
        code = str(getattr(row, "standard_code", "") or "").strip()
        standard = INDIANA_STANDARD_BY_CODE.get(code)
        if standard is None:
            continue
        evidence.append(StandardsEvidenceRecord(
            student_id=str(row.student_id), class_id=str(row.class_id), activity_date=str(row.warmup_date),
            standard_code=code,
            standard_description=str(getattr(row, "standard_description", "") or standard.description),
            source="Igniter", prompt=str(getattr(row, "prompt", "") or ""), correct=bool(row.correct),
            answered_at=row.answered_at, source_slot=int(row.question_slot),
        ))

    quiz_by_id = {str(row.quiz_id): row for row in quiz_sets}
    for row in quiz_answers:
        quiz = quiz_by_id.get(str(row.quiz_id))
        if quiz is None:
            continue
        questions = tuple(getattr(quiz, "questions", ()) or ())
        slot = int(row.question_slot)
        if not 1 <= slot <= len(questions):
            continue
        code, description = question_standard_metadata(questions[slot - 1])
        if not code:
            continue
        evidence.append(StandardsEvidenceRecord(
            student_id=str(row.student_id), class_id=str(row.class_id), activity_date=str(row.quiz_date),
            standard_code=code, standard_description=description, source="Quiz",
            prompt=str(getattr(row, "prompt", "") or ""), correct=bool(row.correct),
            answered_at=row.answered_at, source_slot=slot,
        ))

    for row in recovery_rows:
        code = str(getattr(row, "standard_code", "") or "").strip()
        standard = INDIANA_STANDARD_BY_CODE.get(code)
        if standard is None or int(standard.grade) not in RECOVERY_GRADES:
            continue
        evidence.append(StandardsEvidenceRecord(
            student_id=str(row.student_id), class_id=str(row.class_id), activity_date=str(row.recovery_date),
            standard_code=code,
            standard_description=str(getattr(row, "standard_description", "") or standard.description),
            source="Recovery", prompt=str(getattr(row, "prompt", "") or ""), correct=bool(row.correct),
            answered_at=row.answered_at, source_slot=None,
        ))

    return tuple(sorted(evidence, key=lambda row: (row.activity_date, row.answered_at, row.student_id, row.standard_code)))
