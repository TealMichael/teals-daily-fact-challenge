from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def run():
    checks = {
        "explicit family filter mapping": 'family_filters = {f"{value}s": value for value in range(2, 11)}' in APP,
        "family selection uses explicit membership": 'elif heat_filter in family_filters:' in APP,
        "all facts is not parsed as integer": 'int(heat_filter[:-1])' not in APP,
        "brittle suffix test removed": 'elif heat_filter.endswith("s"):' not in APP,
        "all facts fallback shows full map": 'shown_keys = fact_keys' in APP,
        "focus-only branch preserved": 'if heat_filter == "Focus facts only":' in APP and 'shown_keys = focus_keys' in APP,
        "family filter still filters either factor": 'shown_keys = [key for key in fact_keys if family in key]' in APP,
    }
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError('Failed: ' + ', '.join(failed))
    print(f"v2.8.1 Teacher Dashboard filter hotfix: {len(checks)}/{len(checks)} checks passed")


if __name__ == '__main__':
    run()
