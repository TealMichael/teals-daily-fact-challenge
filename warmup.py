from __future__ import annotations

from fractions import Fraction
import json
import re
from typing import Mapping, Sequence

WARMUP_SLOTS = (
    (1, "🔁 Review Question", "Spiral Review"),
    (2, "📚 Yesterday's Question", "Yesterday Check"),
)
QUESTION_TYPES = (
    "Short answer",
    "Multiple choice",
    "Expanded Form",
    "Equivalent Number",
    "Multi-Part — 2 answers",
)


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


def _is_single_place_value_term(text: str) -> bool:
    """Return True when a term represents exactly one non-zero place-value digit."""
    raw = str(text or "").strip().replace(",", "")
    if not raw:
        return False
    # Whole-number terms: 60000, 3000, 400, 5.  A multi-digit chunk such as
    # 3405 is intentionally rejected because it is not fully expanded.
    if re.fullmatch(r"[+-]?\d+", raw):
        digits = raw.lstrip("+-")
        if not digits or int(digits) == 0:
            return False
        return sum(ch != "0" for ch in digits) == 1
    # Decimal place-value terms such as 0.3 or 0.04.  Keep the same one-digit
    # structure rule after removing the decimal point.
    if re.fullmatch(r"[+-]?(?:\d+\.\d+|\.\d+)", raw):
        digits = raw.lstrip("+-").replace(".", "")
        if not digits or int(digits) == 0:
            return False
        return sum(ch != "0" for ch in digits) == 1
    return False


def expanded_form_matches(student_answer: str, correct_answer: str) -> bool:
    """Grade actual expanded-form structure, not mere numeric equivalence."""
    target = _numeric_value(correct_answer)
    if target is None:
        return False
    raw = str(student_answer or "").strip()
    if "+" not in raw:
        return False
    terms = [term.strip() for term in raw.split("+")]
    if len(terms) < 2 or any(not term for term in terms):
        return False
    if any(not _is_single_place_value_term(term) for term in terms):
        return False
    values = [_numeric_value(term) for term in terms]
    if any(value is None for value in values):
        return False
    # Do not allow the same place-value contribution twice.  This keeps the
    # representation genuinely expanded rather than decomposed arbitrarily.
    if len(set(values)) != len(values):
        return False
    return sum(values, Fraction(0, 1)) == target


def pack_multi_part_response(first: str, second: str) -> str:
    return json.dumps([str(first or ""), str(second or "")], ensure_ascii=False, separators=(",", ":"))


def unpack_multi_part_response(value: str) -> tuple[str, str]:
    try:
        parsed = json.loads(str(value or ""))
        if isinstance(parsed, list) and len(parsed) == 2:
            return str(parsed[0]), str(parsed[1])
    except Exception:
        pass
    return str(value or ""), ""


def display_student_response(value: str, question_type: str) -> str:
    if str(question_type) == "Multi-Part — 2 answers":
        first, second = unpack_multi_part_response(value)
        return f"Part 1: {first} · Part 2: {second}"
    return str(value or "")


def grade_question(question: Mapping, student_answer: str, student_answer_two: str = "") -> bool:
    qtype = str(question.get("question_type") or "Short answer")
    correct = str(question.get("correct_answer") or "")
    alternates = question.get("accepted_answers") or ()
    if qtype == "Expanded Form":
        return expanded_form_matches(student_answer, correct)
    if qtype == "Multi-Part — 2 answers":
        correct_two = str(question.get("correct_answer_two") or "")
        alternates_two = question.get("accepted_answers_two") or ()
        return (
            answer_matches(student_answer, correct, alternates)
            and answer_matches(student_answer_two, correct_two, alternates_two)
        )
    # Equivalent Number is intentionally numeric-equivalence aware through the
    # same exact Fraction matcher used by Short answer.  No fuzzy text guessing.
    return answer_matches(student_answer, correct, alternates)


def correct_answer_for_storage(question: Mapping) -> str:
    if str(question.get("question_type") or "") == "Multi-Part — 2 answers":
        return pack_multi_part_response(
            str(question.get("correct_answer") or ""),
            str(question.get("correct_answer_two") or ""),
        )
    return str(question.get("correct_answer") or "")


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
    correct_answer_two: str = "",
    accepted_answers_two: Sequence[str] = (),
) -> dict:
    slot = int(slot)
    if slot not in (1, 2):
        raise ValueError("Warm-Up slot must be 1 or 2.")
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("Each Warm-Up question needs a prompt.")
    qtype = str(question_type or "").strip()
    if qtype not in QUESTION_TYPES:
        raise ValueError("Choose a supported Igniter answer type.")
    correct = str(correct_answer or "").strip()
    if not correct:
        raise ValueError("Each Warm-Up question needs a correct answer.")
    correct_two = str(correct_answer_two or "").strip()
    if qtype == "Multi-Part — 2 answers" and not correct_two:
        raise ValueError("Multi-Part questions need both correct answers.")
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

    def clean_alternates(values: Sequence[str], primary: str) -> list[str]:
        result = []
        seen = {_clean_text(primary)}
        for value in values:
            cleaned = str(value or "").strip()
            key = _clean_text(cleaned)
            if cleaned and key not in seen:
                result.append(cleaned)
                seen.add(key)
        return result

    alternates = clean_alternates(accepted_answers, correct)
    alternates_two = clean_alternates(accepted_answers_two, correct_two) if correct_two else []

    teacher_label = "Spiral Review" if slot == 1 else "Yesterday Check"
    student_label = "🔁 Review Question" if slot == 1 else "📚 Yesterday's Question"
    return {
        "slot": slot,
        "teacher_label": teacher_label,
        "student_label": student_label,
        "prompt": prompt,
        "question_type": qtype,
        "correct_answer": correct,
        "correct_answer_two": correct_two,
        "accepted_answers": alternates,
        "accepted_answers_two": alternates_two,
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
        correct_answer_two=value.get("correct_answer_two", ""),
        standard_code=value.get("standard_code", ""),
        standard_description=value.get("standard_description", ""),
        options=value.get("options") or (),
        accepted_answers=value.get("accepted_answers") or (),
        accepted_answers_two=value.get("accepted_answers_two") or (),
    )


def question_for_slot(record, slot: int) -> dict:
    """Return a defensive copy of one stored Igniter question."""
    return dict(record.question_one if int(slot) == 1 else record.question_two)
