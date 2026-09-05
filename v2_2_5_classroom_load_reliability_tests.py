from pathlib import Path
import httpx

from supabase_fact_store import _is_transient_http_error, _retry_transient

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text()
STORE = (ROOT / "supabase_fact_store.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()


def test_transient_retry_recovers():
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ReadError("temporary classroom read failure")
        return "ok"
    assert _retry_transient(flaky, attempts=4) == "ok"
    assert calls["n"] == 3


def test_non_transient_is_not_retried():
    calls = {"n": 0}
    def bad():
        calls["n"] += 1
        raise ValueError("real bug")
    try:
        _retry_transient(bad, attempts=4)
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError should propagate")
    assert calls["n"] == 1


def test_transport_classifier():
    assert _is_transient_http_error(httpx.ReadError("x"))
    assert _is_transient_http_error(httpx.ConnectError("x"))
    assert not _is_transient_http_error(ValueError("x"))


checks = {
    "version bumped": 'APP_VERSION = "2.19.7"' in ENGINE,
    "batch mastery updater exists": "def record_mastery_evidence_batch(" in STORE,
    "Daily completion uses batch mastery": "self.record_mastery_evidence_batch(" in STORE,
    "batch rationale documents classroom burst": "~20 mastery database calls per student" in STORE,
    "leaderboard can reuse roster": "students: Sequence[StudentRecord] | None = None" in STORE,
    "leaderboard context loads once": "def load_leaderboard_context(" in APP,
    "completed screen shares leaderboard context": "leaderboard_context=leaderboard_context" in APP,
    "friendly busy message": "The classroom connection is busy for a moment" in APP,
    "student does not redo Daily": "you do not need to redo your 10 facts" in APP,
    "retry button exists": '"Try again"' in APP,
    "get answers protected": "_retry_transient(lambda:" in STORE and "daily_answers" in STORE,
}


def main():
    test_transient_retry_recovers()
    test_non_transient_is_not_retried()
    test_transport_classifier()
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.2.5 classroom load reliability: {len(checks) + 3}/{len(checks) + 3} checks passed")


if __name__ == "__main__":
    main()
