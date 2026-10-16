from __future__ import annotations

"""Shared grading primitives for curriculum questions.

Igniter, Quiz of the Week, and Monday Recovery intentionally share these exact
comparison rules. Keeping the helpers in one module prevents the student flows
from quietly drifting apart when a new curriculum interaction is added.
"""

from collections import Counter
from fractions import Fraction
import hashlib
import json
import random
import re
import unicodedata
from typing import Sequence

COMPARE_QUESTION_TYPE = "Compare Values"
ORDER_QUESTION_TYPE = "Order Tiles"
COMPARISON_SYMBOLS = ("<", "=", ">")
ORDER_DIRECTIONS = ("Least to greatest", "Greatest to least")

COMMON_QUESTION_TYPES = (
    "Number",
    "Fraction",
    "Multiple choice",
    "Number + Label",
    COMPARE_QUESTION_TYPE,
    ORDER_QUESTION_TYPE,
)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def numeric_value(value: str) -> Fraction | None:
    """Parse whole numbers, decimals, fractions, and mixed numbers exactly."""
    text = str(value if value is not None else "").strip()
    if not text or len(text) > 200:
        return None
    text = text.translate(str.maketrans({"−": "-", "–": "-", "﹣": "-", "－": "-", "⁄": "/", "∕": "/"}))
    text = re.sub(r"^([+-])\s+(?=\d|[¼-¾⅐-⅞])", r"\1", text)
    # Pasted iPad fraction glyphs are single values; separate the whole part
    # before expansion so 2½ becomes 2 1/2, never 21/2.
    glyph = re.fullmatch(r"([+-]?)(\d*)\s*([¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞])", text)
    if glyph:
        fraction = unicodedata.normalize("NFKC", glyph.group(3)).replace("⁄", "/")
        text = glyph.group(1) + (glyph.group(2) + " " if glyph.group(2) else "") + fraction
    # Only valid thousands grouping may be removed. "1,5" must not become 15.
    if "," in text:
        if not re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
            return None
        text = text.replace(",", "")
    text = re.sub(r"\s*/\s*", "/", text)
    mixed = re.fullmatch(r"([+-]?\d+)\s+(\d+)\/(\d+)", text)
    if mixed:
        whole = int(mixed.group(1))
        numerator = int(mixed.group(2))
        denominator = int(mixed.group(3))
        if denominator == 0:
            return None
        frac = Fraction(numerator, denominator)
        magnitude = Fraction(abs(whole), 1) + frac
        return -magnitude if mixed.group(1).startswith("-") else magnitude
    # Fraction accepts scientific notation; bound exponents before parsing to
    # keep a mistyped answer from allocating an enormous integer on the server.
    exponent = re.search(r"[eE]([+-]?\d+)$", text)
    if exponent and abs(int(exponent.group(1))) > 100:
        return None
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


def comparison_symbol(left: str, right: str) -> str | None:
    """Return <, =, or > using exact rational arithmetic."""
    left_value = numeric_value(left)
    right_value = numeric_value(right)
    if left_value is None or right_value is None:
        return None
    if left_value < right_value:
        return "<"
    if left_value > right_value:
        return ">"
    return "="


def comparison_answer_matches(student_answer: str, left: str, right: str) -> bool:
    correct = comparison_symbol(left, right)
    return correct is not None and str(student_answer or "").strip() == correct


def normalize_order_direction(value: str) -> str:
    text = clean_text(value)
    if text in {"least to greatest", "ascending", "least", "low to high"}:
        return "Least to greatest"
    if text in {"greatest to least", "descending", "greatest", "high to low"}:
        return "Greatest to least"
    return ""


def validate_order_items(values: Sequence[str]) -> list[str]:
    """Return cleaned 3–6 numeric tiles or raise ValueError."""
    items = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not 3 <= len(items) <= 6:
        raise ValueError("Order Tiles questions need 3 to 6 number tiles.")
    if len(set(items)) != len(items):
        raise ValueError("Order Tiles should use distinct tile labels. Equivalent values such as 0.5 and 0.50 are okay.")
    parsed = [numeric_value(item) for item in items]
    if any(value is None for value in parsed):
        raise ValueError("Every Order Tile must be a valid whole number, decimal, fraction, or mixed number.")
    if len(set(parsed)) < 2:
        raise ValueError("Order Tiles needs at least two different numerical values.")
    return items


def sorted_order_items(values: Sequence[str], direction: str) -> list[str]:
    items = validate_order_items(values)
    normalized = normalize_order_direction(direction)
    if not normalized:
        raise ValueError("Choose least to greatest or greatest to least.")
    reverse = normalized == "Greatest to least"
    # Python's sort is stable, so numerically equivalent tiles retain teacher
    # order in the canonical answer while grading accepts either equivalent order.
    return sorted(items, key=lambda item: numeric_value(item), reverse=reverse)


def pack_order_response(values: Sequence[str]) -> str:
    return json.dumps([str(value or "").strip() for value in values], ensure_ascii=False, separators=(",", ":"))


def unpack_order_response(value: str) -> list[str]:
    try:
        parsed = json.loads(str(value or ""))
        if isinstance(parsed, list):
            return [str(item or "").strip() for item in parsed]
    except Exception:
        pass
    return []


def order_response_matches(student_answer: str, expected_items: Sequence[str], direction: str) -> bool:
    try:
        expected = validate_order_items(expected_items)
    except ValueError:
        return False
    submitted = unpack_order_response(student_answer)
    if len(submitted) != len(expected):
        return False
    if Counter(clean_text(item) for item in submitted) != Counter(clean_text(item) for item in expected):
        return False
    values = [numeric_value(item) for item in submitted]
    if any(value is None for value in values):
        return False
    normalized = normalize_order_direction(direction)
    if normalized == "Least to greatest":
        return all(values[index] <= values[index + 1] for index in range(len(values) - 1))
    if normalized == "Greatest to least":
        return all(values[index] >= values[index + 1] for index in range(len(values) - 1))
    return False


def deterministic_start_order(values: Sequence[str], *, seed: str, direction: str) -> list[str]:
    """Create a stable shuffled starting order for one student/question.

    A student's tiles stay in the same initial arrangement across reruns. When
    possible, the starting arrangement is deliberately not already correct.
    """
    items = validate_order_items(values)
    digest = hashlib.sha256(str(seed or "").encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    shuffled = list(items)
    rng.shuffle(shuffled)
    if order_response_matches(pack_order_response(shuffled), items, direction) and len(shuffled) > 1:
        shuffled = shuffled[1:] + shuffled[:1]
    return shuffled


def order_display(values: Sequence[str], direction: str) -> str:
    normalized = normalize_order_direction(direction)
    arrow = " ≤ " if normalized == "Least to greatest" else " ≥ "
    return arrow.join(str(value) for value in values)
