from pathlib import Path

from supabase_fact_store import SupabaseFactStore, _is_transient_http_error

ROOT = Path(__file__).resolve().parent
STORE = (ROOT / "supabase_fact_store.py").read_text()
WARMUP = (ROOT / "teacher_warmup_ui.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()


class FakeAPIError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = None
        self.hint = None


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, owner):
        self.owner = owner

    def select(self, *_args, **_kwargs): return self
    def eq(self, *_args, **_kwargs): return self
    def order(self, *_args, **_kwargs): return self

    def execute(self):
        self.owner.calls += 1
        if self.owner.failures_remaining > 0:
            self.owner.failures_remaining -= 1
            raise FakeAPIError("PGRST003", "Timed out acquiring connection from the connection pool")
        return FakeResponse([{
            "class_id": "c1",
            "class_name": "Block 1",
            "class_code": "ABC123",
            "active": True,
            "created_at": "2026-08-27T12:00:00+00:00",
        }])


class FakeClient:
    def __init__(self, failures_remaining=0):
        self.calls = 0
        self.failures_remaining = failures_remaining

    def table(self, name):
        assert name == "classes"
        return FakeQuery(self)


def make_store(client):
    store = object.__new__(SupabaseFactStore)
    store.client = client
    return store


def test_structured_postgrest_pool_error_is_transient():
    assert _is_transient_http_error(FakeAPIError("PGRST003", "connection pool timeout"))
    assert _is_transient_http_error(FakeAPIError("PGRST000", "database connection error"))
    assert not _is_transient_http_error(FakeAPIError("42P01", "relation does not exist"))


def test_list_classes_retries_structured_apierror():
    client = FakeClient(failures_remaining=2)
    store = make_store(client)
    rows = store.list_classes()
    assert [row.class_name for row in rows] == ["Block 1"]
    assert client.calls == 3


def test_list_classes_uses_last_good_cache_after_transient_failure():
    client = FakeClient(failures_remaining=0)
    store = make_store(client)
    first = store.list_classes()
    assert first and first[0].class_name == "Block 1"
    client.failures_remaining = 20
    second = store.list_classes()
    assert second and second[0].class_name == "Block 1"


def test_warmup_has_fresh_connection_retry_ui():
    assert 'Retry class connection' in WARMUP
    assert 'tdfc_force_fresh_store_once' in WARMUP
    assert 'warmup_class_list_failed' in WARMUP


def test_version_bumped():
    assert 'APP_VERSION = "2.24.5"' in ENGINE


if __name__ == "__main__":
    tests = [
        test_structured_postgrest_pool_error_is_transient,
        test_list_classes_retries_structured_apierror,
        test_list_classes_uses_last_good_cache_after_transient_failure,
        test_warmup_has_fresh_connection_retry_ui,
        test_version_bumped,
    ]
    for test in tests:
        test()
    print(f"v2.24.5 PostgREST resilience: {len(tests)}/{len(tests)} checks passed")
