from datetime import datetime, timezone
from types import SimpleNamespace

import supabase_fact_store as sfs


class OldMutationBuilder:
    """Mimics supabase-py 2.28.3 mutation builders: execute(), no select()."""
    def __init__(self, row):
        self.row = row
        self.payload = None

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        return SimpleNamespace(data=[self.row])


class NewMutationBuilder(OldMutationBuilder):
    def __init__(self, row):
        super().__init__(row)
        self.selected = None

    def select(self, columns):
        self.selected = columns
        return self


class FakeClient:
    def __init__(self, builder):
        self.builder = builder

    def table(self, _name):
        return self.builder


checks = {}
row = {
    "attempt_id": "attempt-1",
    "student_id": "student-1",
    "challenge_id": "challenge-1",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "timed_started_at": None,
    "completed_at": None,
    "correct_count": None,
    "timed_seconds": None,
}

old = OldMutationBuilder(row)
resp = sfs._execute_returning(old, "*")
checks["2.28.3-style mutation builder executes without select"] = resp.data[0]["attempt_id"] == "attempt-1"
checks["2.28.3-style builder genuinely lacks select"] = not hasattr(old, "select")

new = NewMutationBuilder(row)
resp = sfs._execute_returning(new, "attempt_id")
checks["newer builder still uses select when available"] = new.selected == "attempt_id" and resp.data[0]["attempt_id"] == "attempt-1"

store = sfs.SupabaseFactStore.__new__(sfs.SupabaseFactStore)
store.client = FakeClient(OldMutationBuilder(row))
store.get_attempt_for_student = lambda student_id, challenge_id: None
attempt = store.get_or_create_attempt("student-1", "challenge-1")
checks["Daily attempt creation works with 2.28.3-style builder"] = attempt.attempt_id == "attempt-1"

source = open("supabase_fact_store.py", encoding="utf-8").read()
checks["compatibility helper documents pinned 2.28.3"] = "supabase-py 2.28.3 mutation builder" in source
checks["Daily attempt mutation uses compatibility helper"] = 'row = _first(_execute_returning(\n                self.client.table("daily_attempts")' in source

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError("Failed v2.11.0.3 compatibility checks: " + ", ".join(failed))
print(f"v2.11.0.3 Supabase 2.28.3 compatibility: PASS ({len(checks)}/{len(checks)})")
