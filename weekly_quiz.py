from __future__ import annotations

"""Pure Quiz of the Week logic.

This module deliberately contains no Streamlit routing and no student PII.
Quiz records identify students only through the app's existing UUID; exports use
an irreversible, deterministic display key derived from that UUID.
"""

from datetime import date
import hashlib
import json
from typing import Mapping, Sequence

from curriculum_question_types import (
    COMMON_QUESTION_TYPES,
    clean_alternate_lines,
    clean_text,
    numeric_answers_match,
    numeric_value,
    text_answers_match,
)

QUIZ_QUESTION_COUNT = 5
QUIZ_QUESTION_TYPES = COMMON_QUESTION_TYPES
QUIZ_CATEGORIES = ("SUMM", "FORM")


# Backward-compatible aliases kept here because tests and callers already import
# these names from weekly_quiz. The implementations live in the shared
# curriculum_question_types module so Igniter and Friday Quiz grade the same.
_clean_text = clean_text

def _clean_lines(values, *, primary=""):
    return clean_alternate_lines(values, primary=primary)


def prepare_quiz_question(
    *,
    slot: int,
    prompt: str,
    question_type: str,
    correct_answer: str,
    options: Sequence[str] = (),
    accepted_answers: Sequence[str] = (),
    label_options: Sequence[str] = (),
    correct_label: str = "",
) -> dict:
    slot = int(slot)
    if not 1 <= slot <= QUIZ_QUESTION_COUNT:
        raise ValueError(f"Quiz slot must be 1 through {QUIZ_QUESTION_COUNT}.")
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError(f"Question {slot} needs a prompt.")
    qtype = str(question_type or "").strip()
    if qtype not in QUIZ_QUESTION_TYPES:
        raise ValueError(f"Question {slot} has an unsupported answer type.")
    correct = str(correct_answer or "").strip()
    if not correct:
        raise ValueError(f"Question {slot} needs a correct answer.")

    cleaned_options = [str(item).strip() for item in options if str(item).strip()]
    cleaned_labels = [str(item).strip() for item in label_options if str(item).strip()]
    label = str(correct_label or "").strip()

    if qtype in {"Number", "Fraction", "Number + Label"}:
        if numeric_value(correct) is None:
            raise ValueError(f"Question {slot}'s correct answer must be a valid number or fraction.")
    if qtype == "Multiple choice":
        if len(cleaned_options) < 2:
            raise ValueError(f"Question {slot} needs at least two multiple-choice options.")
        if correct not in cleaned_options:
            raise ValueError(f"Question {slot}'s correct answer must appear in its choices.")
    else:
        cleaned_options = []
    if qtype == "Number + Label":
        if len(cleaned_labels) < 2:
            raise ValueError(f"Question {slot} needs at least two label choices.")
        if not label or label not in cleaned_labels:
            raise ValueError(f"Question {slot}'s correct label must appear in its label choices.")
    else:
        cleaned_labels = []
        label = ""

    return {
        "slot": slot,
        "prompt": prompt,
        "question_type": qtype,
        "correct_answer": correct,
        "accepted_answers": _clean_lines(accepted_answers, primary=correct),
        "options": cleaned_options,
        "label_options": cleaned_labels,
        "correct_label": label,
    }


def validate_quiz_questions(questions: Sequence[Mapping]) -> tuple[dict, ...]:
    if len(list(questions)) != QUIZ_QUESTION_COUNT:
        raise ValueError(f"Quiz of the Week must contain exactly {QUIZ_QUESTION_COUNT} questions.")
    prepared = []
    for index, raw in enumerate(questions, start=1):
        raw = dict(raw or {})
        prepared.append(prepare_quiz_question(
            slot=index,
            prompt=raw.get("prompt", ""),
            question_type=raw.get("question_type", "Number"),
            correct_answer=raw.get("correct_answer", ""),
            options=raw.get("options") or (),
            accepted_answers=raw.get("accepted_answers") or (),
            label_options=raw.get("label_options") or (),
            correct_label=raw.get("correct_label", ""),
        ))
    return tuple(prepared)


def question_for_slot(quiz_record, slot: int) -> dict:
    slot = int(slot)
    questions = tuple(getattr(quiz_record, "questions", ()) or ())
    if not 1 <= slot <= len(questions):
        raise IndexError("Quiz question slot is out of range.")
    return dict(questions[slot - 1])


def grade_quiz_response(question: Mapping, student_answer: str, student_label: str = "") -> dict:
    qtype = str(question.get("question_type") or "Number")
    correct_answer = str(question.get("correct_answer") or "")
    alternates = tuple(question.get("accepted_answers") or ())

    if qtype == "Multiple choice":
        number_correct = text_answers_match(student_answer, correct_answer, alternates)
        label_correct = True
    else:
        number_correct = numeric_answers_match(student_answer, correct_answer, alternates)
        if qtype == "Number + Label":
            label_correct = _clean_text(student_label) == _clean_text(question.get("correct_label") or "")
        else:
            label_correct = True

    return {
        "correct": bool(number_correct and label_correct),
        "number_correct": bool(number_correct),
        "label_correct": bool(label_correct),
    }


def pack_response(answer: str, label: str = "") -> str:
    return json.dumps({"answer": str(answer or ""), "label": str(label or "")}, ensure_ascii=False, separators=(",", ":"))


def unpack_response(value: str) -> tuple[str, str]:
    try:
        parsed = json.loads(str(value or ""))
        if isinstance(parsed, dict):
            return str(parsed.get("answer") or ""), str(parsed.get("label") or "")
    except Exception:
        pass
    return str(value or ""), ""


def student_export_key(student_id: str) -> str:
    """Stable, meaningless local-bridge key. No names or roster data are involved."""
    digest = hashlib.sha256(str(student_id or "").encode("utf-8")).hexdigest().upper()
    return f"QW-{digest[:12]}"


def skyward_score(correct_count: int, max_score: float, *, question_count: int = QUIZ_QUESTION_COUNT):
    correct_count = max(0, min(int(correct_count), int(question_count)))
    max_score = float(max_score)
    value = (correct_count / float(question_count)) * max_score
    rounded = round(value + 1e-12, 2)
    return int(rounded) if float(rounded).is_integer() else rounded


def quiz_is_friday(day: date) -> bool:
    return day.weekday() == 4
