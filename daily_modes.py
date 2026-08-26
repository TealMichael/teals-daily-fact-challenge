from __future__ import annotations

"""Deterministic alternate Daily 10 generators.

Multiplication remains owned by fact_engine.py and TDFC-DAILY-v1.  This module
only supplies the optional class/date Daily 10 modes introduced in v2.13.
"""

from datetime import date
import hashlib
import random
from typing import Mapping, Sequence

from fact_engine import daily_facts_for_date

DAILY_MODES = (
    "Multiplication",
    "Addition Facts",
    "Subtraction Facts",
    "Division Facts",
    "Integers",
    "Mixed",
)
ALT_DAILY_VERSION = "TDFC-ALT-v1"


def daily_mode_setting_key(day: date | str, class_id: str) -> str:
    day_key = day.isoformat() if isinstance(day, date) else str(day)
    return f"daily10_mode:{day_key}:{str(class_id)}"


def normalize_daily_mode(value: object) -> str:
    text = str(value or "Multiplication").strip()
    return text if text in DAILY_MODES else "Multiplication"


def configured_daily_mode(store, class_id: str, day: date | str) -> str:
    try:
        value = store.get_app_setting(daily_mode_setting_key(day, class_id))
        return normalize_daily_mode("Multiplication" if value is None else value)
    except Exception:
        return "Multiplication"


def _stable_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _rng(day: date, mode: str, salt: str = "") -> random.Random:
    return random.Random(_stable_seed(f"{ALT_DAILY_VERSION}:{day.isoformat()}:{mode}:{salt}"))


def _question(prompt: str, answer: int, category: str) -> dict:
    return {"prompt": str(prompt), "correct_answer": int(answer), "category": str(category)}


def _addition(day: date, count: int, salt: str = "") -> list[dict]:
    rng = _rng(day, "Addition Facts", salt)
    pairs = [(a, b) for a in range(0, 10) for b in range(a, 10)]
    rng.shuffle(pairs)
    chosen = pairs[:count]
    result = []
    for index, (a, b) in enumerate(chosen):
        if a != b and rng.random() < 0.5:
            a, b = b, a
        result.append(_question(f"{a} + {b}", a + b, "Addition Facts"))
    return result


def _subtraction(day: date, count: int, salt: str = "") -> list[dict]:
    rng = _rng(day, "Subtraction Facts", salt)
    families = [(a + b, a, b) for a in range(0, 10) for b in range(a, 10) if a + b <= 18]
    rng.shuffle(families)
    result = []
    for total, a, b in families[:count]:
        sub = a if rng.random() < 0.5 else b
        result.append(_question(f"{total} − {sub}", total - sub, "Subtraction Facts"))
    return result


def _division(day: date, count: int, salt: str = "") -> list[dict]:
    rng = _rng(day, "Division Facts", salt)
    facts = [(divisor, quotient) for divisor in range(2, 11) for quotient in range(2, 11)]
    rng.shuffle(facts)
    result = []
    seen = set()
    for divisor, quotient in facts:
        key = (divisor * quotient, divisor)
        if key in seen:
            continue
        seen.add(key)
        result.append(_question(f"{divisor * quotient} ÷ {divisor}", quotient, "Division Facts"))
        if len(result) >= count:
            break
    return result


def _integers(day: date, count: int, salt: str = "") -> list[dict]:
    rng = _rng(day, "Integers", salt)
    result = []
    seen = set()
    operations = (["+", "−"] * ((count + 1) // 2))[:count]
    rng.shuffle(operations)
    while len(result) < count:
        op = operations[len(result)]
        a = rng.randint(-9, 9)
        b = rng.randint(-9, 9)
        if op == "+":
            answer = a + b
            prompt = f"{a} + ({b})" if b < 0 else f"{a} + {b}"
        else:
            answer = a - b
            prompt = f"{a} − ({b})" if b < 0 else f"{a} − {b}"
        key = (prompt, answer)
        if key in seen:
            continue
        seen.add(key)
        result.append(_question(prompt, answer, "Integers"))
    return result


def questions_for_mode(day: date | str, mode: str) -> list[dict]:
    if isinstance(day, str):
        day = date.fromisoformat(day)
    mode = normalize_daily_mode(mode)
    if mode == "Multiplication":
        return [
            _question(f"{fact.a} × {fact.b}", fact.product, "Multiplication")
            for fact in daily_facts_for_date(day)
        ]
    if mode == "Addition Facts":
        result = _addition(day, 10)
    elif mode == "Subtraction Facts":
        result = _subtraction(day, 10)
    elif mode == "Division Facts":
        result = _division(day, 10)
    elif mode == "Integers":
        result = _integers(day, 10)
    elif mode == "Mixed":
        mult = [
            _question(f"{fact.a} × {fact.b}", fact.product, "Multiplication")
            for fact in daily_facts_for_date(day)[:2]
        ]
        result = (
            mult
            + _addition(day, 2, "mixed")
            + _subtraction(day, 2, "mixed")
            + _division(day, 2, "mixed")
            + _integers(day, 2, "mixed")
        )
        rng = _rng(day, "Mixed", "order")
        rng.shuffle(result)
    else:  # normalize_daily_mode already protects this branch
        raise ValueError(f"Unsupported Daily 10 mode: {mode}")
    validate_alt_questions(result, mode)
    return result


def validate_alt_questions(questions: Sequence[Mapping], mode: str) -> None:
    if len(questions) != 10:
        raise ValueError("A Daily 10 must contain exactly 10 questions.")
    for item in questions:
        if not str(item.get("prompt") or "").strip():
            raise ValueError("Every Daily 10 question needs a prompt.")
        int(item.get("correct_answer"))
    if normalize_daily_mode(mode) == "Mixed":
        counts = {name: 0 for name in ("Multiplication", "Addition Facts", "Subtraction Facts", "Division Facts", "Integers")}
        for item in questions:
            category = str(item.get("category") or "")
            if category in counts:
                counts[category] += 1
        if any(value != 2 for value in counts.values()):
            raise ValueError("Mixed Daily 10 must contain exactly two questions of each type.")
