from datetime import date
from pathlib import Path

from fact_engine import CHALLENGE_VERSION, Fact, daily_facts_for_date
from fact_store import InMemoryFactStore


def run():
    checks = 0
    day = date(2026, 8, 15)
    original = daily_facts_for_date(day)
    store = InMemoryFactStore()

    first = store.get_or_create_challenge(day, CHALLENGE_VERSION, original)
    checks += 1

    # Simulate a later deployment producing a different local copy/version.
    altered = list(original)
    altered[0] = Fact(2, 2, "easy") if altered[0].key != (2, 2) else Fact(3, 3, "easy")
    later = store.get_or_create_challenge(day, "TDFC-DAILY-v999", altered)
    assert later.challenge_id == first.challenge_id
    assert later.challenge_version == first.challenge_version
    assert later.facts == first.facts
    checks += 4

    # Tomorrow is still generated normally.
    next_day = date(2026, 8, 16)
    next_facts = daily_facts_for_date(next_day)
    next_challenge = store.get_or_create_challenge(next_day, CHALLENGE_VERSION, next_facts)
    assert next_challenge.facts == tuple(next_facts)
    assert next_challenge.challenge_id != first.challenge_id
    checks += 2

    supabase_source = Path("supabase_fact_store.py").read_text()
    assert "existing = self.get_challenge(key)" in supabase_source
    assert "if existing is not None:" in supabase_source
    assert "Stored Daily Challenge does not match the local generator." not in supabase_source
    checks += 3

    app_source = Path("app.py").read_text()
    assert "return day, list(challenge.facts), challenge" in app_source
    checks += 1

    print(f"v2_8_2_1_daily_continuity_hotfix_tests: PASS ({checks}/11)")


if __name__ == "__main__":
    run()
