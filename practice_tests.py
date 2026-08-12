import random

from fact_engine import Fact, fact_family_options, practice_fact, repeated_addition_text


def run():
    checks = 0
    options = fact_family_options()
    assert options[0] == "Mixed" and options[-1] == "12s" and len(options) == 12
    checks += 1

    for family in range(2, 13):
        rng = random.Random(family)
        for _ in range(100):
            fact = practice_fact(f"{family}s", rng)
            assert family in {fact.a, fact.b}
            assert 2 <= fact.a <= 12 and 2 <= fact.b <= 12
        checks += 1

    rng = random.Random(99)
    for _ in range(1000):
        fact = practice_fact("Mixed", rng)
        assert 2 <= fact.a <= 12 and 2 <= fact.b <= 12
    checks += 1

    fact = Fact(6, 7, "hard")
    text = repeated_addition_text(fact)
    assert text.endswith("= 42.") and text.count("7") >= 6
    checks += 1

    # Avoid list should prevent an immediate repeat when alternatives exist.
    rng = random.Random(12)
    first = practice_fact("7s", rng)
    second = practice_fact("7s", rng, avoid=[first.key])
    assert second.key != first.key
    checks += 1

    print(f"practice_tests: PASS ({checks} checks + 2,100 generated Practice facts)")


if __name__ == "__main__":
    run()
