from datetime import date, timedelta

from fact_engine import (
    CORE_POOLS,
    daily_facts_for_date,
    daily_mix_summary,
    validate_daily_facts,
)


def run():
    checks = 0
    start = date(2026, 1, 1)
    core_seen = set()
    extension_days = 0
    previous = None

    for offset in range(730):
        day = start + timedelta(days=offset)
        first = daily_facts_for_date(day)
        second = daily_facts_for_date(day)
        assert first == second
        checks += 1
        validate_daily_facts(first)
        checks += 1
        assert len(first) == 10
        assert len({f.key for f in first}) == 10
        checks += 1
        extension_count = sum(max(f.a, f.b) >= 11 for f in first)
        assert extension_count in {0, 1}
        extension_days += extension_count
        checks += 1
        mix = daily_mix_summary(first)
        assert mix["easy"] == 3
        assert mix["medium"] == 4
        assert mix["hard"] == (2 if extension_count else 3)
        assert mix["extension"] == extension_count
        checks += 1
        for fact in first:
            assert 2 <= fact.a <= 12 and 2 <= fact.b <= 12
            if max(fact.a, fact.b) <= 10:
                core_seen.add(fact.key)
        checks += 1
        keys = {f.key for f in first}
        if previous is not None:
            assert not (keys & previous), f"Consecutive Daily overlap on {day}: {keys & previous}"
            checks += 1
        previous = keys

    assert 250 <= extension_days <= 330, extension_days  # about 40%
    checks += 1
    assert len(core_seen) == sum(len(values) for values in CORE_POOLS.values()) == 45
    checks += 1

    print(f"fact_engine_tests: PASS ({checks} checks across 730 Daily Challenges)")


if __name__ == "__main__":
    run()
