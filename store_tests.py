from datetime import date, datetime, timedelta, timezone

from fact_engine import CHALLENGE_VERSION, daily_facts_for_date
from fact_store import InMemoryFactStore, NameTaken, hash_pin, verify_pin


def run():
    checks = 0
    encoded = hash_pin("1234")
    assert "1234" not in encoded and verify_pin("1234", encoded) and not verify_pin("9999", encoded)
    checks += 1

    store = InMemoryFactStore()
    c1 = store.create_class("Period 1", "ABC234")
    c2 = store.create_class("Period 2", "DEF567")
    checks += 1

    alice = store.create_student(c1.class_id, "Falcon", "1234")
    same_other_class = store.create_student(c2.class_id, "Falcon", "5678")
    assert store.authenticate_student(c1.class_id, "falcon", "1234") == alice
    assert store.authenticate_student(c1.class_id, "Falcon", "9999") is None
    assert store.authenticate_student(c2.class_id, "Falcon", "5678") == same_other_class
    checks += 1

    try:
        store.create_student(c1.class_id, "FALCON", "2222")
        raise AssertionError("duplicate nickname should fail")
    except NameTaken:
        pass
    checks += 1

    day = date(2026, 8, 12)
    facts = daily_facts_for_date(day)
    challenge = store.get_or_create_challenge(day, CHALLENGE_VERSION, facts)
    attempt = store.get_or_create_attempt(alice.student_id, challenge.challenge_id)
    t0 = datetime(2026, 8, 12, 14, 0, 0, tzinfo=timezone.utc)
    attempt = store.submit_first_answer(attempt.attempt_id, facts[0], facts[0].product, submitted_at=t0)
    assert attempt.timed_started_at == t0
    assert len(store.get_answers(attempt.attempt_id)) == 1
    checks += 1

    remaining = [(fact, fact.product) for fact in facts[1:]]
    done = store.complete_attempt(attempt.attempt_id, remaining, completed_at=t0 + timedelta(seconds=32.4))
    assert done.correct_count == 10 and abs(done.timed_seconds - 32.4) < 1e-9
    assert len(store.get_answers(attempt.attempt_id)) == 10
    checks += 1

    # Accuracy must beat speed.
    bob = store.create_student(c1.class_id, "Speedy", "1111")
    bob_attempt = store.get_or_create_attempt(bob.student_id, challenge.challenge_id)
    store.submit_first_answer(bob_attempt.attempt_id, facts[0], facts[0].product, submitted_at=t0)
    bob_remaining = [(fact, fact.product) for fact in facts[1:]]
    bob_remaining[-1] = (facts[-1], facts[-1].product + 1)
    store.complete_attempt(bob_attempt.attempt_id, bob_remaining, completed_at=t0 + timedelta(seconds=10))
    board = store.leaderboard(c1.class_id, challenge.challenge_id)
    assert board[0]["student_id"] == alice.student_id
    assert board[1]["student_id"] == bob.student_id
    checks += 1

    # Among equal accuracy, faster time wins.
    cara = store.create_student(c1.class_id, "QuickPerfect", "2222")
    cara_attempt = store.get_or_create_attempt(cara.student_id, challenge.challenge_id)
    store.submit_first_answer(cara_attempt.attempt_id, facts[0], facts[0].product, submitted_at=t0)
    store.complete_attempt(cara_attempt.attempt_id, remaining, completed_at=t0 + timedelta(seconds=20))
    board = store.leaderboard(c1.class_id, challenge.challenge_id)
    assert board[0]["student_id"] == cara.student_id
    assert board[1]["student_id"] == alice.student_id
    checks += 1

    # Browser component path: all 10 answers + client-measured timed sprint arrive together.
    dana = store.create_student(c1.class_id, "ComponentKid", "3333")
    dana_attempt = store.get_or_create_attempt(dana.student_id, challenge.challenge_id)
    full_values = [(fact, fact.product) for fact in facts]
    dana_done = store.complete_full_attempt(
        dana_attempt.attempt_id, full_values, 18.75, completed_at=t0 + timedelta(seconds=50)
    )
    assert dana_done.correct_count == 10 and abs(dana_done.timed_seconds - 18.75) < 1e-9
    assert len(store.get_answers(dana_attempt.attempt_id)) == 10
    checks += 1

    assert store.reset_daily_attempt(bob.student_id, challenge.challenge_id)
    assert store.get_attempt_for_student(bob.student_id, challenge.challenge_id) is None
    checks += 1

    store.reset_student_pin(alice.student_id, "4321")
    assert store.authenticate_student(c1.class_id, "Falcon", "1234") is None
    assert store.authenticate_student(c1.class_id, "Falcon", "4321") == alice
    checks += 1

    store.rename_student(alice.student_id, "TealFalcon")
    assert store.authenticate_student(c1.class_id, "TealFalcon", "4321") is not None
    checks += 1

    store.set_student_active(alice.student_id, False)
    assert store.authenticate_student(c1.class_id, "TealFalcon", "4321") is None
    checks += 1

    print(f"store_tests: PASS ({checks}/13 core workflow checks)")


if __name__ == "__main__":
    run()
