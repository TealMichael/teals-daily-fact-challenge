from __future__ import annotations

"""Built-in Indiana Standards Question Bank for Grades 5–7.

The bank is static application content: it contains no student data, makes no
network calls, and does not use Supabase. Questions are copied into the normal
Igniter / Quiz editors before a teacher saves them.
"""

from functools import lru_cache
import json
from pathlib import Path
import random
from typing import Iterable, Mapping

from indiana_math_standards import BY_CODE, ESSENTIAL_CODES, is_essential_standard

BANK_FILE = Path(__file__).with_name("indiana_question_bank.json")
BANK_ASSET_DIR = Path(__file__).with_name("question_bank_assets")
SUPPORTED_BANK_TYPES = frozenset({"Number", "Fraction", "Multiple choice", "Number + Label"})
BANK_GRADES = (5, 6, 7)
QUESTIONS_PER_STANDARD = 10
EXPECTED_STANDARD_COUNT = 75
EXPECTED_QUESTION_COUNT = 750


@lru_cache(maxsize=1)
def all_questions() -> tuple[dict, ...]:
    with BANK_FILE.open("r", encoding="utf-8") as handle:
        rows = json.load(handle)
    return tuple(dict(row) for row in rows)


def questions_for_standard(code: str) -> tuple[dict, ...]:
    code = str(code or "").strip()
    return tuple(row for row in all_questions() if row.get("standard_code") == code)


def questions_for_grade(grade: int) -> tuple[dict, ...]:
    grade = int(grade)
    return tuple(row for row in all_questions() if int(row.get("grade") or 0) == grade)


def domains_for_grade(grade: int) -> tuple[str, ...]:
    seen: list[str] = []
    for row in questions_for_grade(grade):
        domain = str(row.get("domain") or "").strip()
        if domain and domain not in seen:
            seen.append(domain)
    return tuple(seen)


def standard_codes_for(grade: int, domain: str | None = None, *, essential_only: bool = False) -> tuple[str, ...]:
    domain = str(domain or "").strip()
    seen: list[str] = []
    for row in questions_for_grade(grade):
        code = str(row.get("standard_code") or "")
        if domain and str(row.get("domain") or "") != domain:
            continue
        if essential_only and not bool(row.get("essential")):
            continue
        if code and code not in seen:
            seen.append(code)
    return tuple(seen)


def question_by_id(question_id: str) -> dict | None:
    question_id = str(question_id or "").strip()
    for row in all_questions():
        if str(row.get("id") or "") == question_id:
            return dict(row)
    return None


def random_question(code: str, *, exclude_ids: Iterable[str] = ()) -> dict:
    excluded = {str(value) for value in exclude_ids}
    candidates = [row for row in questions_for_standard(code) if str(row.get("id")) not in excluded]
    if not candidates:
        candidates = list(questions_for_standard(code))
    if not candidates:
        raise KeyError(f"No built-in questions found for {code}.")
    return dict(random.SystemRandom().choice(candidates))


def editor_question(question: Mapping) -> dict:
    """Convert one bank row into the normal curriculum-question dictionary."""
    row = dict(question or {})
    return {
        "prompt": str(row.get("prompt") or ""),
        "question_type": str(row.get("question_type") or "Number"),
        "correct_answer": str(row.get("correct_answer") or ""),
        "correct_answer_two": "",
        "accepted_answers": list(row.get("accepted_answers") or ()),
        "accepted_answers_two": [],
        "options": list(row.get("options") or ()),
        "label_options": list(row.get("label_options") or ()),
        "correct_label": str(row.get("correct_label") or ""),
        "standard_code": str(row.get("standard_code") or ""),
        "standard_description": str(row.get("standard_description") or ""),
        "image_path": "",  # temporary teacher uploads remain separate
        "image_alt": str(row.get("bank_image_alt") or "Question diagram") or "Question diagram",
        "bank_image_path": sanitize_bank_image_path(row.get("bank_image_path") or ""),
        "bank_image_alt": str(row.get("bank_image_alt") or "Built-in question diagram") or "Built-in question diagram",
        "bank_question_id": str(row.get("id") or ""),
    }


def seed_editor_state(session_state, *, prefix: str, slot: int, question: Mapping, include_standard: bool) -> None:
    """Seed Streamlit widget state before the destination editor is rendered."""
    values = editor_question(question)
    slot = int(slot)
    state_values = {
        f"{prefix}_prompt_{slot}": values["prompt"],
        f"{prefix}_type_{slot}": values["question_type"],
        f"{prefix}_correct_{slot}": values["correct_answer"],
        f"{prefix}_correct_two_{slot}": "",
        f"{prefix}_options_{slot}": "\n".join(values["options"]),
        f"{prefix}_labels_{slot}": "\n".join(values["label_options"]),
        f"{prefix}_correct_label_{slot}": values["correct_label"],
        f"{prefix}_alternates_{slot}": "\n".join(values["accepted_answers"]),
        f"{prefix}_alternates_two_{slot}": "",
        f"{prefix}_image_alt_{slot}": values["image_alt"],
        f"{prefix}_bank_image_path_{slot}": values["bank_image_path"],
        f"{prefix}_bank_image_alt_{slot}": values["bank_image_alt"],
        f"{prefix}_bank_question_id_{slot}": values["bank_question_id"],
        f"{prefix}_clear_existing_image_once_{slot}": True,
    }
    if include_standard:
        code = values["standard_code"]
        if code in BY_CODE:
            state_values[f"{prefix}_standard_choice_{slot}"] = code
    for key, value in state_values.items():
        session_state[key] = value


def sanitize_bank_image_path(value: str) -> str:
    """Return a safe package-relative path or an empty string."""
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("/") or ".." in Path(raw).parts:
        return ""
    if not raw.startswith("question_bank_assets/"):
        return ""
    return raw


def resolve_bank_image_path(value: str) -> str:
    relative = sanitize_bank_image_path(value)
    if not relative:
        return ""
    candidate = (Path(__file__).parent / relative).resolve()
    root = BANK_ASSET_DIR.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return ""
    return str(candidate) if candidate.is_file() else ""


def bank_summary() -> dict:
    rows = all_questions()
    return {
        "questions": len(rows),
        "standards": len({row.get("standard_code") for row in rows}),
        "essential_standards": len(ESSENTIAL_CODES),
        "essential_questions": sum(bool(row.get("essential")) for row in rows),
    }


def standard_label(code: str) -> str:
    standard = BY_CODE.get(str(code or ""))
    if standard is None:
        return str(code or "")
    prefix = "★ Essential · " if is_essential_standard(standard.code) else ""
    return f"{prefix}{standard.code} — {standard.description}"
