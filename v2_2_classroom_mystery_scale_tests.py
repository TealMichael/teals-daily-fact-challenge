from datetime import date, timedelta

from fact_engine import CHALLENGE_VERSION, daily_facts_for_date
from fact_store import InMemoryFactStore
from weekly_mystery import default_mystery_key_for_week


def run():
    store = InMemoryFactStore()
    classes = [store.create_class(f"Class {i}") for i in range(1, 4)]
    students = []
    for class_index, cls in enumerate(classes, start=1):
        for student_index in range(30):
            students.append(store.create_student(cls.class_id, f"C{class_index} Student {student_index+1}", f"{class_index}{student_index:03d}"[-4:]))

    week = date(2026, 8, 10)
    mystery = store.get_or_create_weekly_mystery(week, default_mystery_key_for_week(week))
    challenges = []
    for offset in range(5):
        day = week + timedelta(days=offset)
        challenges.append(store.get_or_create_challenge(day, CHALLENGE_VERSION, daily_facts_for_date(day)))

    # All 90 students complete all five routines and therefore persist five
    # weekly-reward unlocks. Each gets only one guess regardless of rerenders.
    expected_correct = 0
    for index, student in enumerate(students):
        for day_number, challenge in enumerate(challenges, start=1):
            store.unlock_mystery_day(student.student_id, week, day_number, challenge.challenge_id)
        clue_count = (index % 5) + 1
        correct = index % 2 == 0
        expected_correct += int(correct)
        first = store.submit_mystery_guess(student.student_id, week, f"Guess {index}", correct=correct, clue_count=clue_count)
        again = store.submit_mystery_guess(student.student_id, week, "Replacement", correct=not correct, clue_count=5)
        assert again == first

    stats = store.weekly_mystery_teacher_stats(week)
    assert stats["students_unlocked"] == 90
    assert stats["clues_unlocked"] == 450
    assert stats["guesses"] == 90
    assert stats["correct"] == expected_correct == 45
    assert store.weekly_mystery_locked(week)
    assert store.get_weekly_mystery(week).mystery_key == mystery.mystery_key

    # Private lifetime mystery statistics remain per student, never a class rank.
    assert store.mystery_student_stats(students[0].student_id)["solved"] == 1
    assert store.mystery_student_stats(students[1].student_id)["solved"] == 0

    print("v2_2_classroom_mystery_scale_tests: PASS (3 classes × 30 students × 5 unlocks; one private guess each)")


if __name__ == "__main__":
    run()
