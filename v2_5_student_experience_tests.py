from datetime import date, timedelta
from pathlib import Path

from fact_engine import APP_VERSION, CHALLENGE_VERSION, daily_facts_for_date
from fact_store import InMemoryFactStore
from weekly_mystery import default_mystery_key_for_week

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
DAILY = (ROOT / "daily_sprint_component" / "index.html").read_text(encoding="utf-8")
PAD = (ROOT / "answer_pad_component" / "index.html").read_text(encoding="utf-8")
MIGRATION = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_5.sql").read_text(encoding="utf-8").lower()
SCHEMA = (ROOT / "SUPABASE_SCHEMA.sql").read_text(encoding="utf-8").lower()


def run():
    checks = {}
    checks["version 2.6"] = APP_VERSION == "2.11.0.1"

    # Touch keypad: digit taps are local browser state; Streamlit receives one
    # component value only when ✓ is submitted.
    checks["daily has touch keypad"] = all(x in DAILY for x in ['data-digit="1"', 'data-digit="0"', '⌫', '✓'])
    checks["daily avoids mobile keyboard"] = "<input" not in DAILY.lower()
    checks["daily keypad supports hardware keyboard"] = "document.addEventListener('keydown'" in DAILY
    checks["daily digit taps local"] = "addDigit" in DAILY and "setValue(payload)" in DAILY
    checks["shared pad exists"] = all(x in PAD for x in ['data-digit="1"', 'data-digit="0"', '⌫', '✓'])
    checks["shared pad avoids mobile keyboard"] = "<input" not in PAD.lower()
    checks["shared pad submits once"] = "submitted = true" in PAD and "setValue({answer:value" in PAD
    checks["shared pad returns local latency"] = "response_seconds" in PAD and "performance.now()" in PAD
    checks["fix uses guided touch session"] = 'mode="fix"' in APP and 'guided_fix_' in APP
    checks["focus uses guided touch session"] = 'mode="focus"' in APP and 'guided_focus_' in APP
    checks["guided session preserves touch input"] = 'GUIDED_PRACTICE_COMPONENT' in APP
    checks["optional practice uses guided coach"] = 'guided_free_practice_' in APP and 'mode="practice"' in APP
    checks["legacy multiplication answer forms removed"] = 'text_input("Answer"' not in APP

    # Top 10 is displayed immediately using the already-cached context, then
    # hidden on later Fix/Focus reruns so it does not create scrolling/noise.
    checks["cached top 10 displayed"] = "context=leaderboard_context" in APP
    checks["top 10 only once per session"] = "student_top10_seen_" in APP
    checks["student leaderboard privacy retained"] = '"correct_count"' not in APP[APP.index("def load_leaderboard_context"):APP.index("def _leaderboard_cache_key")]

    # Finish screen is intentionally short; detail is optional/collapsed.
    checks["clear done banner"] = "YOU'RE DONE FOR TODAY!" in APP
    checks["mystery centered as reward"] = "Today's Mystery Reward" in APP
    checks["growth lazy"] = 'st.toggle("🌱 See My Growth"' in APP and 'if show_growth:' in APP
    checks["daily review collapsed"] = 'with st.expander("📝 Review My Daily 10"' in APP
    day_complete = APP[APP.index("def render_day_complete"):APP.index("def render_classroom_connection_retry")]
    checks["no automatic final leaderboard reload"] = "render_leaderboard(" not in day_complete

    # Mystery: only earned Mon-Thu clues, Thursday guess, Friday guess/reveal.
    checks["thursday guess only"] = "Guess #1 of 2 — Thursday" in APP
    checks["friday guess only"] = "Guess #2 of 2 — Friday" in APP
    checks["Friday earns one real clue"] = "One clue is earned for each completed school day, including Friday" in APP and "never grants clues for skipped days" in APP
    checks["Friday optional reveal"] = "Reveal without using my Friday guess" in APP
    checks["migration adds guess day"] = "add column if not exists guess_day" in MIGRATION
    checks["migration two guess slots"] = "guess_day in (4, 5)" in MIGRATION and "primary key (student_id, week_start, guess_day)" in MIGRATION
    checks["fresh schema two guess slots"] = "guess_day smallint not null" in SCHEMA and "primary key (student_id, week_start, guess_day)" in SCHEMA

    # Persistence behavior, including skipped clue days.
    store = InMemoryFactStore()
    cls = store.create_class("Block 1")
    student = store.create_student(cls.class_id, "Falcon", "1234")
    week = date(2026, 8, 10)
    store.get_or_create_weekly_mystery(week, default_mystery_key_for_week(week))
    challenges = {}
    for day_offset in range(5):
        day = week + timedelta(days=day_offset)
        challenges[day_offset + 1] = store.get_or_create_challenge(day, CHALLENGE_VERSION, daily_facts_for_date(day))

    # Complete only Monday, Thursday, Friday. Friday does not manufacture Tue/Wed clues.
    for d in (1, 4, 5):
        store.unlock_mystery_day(student.student_id, week, d, challenges[d].challenge_id)
    unlocks = store.list_mystery_unlocks(student.student_id, week)
    earned_clues = sum(1 for row in unlocks if row.day_number <= 5)
    checks["skipped days mean fewer clues"] = earned_clues == 3

    thu = store.submit_mystery_guess(student.student_id, week, "Thursday idea", correct=False, clue_count=2, guess_day=4)
    fri = store.submit_mystery_guess(student.student_id, week, "Friday idea", correct=True, clue_count=3, guess_day=5)
    checks["two persistent guess slots"] = [g.guess_day for g in store.list_mystery_guesses(student.student_id, week)] == [4, 5]
    checks["Thursday and Friday distinct"] = thu.guess_text != fri.guess_text
    duplicate_thu = store.submit_mystery_guess(student.student_id, week, "replace", correct=True, clue_count=2, guess_day=4)
    checks["each slot immutable"] = duplicate_thu == thu
    try:
        store.submit_mystery_guess(student.student_id, week, "too early", correct=False, clue_count=1, guess_day=3)
    except ValueError:
        early_blocked = True
    else:
        early_blocked = False
    checks["Mon-Wed guess blocked in store"] = early_blocked

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.5 student experience: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
