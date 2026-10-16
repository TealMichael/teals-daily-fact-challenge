from pathlib import Path

APP = Path(__file__).with_name("app.py").read_text(encoding="utf-8")

start = APP.index("def render_final_top10_status")
end = APP.index("\ndef render_day_complete", start)
final_top10 = APP[start:end]

completed_start = APP.index("def render_completed_daily")
completed_end = APP.index("\ndef render_daily(", completed_start)
completed = APP[completed_start:completed_end]

checks = {
    "final screen keeps status heading": 'st.markdown("## 🏆 Current Top 10")' in final_top10,
    "final screen renders leaderboard rows": 'class="leader-row"' in final_top10,
    "final screen renders rank marker": 'class="leader-rank"' in final_top10,
    "final screen renders nickname": 'class="leader-name"' in final_top10,
    "final screen highlights current student": 'suffix = " · you" if own else ""' in final_top10,
    "final screen escapes nicknames": 'html.escape' in final_top10,
    "final screen uses passed snapshot only": "load_leaderboard_context(" not in final_top10 and "store.leaderboard(" not in final_top10,
    "midpoint leaderboard remains absent": "render_leaderboard(" not in completed,
    "leaderboard context still loads only at full completion": completed.index("if progress.completed_at is not None:") < completed.index("get_cached_leaderboard_context(store, challenge, refresh=True)"),
}

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError("Failed checks: " + ", ".join(failed))
print(f"v2_11_2_final_top10_restore_tests: PASS ({len(checks)}/{len(checks)})")
