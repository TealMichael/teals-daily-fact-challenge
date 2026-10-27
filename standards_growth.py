from __future__ import annotations

"""Transparent, recent-evidence standards growth labels.

The four most recent *independent* checks drive the label. Historical evidence
is retained for teacher review but older misses cannot permanently outweigh
new learning. No label is a report-card grade or permanent certification.
"""

from dataclasses import dataclass
from datetime import date
from typing import Sequence

NOT_CHECKED = "Not Yet Checked"
LEARNING = "Learning"
GROWING = "Growing"
CONFIDENT = "Confident"
WINDOW = 4


@dataclass(frozen=True)
class GrowthSnapshot:
    label: str
    checks: int
    recent_correct: int
    distinct_correct_days: int
    progress: float
    last_checked: str | None


def _field(record, name: str, default=None):
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _ordered(rows: Sequence) -> list:
    return sorted(rows, key=lambda row: (
        str(_field(row, "activity_date", "")),
        str(_field(row, "answered_at", "")),
        str(_field(row, "source_slot", "") or ""),
    ))


def growth_snapshot(rows: Sequence) -> GrowthSnapshot:
    ordered = _ordered(rows)
    recent = ordered[-WINDOW:]
    count = len(recent)
    if not count:
        return GrowthSnapshot(NOT_CHECKED, 0, 0, 0, 0.0, None)

    successes = [row for row in recent if bool(_field(row, "correct", False))]
    correct_days = {str(_field(row, "activity_date", "")) for row in successes}
    # Distinct dates are mandatory: several correct questions in one lesson are
    # evidence of progress, but cannot alone establish sustained confidence.
    if count >= 4 and len(successes) >= 3 and len(correct_days) >= 2:
        label = CONFIDENT
    elif len(successes) >= 2 and len(correct_days) >= 2:
        label = GROWING
    else:
        label = LEARNING

    # This is a private visual-strength signal, never a percentage grade.
    # Evidence sufficiency and recency both matter; a correct answer only moves
    # the bar if it actually improves the student's current evidence pattern.
    weighted = sum((i + 1) for i, row in enumerate(recent)
                   if bool(_field(row, "correct", False)))
    possible = sum(range(1, count + 1))
    recent_accuracy = weighted / possible if possible else 0.0
    coverage = min(1.0, count / WINDOW)
    score = 100 * recent_accuracy * (0.38 + 0.62 * coverage)
    # Reserve visual space for the higher, earned labels. The bar is deliberately
    # illustrative rather than a numerical mastery percentage.
    if label == LEARNING:
        # A first correct check must not fill the entire Learning band: the
        # second Igniter check should also show a small, genuine increase.
        # Incorrect attempts still lower the underlying recent evidence.
        score = min(39.0, 100 * recent_accuracy * (0.14 + 0.25 * coverage))
    elif label == GROWING:
        score = max(42.0, min(score, 77.0))
    else:
        score = max(80.0, min(score, 100.0))
    return GrowthSnapshot(
        label, count, len(successes), len(correct_days),
        round(score, 1), str(_field(ordered[-1], "activity_date", "")),
    )


def evidence_for_standard(rows: Sequence, student_id: str, standard_code: str) -> list:
    return [row for row in rows
            if str(_field(row, "student_id", "")) == str(student_id)
            and str(_field(row, "standard_code", "")) == str(standard_code)]


def needs_fresh_check(last_checked: str | None, today: date, *, days: int = 30) -> bool:
    if not last_checked:
        return False
    try:
        return (today - date.fromisoformat(last_checked)).days >= days
    except (ValueError, TypeError):
        return False
