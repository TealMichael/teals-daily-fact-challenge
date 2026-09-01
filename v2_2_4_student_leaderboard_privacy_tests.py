from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
ENGINE = (ROOT / "fact_engine.py").read_text(encoding="utf-8")
TODAY = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")
ALL_UI = APP + "\n" + TODAY

checks = {
    "version bumped": 'APP_VERSION = "2.16.2"' in ENGINE,
    "leaderboard explains private tiebreak": "time used privately as the tiebreaker" in APP,
    "student leaderboard rows omit score cell": 'class="leader-score"' not in APP,
    "student daily result omits Accuracy card": '<div class="result-label">Accuracy</div>' not in APP,
    "student daily result omits Timed Sprint card": '<div class="result-label">Timed Sprint</div>' not in APP,
    "student daily result keeps Top 10 status": '<div class="result-label">Top 10</div>' in APP,
    "student daily result keeps instructional fixes": '<div class="result-label">Facts to Fix</div>' in APP,
    "teacher preview states privacy": "The classroom display shows rank and nickname only." in APP,
    "teacher full results still show accuracy": '"Daily accuracy": "" if row["correct_count"] is None' in ALL_UI,
    "teacher full results still show time": '"Time": "" if row["timed_seconds"] is None' in ALL_UI,
}
failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
if failed:
    raise SystemExit(f"Failed {len(failed)} checks: {failed}")
print(f"All {len(checks)} v2.2.4 student leaderboard privacy checks passed.")
