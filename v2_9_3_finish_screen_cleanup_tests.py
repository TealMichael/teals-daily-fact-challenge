from pathlib import Path

APP = Path("app.py").read_text(encoding="utf-8")
ENGINE = Path("fact_engine.py").read_text(encoding="utf-8")
TODAY = Path("teacher_today_ui.py").read_text(encoding="utf-8")
ALL_UI = APP + "\n" + TODAY

start = APP.index("def render_day_complete")
end = APP.index("\ndef _is_transient_classroom_error", start)
finish = APP[start:end]

completed_start = APP.index("def render_completed_daily")
completed_end = APP.index("\ndef render_login", completed_start) if "\ndef render_login" in APP[completed_start:] else len(APP)
completed = APP[completed_start:completed_end]

checks = {
    "version 2.9.3": 'APP_VERSION = "2.15.0"' in ENGINE,
    "mystery before top ten": finish.index("Today's Mystery Reward") < finish.index("render_final_top10_status"),
    "top ten before streak": finish.index("render_final_top10_status") < finish.index("Learning Streak"),
    "finished screen reuses cached leaderboard": "leaderboard_context=leaderboard_context" in APP,
    "fully complete route goes straight to final screen": completed.index("if progress.completed_at is not None:") < completed.index('st.success("✅ Daily 10 complete!")'),
    "midpoint result card removed": "render_daily_result_summary(" not in completed,
    "final top ten keeps lower ranks private": "lower exact ranks stay private" in APP,
    "student stars removed": "Daily Star earned" not in APP and "total Daily Stars" not in APP,
    "teacher calls it days completed": '"Days Completed"' in ALL_UI,
    "student support no longer says Stars": "mastery, Stars, streak" not in APP,
    "completion count preserved internally": '"stars"' in Path("fact_store.py").read_text(),
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError(f"Failed: {failed}")
print(f"v2.9.3 finish-screen cleanup regression: {len(checks)}/{len(checks)} checks passed")
