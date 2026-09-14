from __future__ import annotations

"""Shared grading primitives for curriculum questions.

Igniter and Quiz of the Week intentionally share these exact comparison rules
for Number, Fraction, Multiple choice, and Number + Label questions. Keeping
these helpers in one module prevents the two teacher/student workflows from
quietly drifting apart again.
"""

from fractions import Fraction
import re
from typing import Sequence

COMMON_QUESTION_TYPES = (
    "Number",
    "Fraction",
    "Multiple choice",
    "Number + Label",
)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def numeric_value(value: str) -> Fraction | None:
    """Parse whole numbers, decimals, fractions, and mixed numbers exactly."""
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    text = re.sub(r"\s*/\s*", "/", text)
    mixed = re.fullmatch(r"([+-]?\d+)\s+(\d+)\/(\d+)", text)
    if mixed:
        whole = int(mixed.group(1))
        numerator = int(mixed.group(2))
        denominator = int(mixed.group(3))
        if denominator == 0:
            return None
        frac = Fraction(numerator, denominator)
        return Fraction(whole, 1) - frac if whole < 0 else Fraction(whole, 1) + frac
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


def numeric_answers_match(
    student_answer: str,
    correct_answer: str,
    accepted_answers: Sequence[str] = (),
) -> bool:
    student = numeric_value(student_answer)
    if student is None:
        return False
    for candidate in [str(correct_answer or "")] + [str(item or "") for item in accepted_answers]:
        parsed = numeric_value(candidate)
        if parsed is not None and parsed == student:
            return True
    return False


def text_answers_match(
    student_answer: str,
    correct_answer: str,
    accepted_answers: Sequence[str] = (),
) -> bool:
    student = clean_text(student_answer)
    if not student:
        return False
    candidates = [correct_answer, *accepted_answers]
    return any(student == clean_text(candidate) for candidate in candidates if clean_text(candidate))


def clean_alternate_lines(values: Sequence[str], *, primary: str = "") -> list[str]:
    seen = {clean_text(primary)} if primary else set()
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        key = clean_text(value)
        if value and key and key not in seen:
            result.append(value)
            seen.add(key)
    return result
