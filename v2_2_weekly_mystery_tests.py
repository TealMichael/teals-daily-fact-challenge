from datetime import date, timedelta
from pathlib import Path

from fact_engine import CHALLENGE_VERSION, daily_facts_for_date
from fact_store import FactStoreError, InMemoryFactStore
from weekly_mystery import (
    MYSTERIES,
    default_mystery_key_for_week,
    is_correct_guess,
    mystery_bank_summary,
    mystery_for_key,
    next_mystery_key,
    normalize_guess,
    school_day_number,
    week_start_for,
)


def run():
    checks = 0

    assert len(MYSTERIES) == 80
    assert len({item.key for item in MYSTERIES}) == 80
    assert all(len(item.clues) == 4 and all(clue.strip() for clue in item.clues) for item in MYSTERIES)
    assert all(item.answer.strip() and item.reveal_note.strip() for item in MYSTERIES)
    for item in MYSTERIES:
        answer_text = normalize_guess(item.answer)
        assert all(answer_text not in normalize_guess(clue) for clue in item.clues)
    checks += 5

    summary = mystery_bank_summary()
    assert len(summary) == 8
    assert set(summary.values()) == {10}
    checks += 2

    # Guess normalization accepts punctuation/articles/accents through curated aliases.
    rubik = mystery_for_key("rubiks-cube")
    assert is_correct_guess(rubik, "The Rubik's Cube")
    beyonce = mystery_for_key("beyonce")
    assert is_correct_guess(beyonce, "Beyonce")
    assert normalize_guess("  THE   Grand-Canyon!! ") == "grand canyon"
    checks += 3

    # The default schedule cycles through all 80 mysteries before repeating.
    first_monday = date(2026, 8, 10)
    keys = [default_mystery_key_for_week(first_monday + timedelta(weeks=i)) for i in range(80)]
    assert len(set(keys)) == 80
    assert all(a != b for a, b in zip(keys, keys[1:]))
    checks += 2

    assert week_start_for(date(2026, 8, 13)) == date(2026, 8, 10)
    assert [school_day_number(date(2026, 8, 10) + timedelta(days=i)) for i in range(7)] == [1, 2, 3, 4, 5, None, None]
    checks += 2

    # Persistence contract: shared weekly mystery, swap before first clue, then lock.
    store = InMemoryFactStore()
    cls = store.create_class("Period 1")
    student = store.create_student(cls.class_id, "Falcon", "2468")
    week = date(2026, 8, 10)
    monday_facts = daily_facts_for_date(week)
    challenge = store.get_or_create_challenge(week, CHALLENGE_VERSION, monday_facts)
    initial_key = default_mystery_key_for_week(week)
    record = store.get_or_create_weekly_mystery(week, initial_key)
    assert record.mystery_key == initial_key
    replacement = next_mystery_key(initial_key)
    record = store.replace_weekly_mystery(week, replacement)
    assert record.mystery_key == replacement and not store.weekly_mystery_locked(week)
    checks += 2

    unlock = store.unlock_mystery_day(student.student_id, week, 1, challenge.challenge_id)
    assert unlock.day_number == 1
    assert store.unlock_mystery_day(student.student_id, week, 1, challenge.challenge_id) == unlock
    assert store.weekly_mystery_locked(week)
    try:
        store.replace_weekly_mystery(week, next_mystery_key(replacement))
        raise AssertionError("Replacement should be blocked after a clue unlock")
    except FactStoreError:
        pass
    checks += 4

    # Thursday and Friday are separate guess slots; each slot is immutable.
    thu1 = store.submit_mystery_guess(student.student_id, week, "first idea", correct=False, clue_count=1, guess_day=4)
    thu2 = store.submit_mystery_guess(student.student_id, week, "replacement", correct=True, clue_count=2, guess_day=4)
    assert thu2 == thu1
    fri = store.submit_mystery_guess(student.student_id, week, "second idea", correct=True, clue_count=1, guess_day=5)
    assert fri.guess_day == 5 and fri.correct
    guesses = store.list_mystery_guesses(student.student_id, week)
    assert [row.guess_day for row in guesses] == [4, 5]
    assert store.get_mystery_guess(student.student_id, week, guess_day=4).guess_text == "first idea"
    assert store.mystery_student_stats(student.student_id) == {"guesses": 2, "solved": 1, "earliest_solve": 1}
    stats = store.weekly_mystery_teacher_stats(week)
    assert stats == {"students_unlocked": 1, "clues_unlocked": 1, "guesses": 2, "correct": 1}
    checks += 7

    # A different student can solve Thursday and earns a private solve stat.
    student2 = store.create_student(cls.class_id, "Hawk", "1357")
    store.unlock_mystery_day(student2.student_id, week, 1, challenge.challenge_id)
    solved = store.submit_mystery_guess(student2.student_id, week, "right", correct=True, clue_count=1, guess_day=4)
    assert solved.correct and solved.guess_day == 4
    assert store.mystery_student_stats(student2.student_id)["earliest_solve"] == 1
    checks += 2

    app = Path("app.py").read_text(encoding="utf-8")
    schema = Path("SUPABASE_SCHEMA.sql").read_text(encoding="utf-8").lower()
    migration = Path("RUN_THIS_ONCE_IN_SUPABASE_v2_2.sql").read_text(encoding="utf-8").lower()
    backend = Path("supabase_fact_store.py").read_text(encoding="utf-8")
    migration25 = Path("RUN_THIS_ONCE_IN_SUPABASE_v2_5.sql").read_text(encoding="utf-8").lower()
    assert "render_weekly_mystery_reward(store, day, challenge)" in app
    assert "Guess #1 of 2 — Thursday" in app and "Guess #2 of 2 — Friday" in app
    assert "Friday never" in app and "backfill" in app
    assert "Weekly Mystery" in app and "Pick another mystery" in app
    assert "weekly_mysteries" in schema and "weekly_mystery_unlocks" in schema and "weekly_mystery_guesses" in schema
    assert "guess_day smallint not null" in schema and "primary key (student_id, week_start, guess_day)" in schema
    assert "create table if not exists public.weekly_mysteries" in migration
    assert "add column if not exists guess_day" in migration25 and "guess_day in (4, 5)" in migration25
    assert "def replace_weekly_mystery" in backend and "def list_mystery_guesses" in backend and "guess_day" in backend
    checks += 9

    print(f"v2_2_weekly_mystery_tests: PASS ({checks} current Weekly Mystery checks)")


if __name__ == "__main__":
    run()
