from pathlib import Path

APP = Path("app.py").read_text(encoding="utf-8")
ENGINE = Path("fact_engine.py").read_text(encoding="utf-8")

start = APP.index("def render_completed_daily")
end = APP.index("\ndef render_daily(store", start)
completed = APP[start:end]

checks = {
    "version": 'APP_VERSION = "2.14.0"' in ENGINE,
    "compact completion message": 'st.success("✅ Daily 10 complete!")' in completed,
    "fix next step visible": 'st.markdown("### Next: Fix Your Misses")' in completed,
    "fix count visible": 'You have {missed_count} fact' in completed,
    "focus next step visible": 'st.markdown("### Next: Focus Practice")' in completed,
    "midpoint result card gone": "render_daily_result_summary(" not in completed,
    "midpoint leaderboard gone": "render_leaderboard(" not in completed,
    "midpoint routine strip gone": "render_learning_path(" not in completed,
    "standings load deferred until complete": completed.index("if progress.completed_at is not None:") < completed.index("get_cached_leaderboard_context(store, challenge, refresh=True)"),
    "daily review available below active step": completed.count("render_daily_review(facts, answers)") == 2,
    "fix legacy step heading removed": "Learning Step 2 of 3 · Fix Your Misses" not in APP,
    "focus legacy step heading removed": "Learning Step 3 of 3 · 🎯 Your Focus Practice" not in APP,
    "final top10 still exists": "render_final_top10_status" in APP,
    "final mystery still exists": "Today's Mystery Reward" in APP,
}

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError(f"Failed: {failed}")
print(f"v2.11.2 post-Daily UI patch regression: {len(checks)}/{len(checks)} checks passed")
