from __future__ import annotations

from fractions import Fraction
import re
from typing import Mapping, Sequence

WARMUP_SLOTS = (
    (1, "🔁 Review Question", "Spiral Review"),
    (2, "📚 Yesterday's Question", "Yesterday Check"),
)
QUESTION_TYPES = ("Short answer", "Multiple choice")


def _clean_text(value: str) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"\s+", " ", text)
    return text


def _numeric_value(value: str) -> Fraction | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


def answer_matches(student_answer: str, correct_answer: str, accepted_answers: Sequence[str] = ()) -> bool:
    """Conservative curriculum-answer matching.

    Numeric equivalents such as 14.40 / 14.4 and 1/2 / 0.5 match. Text
    answers ignore capitalization and repeated spaces. Accepted alternates are
    teacher-controlled; no fuzzy guessing is used for standards data.
    """
    candidates = [str(correct_answer or "")] + [str(value or "") for value in accepted_answers]
    student_numeric = _numeric_value(student_answer)
    for candidate in candidates:
        if student_numeric is not None:
            candidate_numeric = _numeric_value(candidate)
            if candidate_numeric is not None and student_numeric == candidate_numeric:
                return True
        if _clean_text(student_answer) == _clean_text(candidate) and _clean_text(candidate):
            return True
    return False


def prepare_question(
    *,
    slot: int,
    prompt: str,
    question_type: str,
    correct_answer: str,
    standard_code: str,
    standard_description: str = "",
    options: Sequence[str] = (),
    accepted_answers: Sequence[str] = (),
) -> dict:
    slot = int(slot)
    if slot not in (1, 2):
        raise ValueError("Warm-Up slot must be 1 or 2.")
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("Each Warm-Up question needs a prompt.")
    qtype = str(question_type or "").strip()
    if qtype not in QUESTION_TYPES:
        raise ValueError("Question type must be Short answer or Multiple choice.")
    correct = str(correct_answer or "").strip()
    if not correct:
        raise ValueError("Each Warm-Up question needs a correct answer.")
    standard = str(standard_code or "").strip()
    if not standard:
        raise ValueError("Attach an Indiana standard code to each Warm-Up question.")

    cleaned_options = [str(value).strip() for value in options if str(value).strip()]
    if qtype == "Multiple choice":
        if len(cleaned_options) < 2:
            raise ValueError("Multiple-choice questions need at least two choices.")
        if correct not in cleaned_options:
            raise ValueError("The correct answer must appear in the multiple-choice options.")
    else:
        cleaned_options = []

    alternates = []
    seen = {_clean_text(correct)}
    for value in accepted_answers:
        cleaned = str(value or "").strip()
        key = _clean_text(cleaned)
        if cleaned and key not in seen:
            alternates.append(cleaned)
            seen.add(key)

    teacher_label = "Spiral Review" if slot == 1 else "Yesterday Check"
    student_label = "🔁 Review Question" if slot == 1 else "📚 Yesterday's Question"
    return {
        "slot": slot,
        "teacher_label": teacher_label,
        "student_label": student_label,
        "prompt": prompt,
        "question_type": qtype,
        "correct_answer": correct,
        "accepted_answers": alternates,
        "options": cleaned_options,
        "standard_code": standard,
        "standard_description": str(standard_description or "").strip(),
    }


def question_from_mapping(value: Mapping | None, slot: int) -> dict:
    value = dict(value or {})
    return prepare_question(
        slot=slot,
        prompt=value.get("prompt", ""),
        question_type=value.get("question_type", "Short answer"),
        correct_answer=value.get("correct_answer", ""),
        standard_code=value.get("standard_code", ""),
        standard_description=value.get("standard_description", ""),
        options=value.get("options") or (),
        accepted_answers=value.get("accepted_answers") or (),
    )
