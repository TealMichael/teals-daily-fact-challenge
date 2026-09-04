from __future__ import annotations

from pathlib import Path

from fact_engine import APP_VERSION, CHALLENGE_VERSION
from teacher_command_center import build_today_action_items

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TODAY = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")

checks: list[str] = []
def check(name: str, condition: bool) -> None:
    assert condition, name
    checks.append(name)

check("v2.16.0 version", APP_VERSION == "2.19.4")
check("student Daily challenge remains protected", CHALLENGE_VERSION == "TDFC-DAILY-v1")
check("v2.14.2 requires no SQL", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_14_1.sql").exists())

names = build_today_action_items(
    daily_summary={"present": 5, "complete": 2, "in_progress": 1, "not_started": 2},
    routine_summary={"done": 1, "daily": 1, "fix": 1, "focus": 1, "not_started": 1},
    warmup_assigned=True,
    warmup_finished=3,
    pending_prior_raffle=True,
    not_started_names=["FalconFox", "BlueSky"],
    follow_up_names=["MathMaster", "QuickQuokka"],
    warmup_missing_names=["FalconFox", "NumberNinja"],
)
check("Daily follow-up names are visible", names[0]["detail"] == "FalconFox, BlueSky")
check("follow-up practice names are visible", names[1]["detail"] == "MathMaster, QuickQuokka")
check("Warm-Up missing names are visible", names[2]["detail"] == "FalconFox, NumberNinja")
check("follow-up wording is concise", names[0]["title"] == "Daily 10 not started · 2")
check("old awkward heading removed", "What needs you" not in TODAY)
check("new heading is Quick follow-ups", "Quick follow-ups" in TODAY)
check("attendance expander removed", "Attendance exceptions" not in TODAY and "Save attendance exceptions" not in TODAY)
check("all-class snapshot drops Absent column", '"Absent": summary["absent"]' not in TODAY)
check("Today uses full active roster counts", "summary = summarize_daily_status(status_rows)" in TODAY)
check("Warm-Up jump sends selected class", 'args=("Warm-Up", selected.class_name)' in TODAY)
check("teacher router accepts class context", "def _go_teacher_tool(tool: str, class_name: str | None = None)" in APP)
check("teacher router seeds Warm-Up class", 'st.session_state["teacher_warmup_class"] = str(class_name)' in APP)

print(f"v2.14.2 Teacher Follow-up Polish: {len(checks)}/{len(checks)} checks passed")
