from pathlib import Path
import httpx

from supabase_fact_store import SupabaseFactStore

ROOT = Path(__file__).resolve().parent
STORE = (ROOT / "supabase_fact_store.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, owner):
        self.owner = owner

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        self.owner.exec_calls += 1
        if self.owner.exec_calls < 3:
            raise httpx.ReadError("temporary class-list read reset")
        return FakeResponse([{
            "class_id": "c1",
            "class_name": "Block 1",
            "class_code": "ABC123",
            "active": True,
            "created_at": "2026-08-27T12:00:00+00:00",
        }])


class FakeClient:
    def __init__(self):
        self.exec_calls = 0
        self.table_calls = 0

    def table(self, name):
        assert name == "classes"
        self.table_calls += 1
        return FakeQuery(self)


def test_list_classes_recovers_from_readerror_and_rebuilds_query():
    client = FakeClient()
    store = object.__new__(SupabaseFactStore)
    store.client = client
    rows = store.list_classes()
    assert [row.class_name for row in rows] == ["Block 1"]
    assert client.exec_calls == 3
    assert client.table_calls == 3, "each retry should rebuild the PostgREST query"


def main():
    test_list_classes_recovers_from_readerror_and_rebuilds_query()
    checks = {
        "version bumped": 'APP_VERSION = "2.19.5"' in ENGINE,
        "list_classes uses retry wrapper": "_retry_transient(fetch_classes, attempts=4)" in STORE,
        "list_classes rebuilds query": 'def fetch_classes()' in STORE,
        "production comment documents teacher crash protection": "should not crash the entire dashboard" in STORE,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.14.2 class-list ReadError hotfix: {len(checks) + 1}/{len(checks) + 1} checks passed")


if __name__ == "__main__":
    main()
