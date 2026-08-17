from pathlib import Path

APP = Path("app.py").read_text()
ENGINE = Path("fact_engine.py").read_text()

checks = {
    "version bumped": 'APP_VERSION = "2.9.3.1"' in ENGINE,
    "day complete does not render duplicate mystery strip": 'def render_day_complete' in APP and 'render_routine_strip("mystery")' not in APP[APP.index('def render_day_complete'):APP.index('def _is_transient_classroom_error')],
    "single mystery reward heading": '## 🕵️ Today\'s Mystery Reward' in APP,
    "mystery renderer can suppress inner heading": 'show_heading: bool = True' in APP and 'if show_heading:' in APP,
    "day complete suppresses repeated mystery heading": 'render_weekly_mystery_reward(store, day, challenge, show_heading=False)' in APP,
}
failed=[name for name,ok in checks.items() if not ok]
if failed:
    raise AssertionError(f"Failed: {failed}")
print(f"v2.7.0 final-screen polish: {len(checks)}/{len(checks)} checks passed")
