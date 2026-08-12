from datetime import date, datetime, timedelta, timezone

from fact_engine import CHALLENGE_VERSION, daily_facts_for_date
from fact_store import InMemoryFactStore


def run():
    store = InMemoryFactStore()
    classes = [store.create_class(f"Period {i}", f"ABC2{i}{i}") for i in range(1, 4)]
    created = 0
    for class_index, class_record in enumerate(classes, start=1):
        for student_index in range(1, 31):
            store.create_student(class_record.class_id, f"P{class_index}Student{student_index:02d}", f"{student_index:04d}")
            created += 1
    assert created == 90
    assert all(len(store.list_students(c.class_id)) == 30 for c in classes)

    day = date(2026, 8, 12)
    facts = daily_facts_for_date(day)
    challenge = store.get_or_create_challenge(day, CHALLENGE_VERSION, facts)
    t0 = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)

    # Complete 15 students in Period 1. Students should only get a Top 10,
    # while teacher status retains all 30 rows.
    students = store.list_students(classes[0].class_id)
    for index, student in enumerate(students[:15]):
        attempt = store.get_or_create_attempt(student.student_id, challenge.challenge_id)
        values = [fact.product for fact in facts]
        if index >= 12:
            values[0] += 1
        if index in {10, 11, 12, 13, 14}:
            values[-1] += 1
        store.complete_full_attempt(
            attempt.attempt_id,
            list(zip(facts, values)),
            15 + index,
            completed_at=t0 + timedelta(seconds=15 + index),
        )

    board = store.leaderboard(classes[0].class_id, challenge.challenge_id, limit=10)
    assert len(board) == 10
    assert [row["rank"] for row in board] == list(range(1, 11))
    status = store.daily_status(classes[0].class_id, challenge.challenge_id)
    assert len(status) == 30
    assert sum(row["status"] == "Complete" for row in status) == 15
    assert sum(row["status"] == "Not started" for row in status) == 15

    # A slower perfect result outranks a faster 9/10 result.
    for i in range(len(board) - 1):
        left, right = board[i], board[i + 1]
        assert left["correct_count"] > right["correct_count"] or (
            left["correct_count"] == right["correct_count"] and left["timed_seconds"] <= right["timed_seconds"]
        )

    print("teacher_workflow_tests: PASS (3 classes, 90 students, Top-10 privacy, full teacher status)")


if __name__ == "__main__":
    run()
