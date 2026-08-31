from __future__ import annotations

"""Core multiplication-fact logic for Teal's Daily Fact Challenge.

The Daily generator is intentionally deterministic: every student receives the
same 10 facts in the same order for a given Eastern/Indiana calendar date.
Facts are balanced across difficulty bands, use 2s-10s as the core universe,
and include at most one 11/12 extension fact on selected days.
"""

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import random
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

APP_VERSION = "2.16.0"
CHALLENGE_VERSION = "TDFC-DAILY-v1"
DAILY_TIMEZONE = ZoneInfo("America/Indiana/Indianapolis")

CORE_MIN = 2
CORE_MAX = 10
EXTENSION_MAX = 12
DAILY_FACT_COUNT = 10


@dataclass(frozen=True)
class Fact:
    a: int
    b: int
    tier: str

    @property
    def product(self) -> int:
        return self.a * self.b

    @property
    def key(self) -> tuple[int, int]:
        return tuple(sorted((self.a, self.b)))

    @property
    def label(self) -> str:
        return f"{self.a} × {self.b}"

    def as_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "tier": self.tier}

    @classmethod
    def from_dict(cls, value: dict) -> "Fact":
        return cls(a=int(value["a"]), b=int(value["b"]), tier=str(value.get("tier") or "core"))


def current_daily_date(now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(DAILY_TIMEZONE)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=DAILY_TIMEZONE)
    else:
        now = now.astimezone(DAILY_TIMEZONE)
    return now.date()


def current_daily_date_key(now: datetime | None = None) -> str:
    return current_daily_date(now).isoformat()


def canonical_pair(a: int, b: int) -> tuple[int, int]:
    return tuple(sorted((int(a), int(b))))


def _stable_int(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _factor_weight(value: int) -> int:
    # 2s, 5s, and 10s are usually the quickest retrieval anchors. 7s and 8s
    # tend to be the highest-load core families for elementary fact fluency.
    return {
        2: 1,
        3: 2,
        4: 2,
        5: 1,
        6: 3,
        7: 4,
        8: 4,
        9: 3,
        10: 1,
    }[value]


def core_difficulty(pair: tuple[int, int]) -> str:
    a, b = pair
    if not (CORE_MIN <= a <= CORE_MAX and CORE_MIN <= b <= CORE_MAX):
        raise ValueError("core_difficulty only accepts 2s-10s facts")

    if a == b:
        if a <= 5 or a == 10:
            return "easy"
        if a == 6:
            return "medium"
        return "hard"
    max_weight = max(_factor_weight(a), _factor_weight(b))
    min_weight = min(_factor_weight(a), _factor_weight(b))
    if max_weight <= 1:
        return "easy"
    if max_weight == 2 and min_weight <= 2:
        return "easy" if (a == b or 2 in pair or 5 in pair or 10 in pair) else "medium"
    if max_weight >= 4 and min_weight >= 2:
        return "hard"
    if max_weight >= 3 and min_weight >= 3:
        return "hard"
    return "medium"


def _core_pools() -> dict[str, list[tuple[int, int]]]:
    pools = {"easy": [], "medium": [], "hard": []}
    for a in range(CORE_MIN, CORE_MAX + 1):
        for b in range(a, CORE_MAX + 1):
            pools[core_difficulty((a, b))].append((a, b))
    return pools


CORE_POOLS = _core_pools()
EXTENSION_POOL = [
    (a, b)
    for a in range(CORE_MIN, EXTENSION_MAX + 1)
    for b in range(a, EXTENSION_MAX + 1)
    if b >= 11
]


def _fixed_permutation(values: Sequence[tuple[int, int]], salt: str) -> list[tuple[int, int]]:
    result = list(values)
    rng = random.Random(_stable_int(f"{CHALLENGE_VERSION}:{salt}"))
    rng.shuffle(result)
    return result


PERMUTED_POOLS = {tier: _fixed_permutation(values, tier) for tier, values in CORE_POOLS.items()}
PERMUTED_EXTENSION = _fixed_permutation(EXTENSION_POOL, "extension")


def _take_rotating(pool: Sequence[tuple[int, int]], count: int, day_index: int, step: int) -> list[tuple[int, int]]:
    if count <= 0:
        return []
    if not pool:
        raise ValueError("Cannot select facts from an empty pool")
    start = (day_index * step) % len(pool)
    return [pool[(start + offset) % len(pool)] for offset in range(count)]


def _extension_day(day: date) -> bool:
    # Roughly 40% of dates include one 11/12 fact. The remaining dates stay
    # entirely within the 2s-10s core. This is deterministic across devices.
    return _stable_int(f"{CHALLENGE_VERSION}:extension-day:{day.isoformat()}") % 5 in {1, 4}


def _orient(pair: tuple[int, int], day: date, index: int) -> tuple[int, int]:
    a, b = pair
    if a == b:
        return a, b
    flip = _stable_int(f"{CHALLENGE_VERSION}:orient:{day.isoformat()}:{index}:{a}:{b}") % 2
    return (b, a) if flip else (a, b)


def daily_facts_for_date(day: date | str) -> list[Fact]:
    if isinstance(day, str):
        day = date.fromisoformat(day)
    day_index = day.toordinal()

    include_extension = _extension_day(day)
    counts = {"easy": 3, "medium": 4, "hard": 2 if include_extension else 3}

    # Distinct per-tier stride values reduce short-term repeats without making
    # the sequence hard to reproduce or audit.
    selected: list[tuple[tuple[int, int], str]] = []
    for tier, stride in (("easy", 3), ("medium", 5), ("hard", 3)):
        pairs = _take_rotating(PERMUTED_POOLS[tier], counts[tier], day_index, stride)
        selected.extend((pair, tier) for pair in pairs)

    if include_extension:
        ext_pair = PERMUTED_EXTENSION[day_index % len(PERMUTED_EXTENSION)]
        selected.append((ext_pair, "extension"))

    # Defensive de-duplication by commutative pair. The tier pools are disjoint,
    # so this should never trigger, but keeping the invariant explicit makes the
    # daily generator safer to evolve later.
    seen: set[tuple[int, int]] = set()
    unique: list[tuple[tuple[int, int], str]] = []
    for pair, tier in selected:
        key = canonical_pair(*pair)
        if key in seen:
            continue
        seen.add(key)
        unique.append((pair, tier))

    if len(unique) != DAILY_FACT_COUNT:
        raise RuntimeError(f"Daily generator produced {len(unique)} facts instead of {DAILY_FACT_COUNT}")

    # Shuffle the final order with a date-specific deterministic seed so the
    # daily does not always progress easy -> medium -> hard.
    rng = random.Random(_stable_int(f"{CHALLENGE_VERSION}:order:{day.isoformat()}"))
    rng.shuffle(unique)

    facts: list[Fact] = []
    for index, (pair, tier) in enumerate(unique):
        a, b = _orient(pair, day, index)
        facts.append(Fact(a=a, b=b, tier=tier))
    return facts


def validate_daily_facts(facts: Sequence[Fact]) -> None:
    if len(facts) != DAILY_FACT_COUNT:
        raise ValueError("A Daily Challenge must contain exactly 10 facts")
    keys = [fact.key for fact in facts]
    if len(set(keys)) != len(keys):
        raise ValueError("A Daily Challenge cannot repeat a fact or its commutative mirror")
    extension_count = sum(max(fact.a, fact.b) >= 11 for fact in facts)
    if extension_count > 1:
        raise ValueError("A Daily Challenge may contain at most one 11/12 fact")
    for fact in facts:
        if min(fact.a, fact.b) < CORE_MIN or max(fact.a, fact.b) > EXTENSION_MAX:
            raise ValueError("Daily facts must stay within 2s-12s")


def fact_family_options() -> list[str]:
    return ["Mixed"] + [f"{value}s" for value in range(2, 13)]


def practice_fact(focus: str, rng: random.Random | None = None, *, avoid: Iterable[tuple[int, int]] = ()) -> Fact:
    rng = rng or random.Random()
    avoid_keys = {canonical_pair(*pair) for pair in avoid}

    if focus == "Mixed":
        candidates = [
            (a, b)
            for a in range(2, 13)
            for b in range(a, 13)
        ]
    else:
        text = str(focus).strip().lower().replace("×", "").replace("s", "")
        try:
            family = int(text)
        except ValueError as exc:
            raise ValueError(f"Unknown practice focus: {focus}") from exc
        if not 2 <= family <= 12:
            raise ValueError("Practice family must be between 2 and 12")
        candidates = [canonical_pair(family, other) for other in range(2, 13)]

    candidates = list(dict.fromkeys(candidates))
    available = [pair for pair in candidates if pair not in avoid_keys] or candidates
    pair = rng.choice(available)
    a, b = pair
    if a != b and rng.random() < 0.5:
        a, b = b, a
    tier = "extension" if max(a, b) >= 11 else core_difficulty(canonical_pair(a, b))
    return Fact(a=a, b=b, tier=tier)


def repeated_addition_text(fact: Fact) -> str:
    # Keep the explanation readable: use the smaller number of groups when the
    # commutative orientation would otherwise create a very long sentence.
    rows, columns = fact.a, fact.b
    if rows > columns:
        rows, columns = columns, rows
    pieces = " + ".join([str(columns)] * rows)
    return f"{rows} groups of {columns}: {pieces} = {fact.product}."


def daily_mix_summary(facts: Sequence[Fact]) -> dict[str, int]:
    return {
        "easy": sum(f.tier == "easy" for f in facts),
        "medium": sum(f.tier == "medium" for f in facts),
        "hard": sum(f.tier == "hard" for f in facts),
        "extension": sum(f.tier == "extension" for f in facts),
    }
