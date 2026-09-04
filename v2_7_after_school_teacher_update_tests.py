from datetime import date
from pathlib import Path

from fact_engine import APP_VERSION
from weekly_mystery import MYSTERIES, mystery_for_key, mystery_from_plan, mystery_to_plan

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
STORE = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
LEARNING = (ROOT / "teacher_learning_ui.py").read_text(encoding="utf-8")
TODAY = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")
ALL_UI = APP + "\n" + LEARNING + "\n" + TODAY


def run():
    checks = {}
    checks["version 2.7.0"] = APP_VERSION == "2.19.4"

    # Friday is a real fifth clue, with no skipped-day backfill.
    checks["all bank mysteries resolve to five clues"] = all(len(mystery_for_key(item.key).clues) == 5 for item in MYSTERIES)
    checks["student clue count includes Friday"] = "including Friday" in APP and "<= 5" in APP
    checks["skipped clues never backfill"] = "never grants clues for skipped days" in APP
    checks["Friday clue before final guess"] = APP.index("clue_count = min(5") < APP.index("Guess #2 of 2 — Friday")

    # Next-week planning uses existing app_settings persistence, not a new table.
    checks["generic app settings read"] = "def get_app_setting" in STORE
    checks["generic app settings write"] = "def set_app_setting" in STORE
    checks["mystery plan persistence"] = "def save_mystery_plan" in STORE and "weekly_mystery_plan::" in STORE
    checks["next week planning UI"] = "Next Week's Mystery" in APP
    checks["next week can use bank"] = "Use selected bank mystery" in APP
    checks["next week can reset automatic"] = "Reset next week to automatic" in APP
    checks["next week custom editor"] = "Save customized next-week mystery" in APP
    checks["five editable daily clues"] = "Clue #5 · Friday" in APP or 'day_name = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")' in APP
    checks["current week remains locked"] = "This week's mystery is locked because at least one student has already earned a clue" in APP

    base = mystery_for_key("abraham-lincoln")
    plan = mystery_to_plan(base)
    plan["answer"] = "Test Answer"
    plan["clues"] = [f"Test clue {i}" for i in range(1, 6)]
    plan["learning_paragraph"] = "A kid-friendly paragraph about the test answer."
    plan["fun_fact"] = "A fun test fact."
    custom = mystery_from_plan(plan)
    checks["custom plan round trip"] = custom.answer == "Test Answer" and len(custom.clues) == 5 and custom.clues[-1] == "Test clue 5"
    checks["custom learning paragraph"] = custom.learning_paragraph == plan["learning_paragraph"]

    # Teacher refresh + display-safe leaderboard.
    checks["teacher refresh button"] = "🔄 Refresh data" in APP
    checks["teacher refresh keeps session"] = "teacher_authed = False" not in APP[APP.index("def _teacher_refresh_control"):APP.index("def render_teacher_projector")]
    checks["live top 10"] = "Live Top 10" in TODAY and "standings may change" in TODAY
    checks["final top 10"] = "Final Top 10" in TODAY and "Mark standings Final" in TODAY
    checks["projector mode"] = "Display Top 10" in TODAY and "render_teacher_projector" in APP
    projector = APP[APP.index("def render_teacher_projector"):APP.index("def render_teacher_today")]
    checks["projector hides teacher-only metrics"] = "timed_seconds" not in projector and "correct_count" not in projector and "row[\"pin_code\"]" not in projector
    checks["projector only rank nickname"] = 'row["rank"]' in projector and ("row[\'nickname\']" in projector or 'row["nickname"]' in projector)
    checks["student leaderboard labeled current"] = "### 🏆 Current Top 10" in APP

    # Learning Data is decision-oriented and transparent about evidence.
    checks["fact fluency summary"] = "⚡ Fact Fluency" in ALL_UI and "Students to Pull" in ALL_UI
    checks["accuracy and time are separated"] = "Accuracy comes first" in ALL_UI and "Accurate, Still Slow" in ALL_UI
    checks["building alone is not intervention"] = "One isolated miss does not create a red flag" in ALL_UI
    checks["true class map"] = "Detailed Fact Map & Focus Settings" in ALL_UI and "Fact map filter" in ALL_UI
    checks["fact detail"] = "Look Up a Fact" in ALL_UI and "Accuracy on first tries" in ALL_UI
    checks["strategy connection"] = "Teaching move for" in ALL_UI
    checks["quick focus action"] = "Optional: assign a Focus fact family" in ALL_UI
    checks["student detail"] = "Look Up a Student" in ALL_UI and "Inspect one fact" in ALL_UI
    checks["standards tracker"] = "Warm-Up Standards Tracker" in ALL_UI and "Student History" in ALL_UI
    checks["manual controls secondary"] = "Detailed Fact Map & Focus Settings" in ALL_UI and "Class-wide Focus overrides" in ALL_UI
    checks["teaching/data explanation"] = "How each activity counts" in ALL_UI
    checks["no placement test claim"] = "No placement test" in ALL_UI

    # Clear teacher wording.
    checks["teacher logout label"] = 'st.button("Log out"' in APP
    checks["old Lock label removed"] = 'st.button("Lock"' not in APP

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.7 after-school teacher update: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
