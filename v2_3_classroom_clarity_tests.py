from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
ENGINE = (ROOT / "fact_engine.py").read_text(encoding="utf-8")


def function_body(name: str, next_name: str) -> str:
    start = APP.index(f"def {name}(")
    end = APP.index(f"\ndef {next_name}(", start)
    return APP[start:end]

leader_context = function_body("load_leaderboard_context", "_leaderboard_cache_key")
leader_render = function_body("render_leaderboard", "render_daily_review")

a = {
    "version 2.6": 'APP_VERSION = "2.6.1"' in ENGINE,
    "four-step routine strip": 'def render_routine_strip(stage: str)' in APP and '1 · Daily 10' in APP and '4 · Mystery' in APP,
    "daily shows routine strip": 'render_routine_strip("daily")' in APP,
    "done screen is unmistakable": "YOU'RE DONE FOR TODAY!" in APP,
    "done screen says work is finished": "Your learning work is finished" in APP,
    "mystery explicitly earned": "You earned today's Mystery reward!" in APP,
    "mystery guesses limited to Thu/Fri": "Guess #1 of 2 — Thursday" in APP and "Guess #2 of 2 — Friday" in APP,
    "Friday can reveal without guess": "Reveal without using my Friday guess" in APP,
    "final all-done line": "That's it — see you next Challenge day!" in APP,
    "extra practice labeled optional": "Extra Practice (optional)" in APP,
    "student leaderboard context strips correct_count": '"correct_count"' not in leader_context,
    "student leaderboard context strips timed_seconds": '"timed_seconds"' not in leader_context,
    "student leaderboard render has no score field": "leader-score" not in leader_render,
    "student leaderboard only builds rank and nickname": '"rank": index' in leader_context and '"nickname": row["nickname"]' in leader_context,
    "teacher today defines Done": "Done means Daily 10 + Fix Your Misses + Focus Practice are complete" in APP,
    "teacher today says mystery optional": "The Mystery guess is optional" in APP,
    "teacher today has done working not-started": 'c1.metric("🟢 Done"' in APP and 'c2.metric("🟡 Working"' in APP and 'c3.metric("⚪ Not started"' in APP,
    "teacher performance details are teacher-only": "Teacher-only accuracy & timing" in APP,
    "teacher Top 10 preview states exact privacy": "rank + nickname only" in APP,
    "teacher tabs reorganized": all(x in APP for x in ["📊 Today", "👥 Classes & Rosters", "🎯 Mastery & Focus", "🕵️ Weekly Mystery", "🛠️ Student Support"]),
    "classes keeps class creation": "Create a class" in APP and "Create students + PINs" in APP,
    "classes keeps bulk move": "Move selected student(s)" in APP,
    "classes keeps bulk delete": "Delete selected student(s)" in APP,
    "classes keeps clear roster": "Clear this entire roster" in APP,
    "student support keeps nickname": "Save nickname" in APP,
    "student support keeps visible PIN": "Current classroom PIN" in APP,
    "student support keeps PIN reset": "Generate new PIN" in APP,
    "student support keeps daily reset": "Reset today's Daily attempt" in APP,
    "student support keeps focus override": "Personal Focus override" in APP,
    "student support keeps move": "Move student" in APP,
    "student support keeps deactivate/reactivate": "Deactivate student" in APP and "Reactivate student" in APP,
    "student support keeps permanent delete": "Delete student permanently" in APP,
    "mastery keeps global override": "Save everyone focus" in APP,
    "mastery keeps class override": "Save class focus" in APP,
}

failed = [name for name, ok in a.items() if not ok]
for name, ok in a.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
if failed:
    raise SystemExit(f"Failed {len(failed)} checks: {failed}")
print(f"v2.3 classroom clarity: {len(a)}/{len(a)} checks passed")
