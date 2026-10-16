from datetime import date
import random

from adaptive_engine import build_focus_plan
from fact_engine import daily_facts_for_date
from fact_store import InMemoryFactStore


def run():
    store = InMemoryFactStore()
    classes = []
    for class_index in range(3):
        record = store.create_class(f"Period {class_index + 1}", f"C{class_index + 2}D345")
        classes.append(record)
        for student_index in range(30):
            store.create_student(
                record.class_id,
                f"P{class_index + 1}S{student_index + 1}",
                f"{class_index * 30 + student_index:04d}",
            )

    day = date(2026, 8, 13)
    facts = daily_facts_for_date(day)
    challenge = store.get_or_create_challenge(day, "TDFC-DAILY-v1", facts)
    rng = random.Random(20260813)

    for class_record in classes:
        for student in store.list_students(class_record.class_id):
            attempt = store.get_or_create_attempt(student.student_id, challenge.challenge_id)
            answers = [
                fact.product if rng.random() < 0.86 else fact.product + 1
                for fact in facts
            ]
            store.complete_full_attempt(
                attempt.attempt_id,
                list(zip(facts, answers)),
                rng.uniform(22, 65),
                response_seconds=[None] + [rng.uniform(1.5, 7.5) for _ in range(9)],
            )
            daily_rows = store.get_answers(attempt.attempt_id)
            misses = []
            for daily_row, fact in zip(daily_rows, facts):
                if not daily_row.correct:
                    misses.append(fact.key)
                    store.record_practice(
                        student.student_id, "Fix Your Misses", fact, fact.product,
                        challenge_id=challenge.challenge_id, activity_type="fix_miss",
                        activity_index=daily_row.question_number, is_retry=True,
                    )
            store.mark_fix_complete(student.student_id, challenge.challenge_id)
            plan = build_focus_plan(
                store.get_mastery(student.student_id),
                student_id=student.student_id,
                date_key=day.isoformat(),
                recent_daily_misses=misses,
            )
            store.set_focus_plan(student.student_id, challenge.challenge_id, plan)
            for index, fact in enumerate(plan):
                first_value = fact.product if rng.random() < 0.82 else fact.product + 1
                first = store.record_practice(
                    student.student_id, "My Focus Facts", fact, first_value,
                    response_seconds=rng.uniform(1.5, 7.5), challenge_id=challenge.challenge_id,
                    activity_type="focus", activity_index=index, is_retry=False,
                    count_for_mastery=True,
                )
                if not first.correct:
                    store.record_practice(
                        student.student_id, "My Focus Facts", fact, fact.product,
                        challenge_id=challenge.challenge_id, activity_type="focus",
                        activity_index=index, is_retry=True, count_for_mastery=False,
                    )
            store.mark_focus_complete(student.student_id, challenge.challenge_id)

    assert len(store.students) == 90
    for class_record in classes:
        assert len(store.leaderboard(class_record.class_id, challenge.challenge_id)) == 10
        assert len(store.class_mastery_summary(class_record.class_id)) == 45
        stats = store.class_learning_stats(class_record.class_id, day)
        assert len(stats) == 30
        assert all(row["stars"] == 1 and row["current_streak"] == 1 for row in stats.values())
        progress = store.class_learning_progress(class_record.class_id, challenge.challenge_id)
        assert len(progress) == 30 and all(row.completed_at is not None for row in progress.values())

    print("v2_classroom_scale_tests: PASS (3 classes × 30 students; Daily + adaptive routine + private Top 10)")


if __name__ == "__main__":
    run()
