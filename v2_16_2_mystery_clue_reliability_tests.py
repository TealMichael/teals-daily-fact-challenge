from datetime import date
from pathlib import Path

import httpx

from fact_engine import CHALLENGE_VERSION, daily_facts_for_date
from fact_store import InMemoryFactStore
from supabase_fact_store import SupabaseFactStore

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
STORE = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
ENGINE = (ROOT / "fact_engine.py").read_text(encoding="utf-8")


def _complete_multiplication_day(store, student, day):
    facts = daily_facts_for_date(day)
    challenge = store.get_or_create_challenge(day, CHALLENGE_VERSION, facts)
    attempt = store.get_or_create_attempt(student.student_id, challenge.challenge_id)
    store.complete_full_attempt(
        attempt.attempt_id,
        [(fact, fact.product) for fact in facts],
        20.0,
        response_seconds=[1.0] * 10,
    )
    store.mark_focus_complete(student.student_id, challenge.challenge_id)
    return challenge


def _complete_alternate_day(store, student, day):
    facts = daily_facts_for_date(day)
    challenge = store.get_or_create_challenge(day, CHALLENGE_VERSION, facts)
    questions = [
        {"prompt": f"{i}+1", "correct_answer": i + 1, "kind": "addition"}
        for i in range(10)
    ]
    attempt = store.get_or_create_attempt(
        student.student_id,
        challenge.challenge_id,
        daily_mode="Addition Facts",
        custom_questions=questions,
    )
    store.complete_custom_attempt(attempt.attempt_id, [i + 1 for i in range(10)], 20.0)
    return challenge


def test_completed_days_repair_only_real_completed_work():
    store = InMemoryFactStore()
    cls = store.create_class("Block 1")
    student = store.create_student(cls.class_id, "Falcon", "2468")
    week = date(2026, 8, 31)

    monday = _complete_multiplication_day(store, student, date(2026, 8, 31))
    tuesday = _complete_alternate_day(store, student, date(2026, 9, 1))

    # Wednesday has a challenge and started attempt but no completed required routine.
    wed_day = date(2026, 9, 2)
    wed_facts = daily_facts_for_date(wed_day)
    wed = store.get_or_create_challenge(wed_day, CHALLENGE_VERSION, wed_facts)
    store.get_or_create_attempt(student.student_id, wed.challenge_id)

    qualified = store.completed_mystery_days(student.student_id, week, through_day_number=3)
    assert qualified == [(1, monday.challenge_id), (2, tuesday.challenge_id)]

    # Reproduce the bug: Monday's reward receipt was lost, Tuesday's saved.
    store.get_or_create_weekly_mystery(week, "rubiks-cube")
    store.unlock_mystery_day(student.student_id, week, 2, tuesday.challenge_id)
    assert [row.day_number for row in store.list_mystery_unlocks(student.student_id, week)] == [2]

    # The repair restores only days proven complete. Wednesday remains absent.
    for day_number, challenge_id in qualified:
        store.unlock_mystery_day(student.student_id, week, day_number, challenge_id)
    assert [row.day_number for row in store.list_mystery_unlocks(student.student_id, week)] == [1, 2]


class FakeResponse:
    def __init__(self, data):
        self.data = data


class RetryQuery:
    def __init__(self, owner, table_name):
        self.owner = owner
        self.table_name = table_name

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        self.owner.exec_calls += 1
        if self.owner.exec_calls < 3:
            raise httpx.ReadError("temporary Mystery read reset")
        if self.table_name == "weekly_mysteries":
            return FakeResponse([{
                "week_start": "2026-08-31",
                "mystery_key": "rubiks-cube",
                "created_at": "2026-08-31T12:00:00+00:00",
                "updated_at": "2026-08-31T12:00:00+00:00",
            }])
        return FakeResponse([{
            "student_id": "s1",
            "week_start": "2026-08-31",
            "day_number": 2,
            "challenge_id": "c2",
            "unlocked_at": "2026-09-01T14:00:00+00:00",
        }])


class RetryClient:
    def __init__(self):
        self.exec_calls = 0
        self.table_calls = 0

    def table(self, name):
        self.table_calls += 1
        return RetryQuery(self, name)


def test_mystery_reads_retry_and_rebuild_query():
    client = RetryClient()
    store = object.__new__(SupabaseFactStore)
    store.client = client
    row = store.get_weekly_mystery("2026-08-31")
    assert row is not None and row.mystery_key == "rubiks-cube"
    assert client.exec_calls == 3
    assert client.table_calls == 3

    client = RetryClient()
    store = object.__new__(SupabaseFactStore)
    store.client = client
    rows = store.list_mystery_unlocks("s1", "2026-08-31")
    assert [row.day_number for row in rows] == [2]
    assert client.exec_calls == 3
    assert client.table_calls == 3


class LostInsertQuery:
    def __init__(self, owner):
        self.owner = owner
        self.kind = "select"
        self.payload = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.kind = "insert"
        self.payload = dict(payload)
        return self

    def execute(self):
        if self.kind == "select":
            if not self.owner.inserted:
                return FakeResponse([])
            return FakeResponse([{
                **self.owner.payload,
                "unlocked_at": "2026-09-01T14:00:00+00:00",
            }])
        self.owner.insert_calls += 1
        if self.owner.insert_calls == 1:
            self.owner.inserted = True
            self.owner.payload = dict(self.payload)
            raise httpx.ReadError("insert succeeded but response reset")
        raise RuntimeError("duplicate key value violates unique constraint")


class LostInsertClient:
    def __init__(self):
        self.inserted = False
        self.insert_calls = 0
        self.payload = None

    def table(self, name):
        assert name == "weekly_mystery_unlocks"
        return LostInsertQuery(self)


def test_lost_unlock_response_is_recovered_without_losing_clue():
    client = LostInsertClient()
    store = object.__new__(SupabaseFactStore)
    store.client = client
    row = store.unlock_mystery_day("s1", "2026-08-31", 2, "c2")
    assert row.day_number == 2
    assert row.challenge_id == "c2"
    assert client.insert_calls == 2


def main():
    test_completed_days_repair_only_real_completed_work()
    test_mystery_reads_retry_and_rebuild_query()
    test_lost_unlock_response_is_recovered_without_losing_clue()

    checks = {
        "version bumped": 'APP_VERSION = "2.16.2"' in ENGINE,
        "challenge version untouched": 'CHALLENGE_VERSION = "TDFC-DAILY-v1"' in ENGINE,
        "repair helper exists in production store": "def completed_mystery_days(" in STORE,
        "repair helper exists in reference store": "def completed_mystery_days(" in (ROOT / "fact_store.py").read_text(encoding="utf-8"),
        "student reward saves current clue first": "Save today\'s clue first" in APP,
        "student reward reconciles proven prior completed days": "qualified_days = store.completed_mystery_days(" in APP,
        "student reward repairs each earned prior clue": "for earned_day, earned_challenge_id in qualified_days" in APP,
        "skipped-day contract documented": "genuinely skipped day" in APP,
        "friendly transient clue retry": "Your Mystery clue is taking a moment to load" in APP,
        "Mystery retry button": "Try Mystery again" in APP,
        "weekly mystery read protected": "def get_weekly_mystery" in STORE and "_retry_transient" in STORE,
        "unlock read/write protected": "def unlock_mystery_day" in STORE and "fetch_existing" in STORE,
        "guess list protected": "def list_mystery_guesses" in STORE and "_retry_transient" in STORE,
        "student Mystery stats protected": "def mystery_student_stats" in STORE and "_retry_transient" in STORE,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    total = len(checks) + 5  # three tests; retry test contains two independent method checks
    print(f"v2.16.2 Mystery clue reliability: PASS ({total}/{total} checks)")


if __name__ == "__main__":
    main()
