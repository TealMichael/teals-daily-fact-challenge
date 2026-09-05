from __future__ import annotations

from pathlib import Path
import hashlib

from fact_engine import APP_VERSION
from student_recognition import build_public_daily_recognition

ROOT = Path(__file__).resolve().parent
CHECKS = 0


def check(label: str, condition: bool) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1


check("v2.19.9 version", APP_VERSION == "2.19.9")

# Shared recognition logic: Top 10 remains exactly the ranked input order; the
# second club includes only 10/10 students outside Top 10 and alphabetizes them.
completed = []
for index, name in enumerate([
    "RankOne", "RankTwo", "RankThree", "RankFour", "RankFive",
    "RankSix", "RankSeven", "RankEight", "RankNine", "RankTen",
    "Zulu", "alpha", "Bravo",
], start=1):
    completed.append({
        "student_id": f"s{index}",
        "nickname": name,
        "correct_count": 10,
        "timed_seconds": float(index),
    })
completed.append({"student_id": "s14", "nickname": "Almost", "correct_count": 9, "timed_seconds": 1.0})
context = build_public_daily_recognition(completed, roster_count=28, student_id="s12")
check("Top 10 unchanged", [row["nickname"] for row in context["rows"]] == [row["nickname"] for row in completed[:10]])
check("Top 10 ranks remain 1-10", [row["rank"] for row in context["rows"]] == list(range(1, 11)))
check("Perfect club excludes Top 10", not ({row["student_id"] for row in context["rows"]} & {row["student_id"] for row in context["perfect_rows"]}))
check("Perfect club excludes non-perfect", "Almost" not in [row["nickname"] for row in context["perfect_rows"]])
check("Perfect club alphabetized", [row["nickname"] for row in context["perfect_rows"]] == ["alpha", "Bravo", "Zulu"])
check("Public Top 10 strips scores and time", all(set(row) == {"student_id", "nickname", "rank"} for row in context["rows"]))
check("Public perfect club strips scores and time", all(set(row) == {"student_id", "nickname"} for row in context["perfect_rows"]))
check("student id retained only for own highlight", context["student_id"] == "s12")
check("finished and roster counts retained", context["finished"] == 14 and context["roster_count"] == 28)

short = build_public_daily_recognition(completed[:9], roster_count=20)
check("No duplicate club when perfect scorers are already Top 10", short["perfect_rows"] == [])

app = (ROOT / "app.py").read_text(encoding="utf-8")
alt = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
recognition = (ROOT / "student_recognition.py").read_text(encoding="utf-8")
schema = (ROOT / "SUPABASE_SCHEMA.sql").read_text(encoding="utf-8")
migration = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_19_9.sql").read_text(encoding="utf-8")
berry = (ROOT / "AWTRIX_FactTop10.berry").read_bytes()

check("Multiplication and alternate student flows share recognition builder", "build_public_daily_recognition" in app and "build_public_daily_recognition" in alt)
check("Student final screen labels Perfect Score Club", "### ⭐ Perfect Score Club" in app)
check("Alternate final screen labels Perfect Score Club", "### ⭐ Perfect Score Club" in alt)
check("Perfect 10 student gets positive own status", app.count("⭐ Perfect 10/10! You're in today's Perfect Score Club.") >= 2 and "⭐ Perfect 10/10! You're in today's Perfect Score Club." in alt)
check("Club is explicitly 10/10", "10/10 today" in app and "10/10 today" in alt)
check("Shared logic keeps club out of speed ranking", "alphabetized so it does not become a second speed leaderboard" in recognition)

for sql_text, label in ((schema, "fresh schema"), (migration, "v2.19.9 migration")):
    lower = sql_text.lower()
    check(f"{label} keeps accuracy-first Top 10", "order by da.correct_count desc, da.timed_seconds asc, da.completed_at asc" in lower)
    check(f"{label} recognizes only perfect scores below Top 10", "correct_count = 10 and rank > 10" in lower)
    check(f"{label} alphabetizes perfect names", "order by lower(nickname), nickname" in lower)
    check(f"{label} appends club after Top 10 text", "v_text := v_text || '   perfect score club!   ' || v_perfect_names" in lower)
    check(f"{label} excludes test students", "coalesce(s.is_test, false) = false" in lower)
    check(f"{label} excludes inactive students", "s.active = true" in lower)
    check(f"{label} returns only preformatted text/count metadata", "'perfect_count', v_perfect_count" in lower and "'text', v_text" in lower)

check("Existing AWTRIX Berry script is unchanged", hashlib.sha256(berry).hexdigest() == "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2")
check("No AWTRIX reinstall instructions in migration", "Berry script" in migration and "does not change" in migration)

# Core multiplication teaching/runtime sources remain byte-for-byte untouched.
EXPECTED = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
}
for rel, expected in EXPECTED.items():
    check(f"protected multiplication source unchanged: {rel}", hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == expected)

print(f"v2.19.9 Perfect Score Club: PASS ({CHECKS}/{CHECKS} checks)")
