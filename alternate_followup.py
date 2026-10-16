from __future__ import annotations

"""Shared skill identity + validation helpers for alternate Daily follow-up.

This module intentionally does not import the multiplication mastery engine. Mixed
Daily questions may include multiplication, but their follow-up evidence stays in
alternate-learning storage so Mixed never changes the established multiplication
fluency profile.
"""

from dataclasses import dataclass
import re
from typing import Mapping, Sequence

ALT_DOMAINS = (
    "Multiplication",
    "Addition Facts",
    "Subtraction Facts",
    "Division Facts",
    "Integers",
)

ALT_MODES = (
    "Addition Facts",
    "Subtraction Facts",
    "Division Facts",
    "Integers",
    "Mixed",
)


@dataclass(frozen=True)
class SkillIdentity:
    domain: str
    skill_key: str
    skill_label: str
    item_key: str


def _normalize_prompt(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _signed(value: str) -> int:
    return int(str(value).replace("−", "-").strip())


def _sign_name(value: int) -> str:
    if value < 0:
        return "negative"
    if value > 0:
        return "positive"
    return "zero"


def _integer_skill_label(operation: str, a: int, b: int) -> str:
    left, right = _sign_name(a), _sign_name(b)
    if operation == "+":
        return f"Add a {right} integer to a {left} integer"
    if b < 0:
        return f"Subtract a negative integer from a {left} integer"
    return f"Subtract a {right} integer from a {left} integer"


def _question_domain(question: Mapping, default_domain: str | None = None) -> str:
    domain = str(question.get("category") or "").strip()
    if domain in ALT_DOMAINS:
        return domain
    kind = str(question.get("kind") or "").strip().casefold()
    aliases = {
        "multiplication": "Multiplication", "multiply": "Multiplication",
        "addition": "Addition Facts", "add": "Addition Facts",
        "subtraction": "Subtraction Facts", "subtract": "Subtraction Facts",
        "division": "Division Facts", "divide": "Division Facts",
        "integers": "Integers", "integer": "Integers",
    }
    if kind in aliases:
        return aliases[kind]
    default = str(default_domain or "").strip()
    if default in ALT_DOMAINS:
        return default
    raise ValueError(f"Unsupported alternate Daily question category: {domain!r}")


def skill_identity_for_question(question: Mapping, default_domain: str | None = None) -> SkillIdentity:
    """Return a stable skill identity for any stored alternate Daily question.

    Existing v2.13-v2.16 attempts store only prompt/category/correct_answer, so the
    parser deliberately supports those historical question dictionaries instead
    of requiring new generator metadata.
    """
    prompt = _normalize_prompt(question.get("prompt"))
    domain = _question_domain(question, default_domain)

    if domain == "Multiplication":
        match = re.fullmatch(r"\s*(-?\d+)\s*[×xX*]\s*(-?\d+)\s*", prompt)
        if not match:
            raise ValueError(f"Could not identify multiplication skill from {prompt!r}")
        a, b = int(match.group(1)), int(match.group(2))
        lo, hi = sorted((a, b))
        label = f"{lo} × {hi}"
        key = f"mul:{lo}x{hi}"
        return SkillIdentity(domain, key, label, key)

    if domain == "Addition Facts":
        match = re.fullmatch(r"\s*(\d+)\s*\+\s*(\d+)\s*", prompt)
        if not match:
            raise ValueError(f"Could not identify addition skill from {prompt!r}")
        a, b = int(match.group(1)), int(match.group(2))
        lo, hi = sorted((a, b))
        label = f"{lo} + {hi}"
        key = f"add:{lo}+{hi}"
        return SkillIdentity(domain, key, label, key)

    if domain == "Subtraction Facts":
        match = re.fullmatch(r"\s*(\d+)\s*[−-]\s*(\d+)\s*", prompt)
        if not match:
            raise ValueError(f"Could not identify subtraction skill from {prompt!r}")
        total, subtrahend = int(match.group(1)), int(match.group(2))
        label = f"{total} − {subtrahend}"
        key = f"sub:{total}-{subtrahend}"
        return SkillIdentity(domain, key, label, key)

    if domain == "Division Facts":
        match = re.fullmatch(r"\s*(\d+)\s*[÷/]\s*(\d+)\s*", prompt)
        if not match:
            raise ValueError(f"Could not identify division skill from {prompt!r}")
        dividend, divisor = int(match.group(1)), int(match.group(2))
        label = f"{dividend} ÷ {divisor}"
        key = f"div:{dividend}/{divisor}"
        return SkillIdentity(domain, key, label, key)

    # Integer prompts are generated as e.g. "-4 + 7", "5 − (-3)", "-2 + (-8)".
    match = re.fullmatch(r"\s*([−-]?\d+)\s*([+−-])\s*(?:\(([−-]?\d+)\)|([−-]?\d+))\s*", prompt)
    if not match:
        raise ValueError(f"Could not identify integer skill from {prompt!r}")
    a = _signed(match.group(1))
    operation = match.group(2)
    b = _signed(match.group(3) if match.group(3) is not None else match.group(4))
    op_key = "add" if operation == "+" else "sub"
    sign_key = f"{_sign_name(a)[0]}_{_sign_name(b)[0]}"
    skill_key = f"int:{op_key}:{sign_key}"
    normalized_op = "+" if operation == "+" else "-"
    item_key = f"int:{a}{normalized_op}{b}"
    return SkillIdentity(domain, skill_key, _integer_skill_label(operation, a, b), item_key)


def missed_question_items(questions: Sequence[Mapping], answers: Sequence[int], *, default_domain: str | None = None) -> list[dict]:
    if len(questions) != 10 or len(answers) != 10:
        raise ValueError("Alternate Daily follow-up requires all 10 stored questions and answers.")
    result: list[dict] = []
    for index, (question, answer) in enumerate(zip(questions, answers), start=1):
        correct_answer = int(question.get("correct_answer"))
        if int(answer) == correct_answer:
            continue
        skill = skill_identity_for_question(question, default_domain)
        result.append({
            "question_number": index,
            "prompt": _normalize_prompt(question.get("prompt")),
            "original_answer": int(answer),
            "correct_answer": correct_answer,
            "domain": skill.domain,
            "skill_key": skill.skill_key,
            "skill_label": skill.skill_label,
            "item_key": skill.item_key,
        })
    return result


def daily_evidence_rows(questions: Sequence[Mapping], answers: Sequence[int], *, default_domain: str | None = None) -> list[dict]:
    if len(questions) != 10 or len(answers) != 10:
        raise ValueError("Alternate Daily evidence requires all 10 stored questions and answers.")
    rows: list[dict] = []
    for index, (question, answer) in enumerate(zip(questions, answers), start=1):
        skill = skill_identity_for_question(question, default_domain)
        correct_answer = int(question.get("correct_answer"))
        rows.append({
            "question_number": index,
            "prompt": _normalize_prompt(question.get("prompt")),
            "student_answer": int(answer),
            "correct_answer": correct_answer,
            "correct": int(answer) == correct_answer,
            "domain": skill.domain,
            "skill_key": skill.skill_key,
            "skill_label": skill.skill_label,
            "item_key": skill.item_key,
        })
    return rows
