from __future__ import annotations

"""Conservative, non-destructive reconciliation of historical standard tags.

Never trust a stale bank ID after a teacher edits the prompt. Exact prompt
matches are safe to reclassify. A few unequivocal subject/code mismatches are
excluded from *calculated* mastery, with the stored answers left untouched.
Unknown custom questions retain their existing teacher-selected standards.
"""

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Mapping

from indiana_math_standards import BY_CODE
from indiana_question_bank import all_questions


@dataclass(frozen=True)
class TagDecision:
    code: str
    description: str
    disposition: str  # verified, corrected, excluded, teacher_tagged


def normalize_prompt(value: str) -> str:
    value = re.sub(r"(?:\*\*|__|`)", "", str(value or ""))
    return re.sub(r"\s+", " ", value).strip().casefold()


@lru_cache(maxsize=1)
def _exact_bank_index() -> dict[str, str]:
    mapping: dict[str, set[str]] = {}
    for row in all_questions():
        prompt = normalize_prompt(row.get("prompt", ""))
        code = str(row.get("standard_code") or "")
        if prompt and code:
            mapping.setdefault(prompt, set()).add(code)
    return {prompt: next(iter(codes)) for prompt, codes in mapping.items()
            if len(codes) == 1}


def reconcile_tag(code: str, description: str, prompt: str,
                  *, bank_question_id: str = "") -> TagDecision:
    code = str(code or "").strip()
    standard = BY_CODE.get(code)
    if standard is None:
        return TagDecision("", "", "excluded")
    normal = normalize_prompt(prompt)
    matching_code = _exact_bank_index().get(normal)
    if matching_code and matching_code in BY_CODE:
        correct_standard = BY_CODE[matching_code]
        if matching_code != code:
            return TagDecision(matching_code, correct_standard.description, "corrected")
        return TagDecision(code, standard.description, "verified")

    # A bank_question_id can be stale after free-text editing, so it is never
    # enough to reclassify a question without a matching current prompt.
    # These patterns identify *contradictions*, not a replacement standard.
    if code == "5.CA.2" and (
        re.search(r"\b(volume|prism|expanded form)\b", normal)
        or re.search(r"\bvalue of (the )?digit\b", normal)
        or re.fullmatch(r"\d[\d,]*\s*[×x*]\s*\d[\d,]*\s*=\s*", normal)
    ):
        return TagDecision("", "", "excluded")
    if code.startswith("5.CA.") and re.search(r"\b(volume of|find the volume|rectangular prism)\b", normal):
        return TagDecision("", "", "excluded")
    return TagDecision(code, description or standard.description, "teacher_tagged")


def reconcile_question(question: Mapping) -> TagDecision:
    return reconcile_tag(
        question.get("standard_code", ""), question.get("standard_description", ""),
        question.get("prompt", ""), bank_question_id=question.get("bank_question_id", ""),
    )
