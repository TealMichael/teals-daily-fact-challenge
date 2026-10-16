from __future__ import annotations

"""Answer-only review helpers. No correct answers or student identities."""

from collections import Counter
from typing import Mapping

from curriculum_question_types import COMPARISON_SYMBOLS, ORDER_QUESTION_TYPE, unpack_order_response
from weekly_quiz import QUIZ_QUESTION_COUNT, question_for_slot, unpack_response


def review_responses(answers_by_slot: Mapping, drafts: Mapping) -> dict[int, tuple[str, str]]:
    result = {
        int(slot): unpack_response(row.student_response)
        for slot, row in answers_by_slot.items()
        if int(slot) in range(1, QUIZ_QUESTION_COUNT + 1)
    }
    for slot, value in drafts.items():
        if int(slot) in range(1, QUIZ_QUESTION_COUNT + 1):
            result[int(slot)] = unpack_response(value)
    return result


def response_complete(question: Mapping, answer: str, label: str = "") -> bool:
    """Check presence/shape only; never tell students whether an answer is right."""
    if not str(answer or "").strip():
        return False
    qtype = question.get("question_type")
    if qtype == "Number + Label":
        return label in (question.get("label_options") or ())
    if qtype == "Multiple choice":
        return answer in (question.get("options") or ())
    if qtype == "Compare Values":
        return answer in COMPARISON_SYMBOLS
    if qtype == ORDER_QUESTION_TYPE:
        return Counter(unpack_order_response(answer)) == Counter(question.get("order_items") or ())
    return True


def missing_response_slots(quiz, responses: Mapping) -> list[int]:
    return [
        slot for slot in range(1, QUIZ_QUESTION_COUNT + 1)
        if not response_complete(question_for_slot(quiz, slot), *responses.get(slot, ("", "")))
    ]


def display_review_response(question: Mapping, answer: str, label: str = "") -> str:
    if question.get("question_type") == ORDER_QUESTION_TYPE:
        return " → ".join(unpack_order_response(answer)) or "No answer yet"
    if question.get("question_type") == "Number + Label":
        return f"{answer or 'No number yet'} · {label or 'No label yet'}"
    return str(answer or "No answer yet")


def pending_review_saves(quiz, responses: Mapping, answers_by_slot: Mapping) -> list[int]:
    """Save revised earlier items first; the fifth row is the completion marker."""
    if missing_response_slots(quiz, responses):
        raise ValueError("Answer all five questions before submitting.")
    return [
        slot for slot in range(1, QUIZ_QUESTION_COUNT + 1)
        if slot not in answers_by_slot
        or unpack_response(answers_by_slot[slot].student_response) != responses[slot]
    ]
