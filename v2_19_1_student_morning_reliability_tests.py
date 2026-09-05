from __future__ import annotations

"""v2.19.1 student-morning reliability/performance regression.

Targets only the new alternate-mode path. Multiplication is protected elsewhere by
v2.19/v2.18/v2.17 hash guards and must remain unchanged.
"""

from pathlib import Path
import httpx

import supabase_fact_store as sfs
from fact_engine import APP_VERSION
from supabase_fact_store import SupabaseFactStore

ROOT = Path(__file__).parent
STUDENT = (ROOT / "student_alt_daily_ui.py").read_text()
STORE = (ROOT / "supabase_fact_store.py").read_text()

checks: list[str] = []
def check(name: str, condition: bool):
    assert condition, name
    checks.append(name)

check("v2.19.1 version", APP_VERSION == "2.19.6")
check("alternate completed page mirrors multiplication evidence guard", 'daily_evidence_verified::{attempt.attempt_id}' in STUDENT)
check("alternate completed page uses daily evidence repair marker", 'store.ensure_daily_learning_evidence(attempt.attempt_id)' in STUDENT)
check("alternate completed page reads stored progress directly", 'store.get_alternate_learning_progress(' in STUDENT)
check("alternate completed page only falls back to alternate initializer when progress missing", 'if progress is None:' in STUDENT and 'progress = store.ensure_alternate_followup_state(attempt.attempt_id)' in STUDENT)
check("perfect Daily wording does not claim misses were fixed", '"✅ Fix Your Misses complete!" if had_daily_misses else "✅ Daily 10 complete!"' in STUDENT)
check("alternate activity retry rebuilds query", 'def _load_activity_rows()' in STORE and '_retry_transient(_load_activity_rows)' in STORE)
check("alternate progress creation rereads after uncertain insert", 'for create_try in range(2):' in STORE and '_retry_transient(_load_progress_row)' in STORE)


class Response:
    def __init__(self, data):
        self.data = data


class ProgressBackend:
    def __init__(self, mode: str):
        self.mode = mode
        self.row = None
        self.insert_calls = 0
        self.failure_mode = "before_commit"


class ProgressQuery:
    def __init__(self, backend: ProgressBackend, op: str = "select", payload=None):
        self.backend = backend
        self.op = op
        self.payload = payload

    def select(self, *_args, **_kwargs):
        return self
    def eq(self, *_args, **_kwargs):
        return self
    def limit(self, *_args, **_kwargs):
        return self
    def insert(self, payload):
        return ProgressQuery(self.backend, "insert", dict(payload))

    def execute(self):
        if self.op == "select":
            return Response([] if self.backend.row is None else [dict(self.backend.row)])
        self.backend.insert_calls += 1
        payload = dict(self.payload)
        row = {
            "student_id": payload["student_id"],
            "challenge_id": payload["challenge_id"],
            "daily_mode": payload["daily_mode"],
            "focus_plan": payload.get("focus_plan", []),
            "fix_completed_at": None,
            "focus_completed_at": None,
            "completed_at": None,
        }
        if self.backend.insert_calls == 1:
            if self.backend.failure_mode == "after_commit":
                self.backend.row = row
            raise httpx.ReadError("simulated dropped insert response")
        self.backend.row = row
        return Response([dict(row)])


class ProgressClient:
    def __init__(self, backend):
        self.backend = backend
    def table(self, name):
        assert name == "alternate_learning_progress"
        return ProgressQuery(self.backend)


old_sleep = sfs.time.sleep
old_uniform = sfs.random.uniform
sfs.time.sleep = lambda *_args, **_kwargs: None
sfs.random.uniform = lambda *_args, **_kwargs: 0.0
try:
    # If the first request dies before Supabase receives it, v2.19.1 should retry
    # creation instead of making the student hit Try Again.
    backend = ProgressBackend("Mixed")
    store = SupabaseFactStore("https://example.supabase.co", "secret", client=ProgressClient(backend))
    rec = store.get_or_create_alternate_learning_progress("s1", "c1", "Mixed")
    check("progress creation retries when first insert never arrived", rec.student_id == "s1" and backend.insert_calls == 2)

    # If Supabase committed the first insert but its response was lost, reread it
    # rather than blindly inserting again.
    backend = ProgressBackend("Mixed")
    backend.failure_mode = "after_commit"
    store = SupabaseFactStore("https://example.supabase.co", "secret", client=ProgressClient(backend))
    rec = store.get_or_create_alternate_learning_progress("s2", "c2", "Mixed")
    check("progress creation recovers lost post-commit response without duplicate insert", rec.student_id == "s2" and backend.insert_calls == 1)
finally:
    sfs.time.sleep = old_sleep
    sfs.random.uniform = old_uniform


class ActivityBackend:
    def __init__(self):
        self.table_calls = 0
        self.execute_calls = 0


class ActivityQuery:
    def __init__(self, backend: ActivityBackend):
        self.backend = backend
    def select(self, *_args, **_kwargs): return self
    def eq(self, *_args, **_kwargs): return self
    def order(self, *_args, **_kwargs): return self
    def execute(self):
        self.backend.execute_calls += 1
        if self.backend.execute_calls == 1:
            raise httpx.ReadError("simulated transient read")
        return Response([])


class ActivityClient:
    def __init__(self, backend): self.backend = backend
    def table(self, name):
        assert name == "alternate_learning_events"
        self.backend.table_calls += 1
        return ActivityQuery(self.backend)


sfs.time.sleep = lambda *_args, **_kwargs: None
sfs.random.uniform = lambda *_args, **_kwargs: 0.0
try:
    backend = ActivityBackend()
    store = SupabaseFactStore("https://example.supabase.co", "secret", client=ActivityClient(backend))
    rows = store.alternate_learning_activity_rows("s", "c", "focus")
    check("activity read retry rebuilds PostgREST query", rows == [] and backend.table_calls == 2 and backend.execute_calls == 2)
finally:
    sfs.time.sleep = old_sleep
    sfs.random.uniform = old_uniform

print(f"v2.19.1 Student Morning Reliability: PASS ({len(checks)}/{len(checks)} checks)")
