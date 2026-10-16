from datetime import date, timedelta

from adaptive_engine import (
    FOCUS_SESSION_LENGTH,
    STATUS_BUILDING,
    STATUS_FLUENT,
    STATUS_FOCUS,
    STATUS_UNKNOWN,
    MasterySnapshot,
    build_focus_plan,
    mastery_counts,
    update_snapshot,
)
from fact_engine import Fact, daily_facts_for_date
from fact_store import InMemoryFactStore


def next_weekday(day: date) -> date:
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def run():
    checks = 0

    # New students start with no forced assessment and no fabricated evidence.
    store = InMemoryFactStore()
    cls = store.create_class("Period 1", "ABC234")
    student = store.create_student(cls.class_id, "FalconFox", "2468")
    assert store.get_mastery(student.student_id) == []
    summary = store.mastery_summary(student.student_id)
    assert summary == {"Fluent": 0, "Building": 0, "Focus": 0, "Unknown": 45}
    checks += 2

    # A fact profile develops gradually from independent retrievals.
    snap = None
    for correct, seconds in [(False, 8.0), (True, 5.5), (True, 4.5), (True, 3.5), (True, 3.0)]:
        snap = update_snapshot(snap, a=7, b=8, correct=correct, response_seconds=seconds)
    assert snap.evidence_count == 5 and snap.correct_count == 4
    assert snap.status in {STATUS_BUILDING, STATUS_FLUENT}
    checks += 2

    weak = update_snapshot(None, a=6, b=7, correct=False, response_seconds=10)
    weak = update_snapshot(weak, a=6, b=7, correct=False, response_seconds=9)
    assert weak.status == STATUS_FOCUS
    checks += 1

    # A first personalized plan needs no placement test, contains exactly eight
    # retrievals, and avoids immediate identical repeats.
    plan = build_focus_plan([], student_id=student.student_id, date_key="2026-08-13")
    assert len(plan) == FOCUS_SESSION_LENGTH
    assert all(plan[i].key != plan[i + 1].key for i in range(len(plan) - 1))
    assert all(2 <= min(f.key) <= max(f.key) <= 10 for f in plan)
    checks += 3

    # Teacher override narrows the target family but still spaces targets with
    # maintenance/exploration facts when useful.
    six_plan = build_focus_plan([], student_id=student.student_id, date_key="2026-08-13", override_family=6)
    assert len(six_plan) == 8
    assert sum(6 in fact.key for fact in six_plan) >= 6
    assert all(six_plan[i].key != six_plan[i + 1].key for i in range(7))
    checks += 3

    # Daily Challenge itself creates the first real mastery evidence. Fact 1 is
    # deliberately accuracy-only; Facts 2-10 may carry response-time evidence.
    day1 = date(2026, 8, 13)
    facts1 = daily_facts_for_date(day1)
    challenge1 = store.get_or_create_challenge(day1, "TDFC-DAILY-v1", facts1)
    attempt1 = store.get_or_create_attempt(student.student_id, challenge1.challenge_id)
    values = [fact.product for fact in facts1]
    values[1] += 1
    store.complete_full_attempt(
        attempt1.attempt_id,
        list(zip(facts1, values)),
        42.0,
        response_seconds=[None] + [3.0 + i / 10 for i in range(9)],
    )
    core_daily = {fact.key for fact in facts1 if max(fact.key) <= 10}
    evidence = store.get_mastery(student.student_id)
    assert {row.key for row in evidence} == core_daily
    answers = store.get_answers(attempt1.attempt_id)
    assert answers[0].response_seconds is None and answers[1].response_seconds is not None
    checks += 2

    # Fix Your Misses is teaching, not a second mastery observation.
    missed_fact = facts1[1]
    before = {row.key: row.evidence_count for row in store.get_mastery(student.student_id)}
    store.record_practice(
        student.student_id, "Fix Your Misses", missed_fact, missed_fact.product,
        challenge_id=challenge1.challenge_id, activity_type="fix_miss", activity_index=2,
        is_retry=True, count_for_mastery=False,
    )
    after = {row.key: row.evidence_count for row in store.get_mastery(student.student_id)}
    assert before == after
    store.mark_fix_complete(student.student_id, challenge1.challenge_id)
    checks += 2

    # Assigned Focus first tries update mastery; correction retries do not.
    focus_plan = build_focus_plan(
        store.get_mastery(student.student_id),
        student_id=student.student_id,
        date_key=day1.isoformat(),
        recent_daily_misses=[missed_fact.key],
    )
    store.set_focus_plan(student.student_id, challenge1.challenge_id, focus_plan)
    first_fact = focus_plan[0]
    old_count = next((r.evidence_count for r in store.get_mastery(student.student_id) if r.key == first_fact.key), 0)
    store.record_practice(
        student.student_id, "My Focus Facts", first_fact, first_fact.product + 1,
        response_seconds=4.0, challenge_id=challenge1.challenge_id, activity_type="focus",
        activity_index=0, is_retry=False, count_for_mastery=True,
    )
    count_after_first = next(r.evidence_count for r in store.get_mastery(student.student_id) if r.key == first_fact.key)
    store.record_practice(
        student.student_id, "My Focus Facts", first_fact, first_fact.product,
        challenge_id=challenge1.challenge_id, activity_type="focus",
        activity_index=0, is_retry=True, count_for_mastery=False,
    )
    count_after_retry = next(r.evidence_count for r in store.get_mastery(student.student_id) if r.key == first_fact.key)
    assert count_after_first == old_count + 1
    assert count_after_retry == count_after_first
    checks += 2

    # Finish remaining Focus items and earn exactly one Star for the completed
    # full routine—not for merely finishing the competitive Daily 10.
    for i, fact in enumerate(focus_plan[1:], start=1):
        store.record_practice(
            student.student_id, "My Focus Facts", fact, fact.product,
            response_seconds=3.0, challenge_id=challenge1.challenge_id, activity_type="focus",
            activity_index=i, is_retry=False, count_for_mastery=True,
        )
    store.mark_focus_complete(student.student_id, challenge1.challenge_id)
    stats = store.student_learning_stats(student.student_id, day1)
    assert stats == {"current_streak": 1, "longest_streak": 1, "stars": 1}
    checks += 1

    # Streaks follow assigned weekday Challenge days, so Friday -> Monday
    # continues rather than breaking for the weekend.
    day2 = next_weekday(day1)
    day3 = next_weekday(day2)
    for day in (day2, day3):
        facts = daily_facts_for_date(day)
        ch = store.get_or_create_challenge(day, "TDFC-DAILY-v1", facts)
        store.get_or_create_learning_progress(student.student_id, ch.challenge_id)
        store.mark_fix_complete(student.student_id, ch.challenge_id)
        store.set_focus_plan(student.student_id, ch.challenge_id, build_focus_plan(store.get_mastery(student.student_id), student_id=student.student_id, date_key=day.isoformat()))
        store.mark_focus_complete(student.student_id, ch.challenge_id)
    stats = store.student_learning_stats(student.student_id, day3)
    assert stats["current_streak"] == 3 and stats["longest_streak"] == 3 and stats["stars"] == 3
    checks += 1


    # A teacher reset removes that day's learning activity and rebuilds mastery
    # from the remaining saved history, preventing double-counted evidence.
    before_reset_evidence = sum(row.evidence_count for row in store.get_mastery(student.student_id))
    assert store.reset_daily_attempt(student.student_id, challenge1.challenge_id)
    assert store.get_attempt_for_student(student.student_id, challenge1.challenge_id) is None
    assert store.get_learning_progress(student.student_id, challenge1.challenge_id).completed_at is None
    after_reset_evidence = sum(row.evidence_count for row in store.get_mastery(student.student_id))
    assert after_reset_evidence < before_reset_evidence
    checks += 4

    # Override specificity: student > class > all-student.
    store.set_global_focus_override(4)
    assert store.get_effective_focus_override(student.student_id) == 4
    store.set_class_focus_override(cls.class_id, 6)
    assert store.get_effective_focus_override(student.student_id) == 6
    store.set_student_focus_override(student.student_id, 8)
    assert store.get_effective_focus_override(student.student_id) == 8
    store.set_student_focus_override(student.student_id, None)
    assert store.get_effective_focus_override(student.student_id) == 6
    checks += 4

    print(f"adaptive_learning_tests: PASS ({checks} gradual-mastery/adaptive-flow checks)")


if __name__ == "__main__":
    run()
