from __future__ import annotations

"""Student-safe Daily recognition shared by every Daily 10 mode.

The ranking input may include scores and times on the server, but the returned
context intentionally contains only public Top 10 rank/nickname data plus
Perfect Score Club membership (10/10 students not already in the Top 10).
"""

from collections.abc import Mapping, Sequence


def build_public_daily_recognition(
    completed: Sequence[Mapping], *, roster_count: int, student_id: str | None = None
) -> dict:
    """Build one shared Top 10 + Perfect Score Club snapshot.

    `completed` must already be ranked accuracy-first, then time, matching the
    established Daily leaderboard. Perfect Score Club never changes ranking:
    it only recognizes 10/10 students who fall below rank 10. Club names are
    alphabetized so it does not become a second speed leaderboard.
    """
    completed_rows = list(completed)
    top_completed = completed_rows[:10]
    top_ids = {str(row["student_id"]) for row in top_completed}
    top_rows = [
        {
            "student_id": str(row["student_id"]),
            "nickname": str(row["nickname"]),
            "rank": index,
        }
        for index, row in enumerate(top_completed, start=1)
    ]
    perfect_rows = sorted(
        [
            {"student_id": str(row["student_id"]), "nickname": str(row["nickname"])}
            for row in completed_rows
            if int(row.get("correct_count") or 0) == 10 and str(row["student_id"]) not in top_ids
        ],
        key=lambda row: (row["nickname"].casefold(), row["nickname"]),
    )
    context = {
        "rows": top_rows,
        "perfect_rows": perfect_rows,
        "finished": len(completed_rows),
        "roster_count": int(roster_count),
    }
    if student_id is not None:
        context["student_id"] = str(student_id)
    return context
