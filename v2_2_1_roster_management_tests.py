from datetime import date

from fact_engine import CHALLENGE_VERSION, Fact, daily_facts_for_date
from fact_store import InMemoryFactStore, NameTaken, NotFound


def run():
    store = InMemoryFactStore()
    block1 = store.create_class("Block 1", "ABC221")
    block2 = store.create_class("Block 2", "ABC222")
    block3 = store.create_class("Block 3", "ABC223")

    # Moving a student keeps the same account/PIN and changes which class owns the roster entry.
    moved = store.create_student(block1.class_id, "Blue Falcon", "2468")
    store.move_student(moved.student_id, block2.class_id)
    assert moved.student_id not in {s.student_id for s in store.list_students(block1.class_id, include_inactive=True)}
    assert moved.student_id in {s.student_id for s in store.list_students(block2.class_id, include_inactive=True)}
    assert store.authenticate_student(block1.class_id, "Blue Falcon", "2468") is None
    auth = store.authenticate_student(block2.class_id, "Blue Falcon", "2468")
    assert auth is not None and auth.student_id == moved.student_id and auth.pin_code == "2468"

    # Bulk-style moves can preserve several accounts without recreating them.
    bulk = [store.create_student(block1.class_id, f"Student {i}", f"{3000+i}") for i in range(1, 6)]
    for student in bulk:
        store.move_student(student.student_id, block2.class_id)
    assert all(student.student_id in {s.student_id for s in store.list_students(block2.class_id)} for student in bulk)

    # A duplicate nickname in the destination class is blocked instead of overwriting anyone.
    conflict_source = store.create_student(block1.class_id, "Same Name", "4001")
    store.create_student(block3.class_id, "Same Name", "4002")
    try:
        store.move_student(conflict_source.student_id, block3.class_id)
        raise AssertionError("Expected destination nickname conflict")
    except NameTaken:
        pass
    assert store.get_student(conflict_source.student_id).class_id == block1.class_id

    # Deletion is permanent and cleans student-linked in-memory learning data.
    doomed = store.create_student(block1.class_id, "Accidental Entry", "5555")
    day = date(2026, 8, 13)
    facts = daily_facts_for_date(day)
    challenge = store.get_or_create_challenge(day, CHALLENGE_VERSION, facts)
    attempt = store.get_or_create_attempt(doomed.student_id, challenge.challenge_id)
    store.complete_full_attempt(
        attempt.attempt_id,
        [(fact, fact.product) for fact in facts],
        20.0,
    )
    store.record_practice(
        doomed.student_id,
        "Mixed Facts",
        Fact(6, 7, "hard"),
        42,
        response_seconds=2.0,
        challenge_id=challenge.challenge_id,
        activity_type="focus",
        activity_index=1,
        count_for_mastery=True,
    )
    store.set_student_focus_override(doomed.student_id, 7)
    assert store.get_mastery(doomed.student_id)
    store.delete_student(doomed.student_id)
    try:
        store.get_student(doomed.student_id)
        raise AssertionError("Deleted student still exists")
    except NotFound:
        pass
    assert not any(a.student_id == doomed.student_id for a in store.attempts.values())
    assert not any(row.student_id == doomed.student_id for row in store.practice)
    assert not any(key[0] == doomed.student_id for key in store.mastery)
    assert doomed.student_id not in store.student_focus_overrides

    # Static production/UI protections: real Supabase store and teacher controls exist.
    backend = open("supabase_fact_store.py", encoding="utf-8").read()
    ui = open("app.py", encoding="utf-8").read()
    assert "def move_student(" in backend and '.update({"class_id": str(new_class_id)})' in backend
    assert "def delete_student(" in backend and '.delete()' in backend
    assert "Move selected student(s)" in ui and "Roster Management" in ui
    assert "Move student" in ui
    assert "Delete student permanently" in ui
    assert "Permanent: removes this account" in ui

    print("v2_2_1_roster_management_tests: PASS (move, bulk move, duplicate protection, permanent delete, teacher UI)")


if __name__ == "__main__":
    run()
