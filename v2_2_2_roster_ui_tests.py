from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()

checks = {
    "version bumped": 'APP_VERSION = "2.8.4"' in ENGINE,
    "roster management visible": '🔧 Roster Management' in APP,
    "bulk selector": '"Select student(s)"' in APP,
    "bulk move visible": '"Move selected student(s)"' in APP,
    "bulk delete visible": '"Delete selected student(s)"' in APP,
    "delete confirmation": '"I understand deletion is permanent."' in APP,
    "move preserves history copy": "Moving preserves all student history" in APP,
    "move uses store method": 'store.move_student(target.student_id, destination.class_id)' in APP,
    "delete uses bulk store method": 'store.delete_students([target.student_id for target in targets])' in APP,
    "move fallback if no other class": 'Create another active class first, then you can move students into it.' in APP,
    "individual move remains": '"Move student"' in APP,
    "individual delete remains": '"Delete student permanently"' in APP,
}
failed=[name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
if failed:
    raise SystemExit(f"Failed {len(failed)} checks: {failed}")
print(f"All {len(checks)} v2.2.2 roster UI checks passed.")
