from __future__ import annotations

"""Adaptive mastery and Focus Practice logic for Teal's Daily Fact Challenge.

There is intentionally no placement test. New students begin with an unknown
45-fact core map and the profile grows from normal Daily Challenge and Focus
Practice evidence over time.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import random
from typing import Iterable, Mapping, Sequence

from fact_engine import Fact, canonical_pair, core_difficulty

CORE_FACTS: tuple[tuple[int, int], ...] = tuple(
    (a, b) for a in range(2, 11) for b in range(a, 11)
)
FOCUS_SESSION_LENGTH = 8

STATUS_UNKNOWN = "Unknown"
STATUS_FOCUS = "Focus"
STATUS_BUILDING = "Building"
STATUS_FLUENT = "Fluent"
STATUS_ORDER = (STATUS_FOCUS, STATUS_BUILDING, STATUS_UNKNOWN, STATUS_FLUENT)


@dataclass(frozen=True)
class MasterySnapshot:
    a: int
    b: int
    evidence_count: int = 0
    correct_count: int = 0
    ema_accuracy: float | None = None
    ema_seconds: float | None = None
    correct_streak: int = 0
    status: str = STATUS_UNKNOWN
    last_practiced_at: datetime | None = None

    @property
    def key(self) -> tuple[int, int]:
        return canonical_pair(self.a, self.b)

    @property
    def accuracy(self) -> float | None:
        if not self.evidence_count:
            return None
        return self.correct_count / self.evidence_count


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mastery_status(
    *,
    evidence_count: int,
    ema_accuracy: float | None,
    ema_seconds: float | None,
    correct_streak: int,
) -> str:
    """Turn gradually collected evidence into a simple student-facing label.

    Accuracy is primary. Speed only helps distinguish Fluent after enough
    accurate repetitions; it never overrides poor accuracy.
    """
    if evidence_count < 2 or ema_accuracy is None:
        return STATUS_UNKNOWN
    if ema_accuracy < 0.68:
        return STATUS_FOCUS
    if evidence_count >= 4 and ema_accuracy >= 0.88 and correct_streak >= 3:
        if ema_seconds is None or ema_seconds <= 5.0:
            return STATUS_FLUENT
    return STATUS_BUILDING


def update_snapshot(
    snapshot: MasterySnapshot | None,
    *,
    a: int,
    b: int,
    correct: bool,
    response_seconds: float | None,
    practiced_at: datetime | None = None,
) -> MasterySnapshot:
    """Apply one *independent retrieval* observation to a fact profile.

    Correction retries are deliberately excluded by callers. They are teaching,
    not evidence that a fact was independently retrieved.
    """
    a, b = canonical_pair(a, b)
    old = snapshot or MasterySnapshot(a=a, b=b)
    practiced_at = practiced_at or datetime.now(timezone.utc)
    count = old.evidence_count + 1
    correct_count = old.correct_count + (1 if correct else 0)
    accuracy_value = 1.0 if correct else 0.0
    if old.ema_accuracy is None:
        ema_accuracy = accuracy_value
    else:
        ema_accuracy = 0.65 * old.ema_accuracy + 0.35 * accuracy_value

    ema_seconds = old.ema_seconds
    if correct and response_seconds is not None:
        seconds = _clamp(float(response_seconds), 0.15, 30.0)
        ema_seconds = seconds if ema_seconds is None else 0.70 * ema_seconds + 0.30 * seconds

    streak = old.correct_streak + 1 if correct else 0
    status = mastery_status(
        evidence_count=count,
        ema_accuracy=ema_accuracy,
        ema_seconds=ema_seconds,
        correct_streak=streak,
    )
    return MasterySnapshot(
        a=a,
        b=b,
        evidence_count=count,
        correct_count=correct_count,
        ema_accuracy=ema_accuracy,
        ema_seconds=ema_seconds,
        correct_streak=streak,
        status=status,
        last_practiced_at=practiced_at,
    )


def mastery_priority(snapshot: MasterySnapshot) -> float:
    """Higher values mean a fact is more useful to revisit in Focus Practice."""
    if snapshot.status == STATUS_UNKNOWN:
        return 44.0
    acc = snapshot.ema_accuracy if snapshot.ema_accuracy is not None else 0.5
    speed_penalty = 0.0
    if snapshot.ema_seconds is not None:
        speed_penalty = _clamp((snapshot.ema_seconds - 4.0) * 2.0, 0.0, 12.0)
    base = {
        STATUS_FOCUS: 80.0,
        STATUS_BUILDING: 58.0,
        STATUS_FLUENT: 18.0,
    }.get(snapshot.status, 44.0)
    return base + (1.0 - acc) * 30.0 + speed_penalty


def complete_mastery_map(rows: Iterable[MasterySnapshot]) -> dict[tuple[int, int], MasterySnapshot]:
    result = {row.key: row for row in rows}
    for a, b in CORE_FACTS:
        result.setdefault((a, b), MasterySnapshot(a=a, b=b))
    return result


def mastery_counts(rows: Iterable[MasterySnapshot]) -> dict[str, int]:
    full = complete_mastery_map(rows)
    counts = {status: 0 for status in (STATUS_FLUENT, STATUS_BUILDING, STATUS_FOCUS, STATUS_UNKNOWN)}
    for row in full.values():
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


def _stable_seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def _choose_dissimilar(
    candidates: Sequence[MasterySnapshot],
    count: int,
    *,
    rng: random.Random,
    already: Sequence[tuple[int, int]] = (),
) -> list[MasterySnapshot]:
    """Prefer targets that do not all share the same factor when choices allow."""
    remaining = list(candidates)
    picked: list[MasterySnapshot] = []
    used = list(already)
    while remaining and len(picked) < count:
        top_window = remaining[: min(8, len(remaining))]
        def overlap_penalty(row: MasterySnapshot) -> tuple[int, float]:
            factors = set(row.key)
            overlap = sum(bool(factors & set(pair)) for pair in used)
            return overlap, -mastery_priority(row)
        best_penalty = min(overlap_penalty(row)[0] for row in top_window)
        eligible = [row for row in top_window if overlap_penalty(row)[0] == best_penalty]
        row = rng.choice(eligible)
        picked.append(row)
        used.append(row.key)
        remaining.remove(row)
    return picked


def build_focus_plan(
    rows: Iterable[MasterySnapshot],
    *,
    student_id: str,
    date_key: str,
    override_family: int | None = None,
    recent_daily_misses: Sequence[tuple[int, int]] = (),
) -> list[Fact]:
    """Build an eight-retrieval personalized session with spacing and success.

    The plan intentionally mixes weak/building facts, a little unknown evidence
    gathering, and a maintenance success fact. Weak targets repeat with space
    between them rather than appearing back-to-back.
    """
    full = complete_mastery_map(rows)
    rng = random.Random(_stable_seed(f"focus-v2:{student_id}:{date_key}:{override_family}"))

    if override_family is not None:
        family = int(override_family)
        if not 2 <= family <= 10:
            raise ValueError("Teacher focus family must be 2 through 10")
        pool = [row for row in full.values() if family in row.key]
        pool.sort(key=lambda row: (-mastery_priority(row), row.key))
        targets = _choose_dissimilar(pool, 4, rng=rng)
    else:
        miss_keys = [canonical_pair(*pair) for pair in recent_daily_misses if canonical_pair(*pair) in full]
        missed = [full[key] for key in dict.fromkeys(miss_keys)]
        missed.sort(key=lambda row: (-mastery_priority(row), row.key))

        focus_rows = sorted(
            [row for row in full.values() if row.status == STATUS_FOCUS and row.key not in miss_keys],
            key=lambda row: (-mastery_priority(row), row.key),
        )
        building_rows = sorted(
            [row for row in full.values() if row.status == STATUS_BUILDING and row.key not in miss_keys],
            key=lambda row: (-mastery_priority(row), row.key),
        )
        unknown_rows = [row for row in full.values() if row.status == STATUS_UNKNOWN and row.key not in miss_keys]
        rng.shuffle(unknown_rows)

        targets: list[MasterySnapshot] = []
        for pool in (missed, focus_rows, building_rows, unknown_rows):
            if len(targets) >= 3:
                break
            chosen = _choose_dissimilar(
                [row for row in pool if row.key not in {item.key for item in targets}],
                3 - len(targets),
                rng=rng,
                already=[item.key for item in targets],
            )
            targets.extend(chosen)
        if not targets:
            targets = _choose_dissimilar(list(full.values()), 3, rng=rng)

    # A maintenance fact gives students successful retrievals and protects facts
    # that have already become fluent.
    fluent = [row for row in full.values() if row.status == STATUS_FLUENT and row.key not in {t.key for t in targets}]
    fluent.sort(key=lambda row: (row.last_practiced_at or datetime.min.replace(tzinfo=timezone.utc), row.key))
    non_targets = [row for row in full.values() if row.key not in {t.key for t in targets}]
    if fluent:
        maintenance = fluent[0]
    else:
        # Early in the year there may be no fluent facts yet. Use a different
        # non-target fact instead of repeating a weak target back-to-back.
        non_targets.sort(key=lambda row: (mastery_priority(row), row.key))
        maintenance = non_targets[0] if non_targets else None

    unknown = [row for row in non_targets if row.status == STATUS_UNKNOWN and row is not maintenance]
    rng.shuffle(unknown)
    explore = unknown[0] if unknown else next((row for row in non_targets if row is not maintenance), None)

    # Ensure at least three target anchors when an override yields fewer due to
    # future constraints (not expected with 2s-10s).
    if len(targets) < 3:
        fill = [row for row in full.values() if row.key not in {t.key for t in targets}]
        fill.sort(key=lambda row: (-mastery_priority(row), row.key))
        targets.extend(fill[: 3 - len(targets)])

    t0, t1, t2 = targets[0], targets[1], targets[2]
    slots: list[MasterySnapshot] = [
        t0,
        t1,
        maintenance or t2,
        t2,
        t0,
        explore or t1,
        t1,
        t2,
    ]

    facts: list[Fact] = []
    for index, row in enumerate(slots[:FOCUS_SESSION_LENGTH]):
        a, b = row.key
        if a != b and rng.random() < 0.5:
            a, b = b, a
        facts.append(Fact(a=a, b=b, tier=core_difficulty(canonical_pair(a, b))))
    return facts


def status_for_display(status: str) -> tuple[str, str]:
    return {
        STATUS_FLUENT: ("🟢", "Fluent"),
        STATUS_BUILDING: ("🟡", "Building"),
        STATUS_FOCUS: ("🔴", "Focus"),
        STATUS_UNKNOWN: ("⚪", "Learning"),
    }.get(status, ("⚪", str(status)))
