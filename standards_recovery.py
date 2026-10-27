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
from standards_growth import growth_snapshot
from standards_tagging import reconcile_tag, normalize_prompt
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
    tag_disposition: str = "teacher_tagged"


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
        # The old planner could retain a bank ID after the prompt was freely
        # edited. Only infer a missing tag when the actual text still matches.
        if bank_row is not None and normalize_prompt(bank_row.get("prompt", "")) == normalize_prompt(raw.get("prompt", "")):
            code = str(bank_row.get("standard_code") or "").strip()
            description = str(bank_row.get("standard_description") or "").strip()

    decision = reconcile_tag(code, description, str(raw.get("prompt") or ""),
                             bank_question_id=str(raw.get("bank_question_id") or ""))
    standard = INDIANA_STANDARD_BY_CODE.get(decision.code)
    if standard is None or int(standard.grade) not in RECOVERY_GRADES:
        return "", ""
    return standard.code, decision.description or standard.description


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
    """Single source of truth for both teacher and student growth labels."""
    return growth_snapshot(rows).label


def combine_standards_evidence(
    *,
    warmup_rows: Sequence,
    quiz_sets: Sequence,
    quiz_answers: Sequence,
    recovery_rows: Sequence,
    quick_check_rows: Sequence = (),
) -> tuple[StandardsEvidenceRecord, ...]:
    """Normalize independent results, reconciling demonstrably bad tags read-only."""
    evidence: list[StandardsEvidenceRecord] = []

    for row in warmup_rows:
        code = str(getattr(row, "standard_code", "") or "").strip()
        decision = reconcile_tag(code, getattr(row, "standard_description", ""),
                                 getattr(row, "prompt", ""))
        standard = INDIANA_STANDARD_BY_CODE.get(decision.code)
        if standard is None:
            continue
        evidence.append(StandardsEvidenceRecord(
            student_id=str(row.student_id), class_id=str(row.class_id), activity_date=str(row.warmup_date),
            standard_code=decision.code,
            standard_description=decision.description or standard.description,
            source="Igniter", prompt=str(getattr(row, "prompt", "") or ""), correct=bool(row.correct),
            answered_at=row.answered_at, source_slot=int(row.question_slot), tag_disposition=decision.disposition,
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
        raw_question = dict(questions[slot - 1])
        code, description = question_standard_metadata(raw_question)
        decision = reconcile_tag(code, description, getattr(row, "prompt", "") or raw_question.get("prompt", ""))
        if not decision.code:
            continue
        evidence.append(StandardsEvidenceRecord(
            student_id=str(row.student_id), class_id=str(row.class_id), activity_date=str(row.quiz_date),
            standard_code=decision.code, standard_description=decision.description, source="Quiz",
            prompt=str(getattr(row, "prompt", "") or ""), correct=bool(row.correct),
            answered_at=row.answered_at, source_slot=slot, tag_disposition=decision.disposition,
        ))

    for row in recovery_rows:
        code = str(getattr(row, "standard_code", "") or "").strip()
        decision = reconcile_tag(code, getattr(row, "standard_description", ""),
                                 getattr(row, "prompt", ""))
        standard = INDIANA_STANDARD_BY_CODE.get(decision.code)
        if standard is None or int(standard.grade) not in RECOVERY_GRADES:
            continue
        evidence.append(StandardsEvidenceRecord(
            student_id=str(row.student_id), class_id=str(row.class_id), activity_date=str(row.recovery_date),
            standard_code=decision.code,
            standard_description=decision.description or standard.description,
            source="Recovery", prompt=str(getattr(row, "prompt", "") or ""), correct=bool(row.correct),
            answered_at=row.answered_at, source_slot=None, tag_disposition=decision.disposition,
        ))

    for row in quick_check_rows:
        get = (lambda name, default=None: row.get(name, default)) if isinstance(row, dict) else (
            lambda name, default=None: getattr(row, name, default))
        if get("completed_at") is None or get("correct") is None:
            continue
        decision = reconcile_tag(get("standard_code", ""), get("standard_description", ""),
                                 get("prompt", ""))
        if not decision.code:
            continue
        evidence.append(StandardsEvidenceRecord(
            student_id=str(get("student_id", "")), class_id=str(get("class_id", "")),
            activity_date=str(get("completed_date") or str(get("completed_at"))[:10]),
            standard_code=decision.code, standard_description=decision.description,
            source="Quick Check", prompt=str(get("prompt", "")), correct=bool(get("correct")),
            answered_at=get("completed_at"), source_slot=None,
            tag_disposition=decision.disposition,
        ))

    return tuple(sorted(evidence, key=lambda row: (row.activity_date, row.answered_at, row.student_id, row.standard_code)))
