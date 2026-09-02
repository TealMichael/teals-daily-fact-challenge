from __future__ import annotations

"""Adaptive Focus Practice planning for alternate Daily 10 modes.

This module deliberately does not import the multiplication adaptive/mastery engine.
Multiplication remains the gold-standard implementation and source of truth.  Mixed
multiplication items may be practiced here, but all evidence stays in the isolated
alternate-learning stream created in v2.17.
"""

from dataclasses import dataclass
import hashlib
from typing import Iterable, Mapping, Sequence

from alternate_followup import ALT_DOMAINS, ALT_MODES, daily_evidence_rows, skill_identity_for_question

ALT_FOCUS_SESSION_LENGTH = 8


@dataclass(frozen=True)
class AlternateFocusTarget:
    question: dict
    score: float
    reason: str


def _stable_rank(seed: str, item_key: str) -> int:
    digest = hashlib.sha256(f"TDFC-ALT-FOCUS-v1:{seed}:{item_key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _get(row, name: str, default=None):
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _question(prompt: str, answer: int, category: str) -> dict:
    identity = skill_identity_for_question({"prompt": prompt, "correct_answer": answer, "category": category})
    return {
        "prompt": str(prompt),
        "correct_answer": int(answer),
        "category": str(category),
        "domain": identity.domain,
        "skill_key": identity.skill_key,
        "skill_label": identity.skill_label,
        "item_key": identity.item_key,
    }


def _addition_pool() -> list[dict]:
    return [_question(f"{a} + {b}", a + b, "Addition Facts") for a in range(0, 10) for b in range(a, 10)]


def _subtraction_pool() -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for a in range(0, 10):
        for b in range(a, 10):
            total = a + b
            if total > 18:
                continue
            for sub in {a, b}:
                q = _question(f"{total} − {sub}", total - sub, "Subtraction Facts")
                if q["item_key"] not in seen:
                    seen.add(q["item_key"])
                    result.append(q)
    return result


def _division_pool() -> list[dict]:
    return [
        _question(f"{divisor * quotient} ÷ {divisor}", quotient, "Division Facts")
        for divisor in range(2, 11) for quotient in range(2, 11)
    ]


def _multiplication_pool() -> list[dict]:
    # Mixed-only pool.  This never enters multiplication mastery.
    return [_question(f"{a} × {b}", a * b, "Multiplication") for a in range(2, 11) for b in range(a, 11)]


def _integer_pool() -> list[dict]:
    result: list[dict] = []
    for operation in ("+", "−"):
        for a in range(-9, 10):
            for b in range(-9, 10):
                # Keep a useful spread but avoid a pool dominated by trivial 0/0 repeats.
                if a == 0 and b == 0:
                    continue
                answer = a + b if operation == "+" else a - b
                prompt = f"{a} {operation} ({b})" if b < 0 else f"{a} {operation} {b}"
                result.append(_question(prompt, answer, "Integers"))
    return result


_POOLS = {
    "Addition Facts": _addition_pool,
    "Subtraction Facts": _subtraction_pool,
    "Division Facts": _division_pool,
    "Integers": _integer_pool,
    "Multiplication": _multiplication_pool,
}


def focus_candidate_pool(daily_mode: str) -> list[dict]:
    mode = str(daily_mode or "")
    if mode not in ALT_MODES:
        raise ValueError("Alternate Focus Practice requires an alternate Daily 10 mode.")
    domains = ALT_DOMAINS if mode == "Mixed" else (mode,)
    result: list[dict] = []
    for domain in domains:
        result.extend(_POOLS[domain]())
    return result


def _independent_event(row) -> bool:
    activity = str(_get(row, "activity_type", ""))
    if activity == "fix_miss":
        return False
    if activity == "focus" and bool(_get(row, "is_retry", False)):
        return False
    return activity in ("daily", "focus")


def build_alternate_focus_plan(
    daily_mode: str,
    daily_questions: Sequence[Mapping],
    daily_answers: Sequence[int],
    historical_events: Iterable,
    *,
    student_id: str,
    date_key: str,
) -> tuple[dict, ...]:
    """Build a deterministic eight-item personalized alternate Focus plan.

    Priority comes from independent evidence only.  Current Daily misses are the
    strongest signal; recent independent misses continue to raise an item/skill,
    while correct independent retrieval gradually lowers its priority.  Coached
    corrections are deliberately ignored so teaching is not misread as mastery.
    """
    mode = str(daily_mode or "")
    if mode not in ALT_MODES:
        raise ValueError("Alternate Focus Practice requires an alternate Daily 10 mode.")
    if len(daily_questions) != 10 or len(daily_answers) != 10:
        raise ValueError("Alternate Focus Practice requires the saved Daily 10.")

    allowed = set(ALT_DOMAINS if mode == "Mixed" else (mode,))
    item_score: dict[str, float] = {}
    skill_score: dict[tuple[str, str], float] = {}
    item_exposures: dict[str, int] = {}

    # Recent rows are expected newest-first from the Supabase helper.  Limiting the
    # window keeps old struggles from following a student forever.
    rows = list(historical_events)[:500]
    for position, row in enumerate(rows):
        if not _independent_event(row):
            continue
        domain = str(_get(row, "domain", ""))
        if domain not in allowed:
            continue
        item_key = str(_get(row, "item_key", ""))
        skill_key = str(_get(row, "skill_key", ""))
        if not item_key or not skill_key:
            continue
        # Gentle recency decay across the retrieved history.
        recency = max(0.35, 1.0 - (position / 700.0))
        correct = bool(_get(row, "correct", False))
        item_exposures[item_key] = item_exposures.get(item_key, 0) + 1
        if correct:
            item_score[item_key] = item_score.get(item_key, 0.0) - 2.5 * recency
            skill_score[(domain, skill_key)] = skill_score.get((domain, skill_key), 0.0) - 0.8 * recency
        else:
            item_score[item_key] = item_score.get(item_key, 0.0) + 14.0 * recency
            skill_score[(domain, skill_key)] = skill_score.get((domain, skill_key), 0.0) + 6.0 * recency

    current_rows = daily_evidence_rows(
        daily_questions,
        daily_answers,
        default_domain=None if mode == "Mixed" else mode,
    )
    current_miss_keys: set[str] = set()
    current_keys: set[str] = set()
    for row in current_rows:
        domain = str(row["domain"])
        if domain not in allowed:
            continue
        key = str(row["item_key"])
        skill = (domain, str(row["skill_key"]))
        current_keys.add(key)
        if bool(row["correct"]):
            item_score[key] = item_score.get(key, 0.0) + 7.0
            skill_score[skill] = skill_score.get(skill, 0.0) + 1.5
        else:
            current_miss_keys.add(key)
            item_score[key] = item_score.get(key, 0.0) + 80.0
            skill_score[skill] = skill_score.get(skill, 0.0) + 24.0

    seed = f"{student_id}:{date_key}:{mode}"
    targets: list[AlternateFocusTarget] = []
    for q in focus_candidate_pool(mode):
        identity = skill_identity_for_question(q)
        if identity.domain not in allowed:
            continue
        score = item_score.get(identity.item_key, 0.0) + skill_score.get((identity.domain, identity.skill_key), 0.0)
        # Give unseen facts a small invitation, while still preferring today's scope.
        if item_exposures.get(identity.item_key, 0) == 0:
            score += 1.5
        if identity.item_key in current_miss_keys:
            reason = "Today’s miss"
        elif item_score.get(identity.item_key, 0.0) >= 10 or skill_score.get((identity.domain, identity.skill_key), 0.0) >= 5:
            reason = "Recent need"
        elif identity.item_key in current_keys:
            reason = "Today’s practice"
        else:
            reason = "Build fluency"
        targets.append(AlternateFocusTarget(q, score, reason))

    targets.sort(key=lambda target: (-target.score, _stable_rank(seed, str(target.question["item_key"]))))

    chosen: list[dict] = []
    seen: set[str] = set()
    for target in targets:
        key = str(target.question["item_key"])
        if key in seen:
            continue
        seen.add(key)
        item = dict(target.question)
        item["focus_reason"] = target.reason
        chosen.append(item)
        if len(chosen) == ALT_FOCUS_SESSION_LENGTH:
            break

    if len(chosen) != ALT_FOCUS_SESSION_LENGTH:
        raise ValueError("Could not build the full alternate Focus Practice plan.")
    return tuple(chosen)
