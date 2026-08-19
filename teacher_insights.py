from __future__ import annotations

"""Teacher-facing interpretation helpers for fact fluency and Igniter evidence.

The adaptive engine remains the source of truth for student practice.  This
module translates that evidence into plain classroom language without changing
how Focus Practice, Daily 10, or mastery evidence are calculated.
"""

from dataclasses import dataclass
from statistics import median
from typing import Iterable, Mapping, Sequence

from adaptive_engine import (
    STATUS_FLUENT,
    STATUS_FOCUS,
    MasterySnapshot,
)

BAND_KNOWN = "known"
BAND_SLOW = "slow"
BAND_HELP = "needs_help"
BAND_LEARNING = "learning"

BAND_LABELS = {
    BAND_KNOWN: "Knows It",
    BAND_SLOW: "Accurate, Still Slow",
    BAND_HELP: "Needs Help",
    BAND_LEARNING: "Still Learning",
}


@dataclass(frozen=True)
class StudentFluencySummary:
    student_id: str
    nickname: str
    known: int
    slow: int
    needs_help: int
    learning: int
    evidence_facts: int
    typical_correct_seconds: float | None
    pull_score: float
    start_facts: tuple[str, ...]


def teacher_fact_band(snapshot: MasterySnapshot) -> str:
    """Translate one fact snapshot into teacher-friendly classroom language.

    Accuracy remains primary.  A fact is only called "slow" when the student
    has repeated accurate retrieval evidence and the weighted correct-response
    time is still above five seconds.  Unknown/limited evidence is never treated
    as a deficit.
    """
    if snapshot.evidence_count < 2 or snapshot.ema_accuracy is None:
        return BAND_LEARNING
    if snapshot.status == STATUS_FOCUS:
        return BAND_HELP
    if snapshot.status == STATUS_FLUENT:
        return BAND_KNOWN
    if (
        snapshot.evidence_count >= 3
        and snapshot.ema_accuracy >= 0.80
        and snapshot.correct_streak >= 2
        and snapshot.ema_seconds is not None
        and snapshot.ema_seconds > 5.0
    ):
        return BAND_SLOW
    return BAND_LEARNING


def _fact_label(snapshot: MasterySnapshot) -> str:
    return f"{snapshot.a}×{snapshot.b}"


def summarize_student_fluency(
    student_id: str,
    nickname: str,
    rows: Iterable[MasterySnapshot],
) -> StudentFluencySummary:
    snapshots = list(rows)
    by_band = {band: [] for band in (BAND_KNOWN, BAND_SLOW, BAND_HELP, BAND_LEARNING)}
    for row in snapshots:
        by_band[teacher_fact_band(row)].append(row)

    stable_times = [
        float(row.ema_seconds)
        for row in snapshots
        if teacher_fact_band(row) in {BAND_KNOWN, BAND_SLOW} and row.ema_seconds is not None
    ]
    typical = float(median(stable_times)) if stable_times else None
    evidence_facts = sum(row.evidence_count >= 2 for row in snapshots)

    help_rows = sorted(
        by_band[BAND_HELP],
        key=lambda row: (
            row.ema_accuracy if row.ema_accuracy is not None else 1.0,
            -row.evidence_count,
            row.a,
            row.b,
        ),
    )
    slow_rows = sorted(
        by_band[BAND_SLOW],
        key=lambda row: (-(row.ema_seconds or 0.0), row.a, row.b),
    )
    start_rows = (help_rows + slow_rows)[:5]

    needs_help = len(help_rows)
    slow = len(slow_rows)
    # Repeated misses dominate the priority.  Slow-but-accurate facts matter,
    # but should never outrank an accuracy problem.
    pull_score = needs_help * 10.0 + slow * 2.0

    return StudentFluencySummary(
        student_id=str(student_id),
        nickname=str(nickname),
        known=len(by_band[BAND_KNOWN]),
        slow=slow,
        needs_help=needs_help,
        learning=len(by_band[BAND_LEARNING]),
        evidence_facts=evidence_facts,
        typical_correct_seconds=typical,
        pull_score=pull_score,
        start_facts=tuple(_fact_label(row) for row in start_rows),
    )


def should_pull(summary: StudentFluencySummary) -> bool:
    """Return True only for an actionable accuracy or fluency concern."""
    return summary.needs_help > 0 or summary.slow >= 4


def pull_reason(summary: StudentFluencySummary) -> str:
    if summary.needs_help >= 2:
        return f"{summary.needs_help} facts repeatedly missed"
    if summary.needs_help == 1 and summary.slow:
        return f"1 repeated miss + {summary.slow} slow facts"
    if summary.needs_help == 1:
        return "1 fact repeatedly missed"
    if summary.slow >= 4:
        return f"{summary.slow} accurate-but-slow facts"
    return "Keep gathering evidence"


def rank_students_to_pull(summaries: Sequence[StudentFluencySummary]) -> list[StudentFluencySummary]:
    return sorted(
        [summary for summary in summaries if should_pull(summary)],
        key=lambda summary: (-summary.pull_score, summary.nickname.casefold()),
    )


def common_fact_needs(
    full_by_student: Mapping[str, Mapping[tuple[int, int], MasterySnapshot]],
    *,
    limit: int = 5,
) -> list[dict]:
    """Return the most common class fact needs, with accuracy needs first."""
    if not full_by_student:
        return []
    first_map = next(iter(full_by_student.values()))
    results = []
    for key in sorted(first_map):
        help_count = 0
        slow_count = 0
        for student_map in full_by_student.values():
            band = teacher_fact_band(student_map[key])
            help_count += band == BAND_HELP
            slow_count += band == BAND_SLOW
        score = help_count * 10 + slow_count * 2
        if score:
            results.append({
                "fact": f"{key[0]} × {key[1]}",
                "needs_help": help_count,
                "slow": slow_count,
                "score": score,
            })
    return sorted(results, key=lambda row: (-row["score"], -row["needs_help"], -row["slow"], row["fact"]))[:limit]


def standard_student_history(students, rows, standard_code: str) -> list[dict]:
    """Aggregate Igniter evidence for one standard by current student.

    The history preserves each individual check.  This is evidence, not an
    automatic claim that the entire academic standard has been mastered.
    """
    code = str(standard_code or "").strip()
    matching = [row for row in rows if str(getattr(row, "standard_code", "") or "").strip() == code]
    by_student: dict[str, list] = {}
    for row in matching:
        by_student.setdefault(str(row.student_id), []).append(row)

    output = []
    for student in students:
        student_rows = sorted(
            by_student.get(str(student.student_id), []),
            key=lambda row: (str(row.warmup_date), getattr(row, "answered_at", None), int(row.question_slot)),
        )
        checks = len(student_rows)
        correct = sum(bool(row.correct) for row in student_rows)
        marks = ["✅" if row.correct else "❌" for row in student_rows[-8:]]
        history = " ".join(marks) if marks else "—"
        output.append({
            "student_id": str(student.student_id),
            "nickname": str(student.nickname),
            "checks": checks,
            "correct": correct,
            "accuracy": None if checks == 0 else correct / checks,
            "history": history,
            "rows": student_rows,
        })
    return sorted(
        output,
        key=lambda item: (
            item["accuracy"] is None,
            item["accuracy"] if item["accuracy"] is not None else 2.0,
            item["nickname"].casefold(),
        ),
    )
