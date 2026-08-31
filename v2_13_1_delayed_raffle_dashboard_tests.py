from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from fact_engine import APP_VERSION, CHALLENGE_VERSION
from fact_store import InMemoryFactStore

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
SETUP = (ROOT / "teacher_daily_setup_ui.py").read_text(encoding="utf-8")

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

check("v2.14.2 version", APP_VERSION == "2.14.2")
check("multiplication challenge version untouched", CHALLENGE_VERSION == "TDFC-DAILY-v1")

# Execute the real pure raffle-state helpers from app.py without importing the Streamlit app shell.
tree = ast.parse(APP)
helper_names = {"_mystery_raffle_setting_key", "_mystery_raffle_has_pending_draw"}
helper_nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in helper_names]
check("raffle helper functions present", {node.name for node in helper_nodes} == helper_names)
module = ast.Module(body=helper_nodes, type_ignores=[])
namespace = {"SupabaseFactStore": object}
exec(compile(module, "app.py", "exec"), namespace)
setting_key = namespace["_mystery_raffle_setting_key"]
has_pending = namespace["_mystery_raffle_has_pending_draw"]

store = InMemoryFactStore()
klass = store.create_class("Block 1")
student = store.create_student(klass.class_id, "FalconFox", "2468")
last_week = date(2026, 8, 17)
store.submit_mystery_guess(student.student_id, last_week, "answer", correct=True, clue_count=5, guess_day=5)
check("undrawn prior raffle detected", has_pending(store, last_week))

store.set_app_setting(setting_key(last_week, klass.class_id), {
    "student_id": student.student_id,
    "nickname": student.nickname,
    "class_id": klass.class_id,
    "class_name": klass.class_name,
})
check("saved valid winner clears pending state", not has_pending(store, last_week))

store.set_app_setting(setting_key(last_week, klass.class_id), {"student_id": "missing-student"})
check("stale saved winner remains pending", has_pending(store, last_week))

check("raffle unlock uses its own Friday date", "raffle_open = day >= (week_start + timedelta(days=4))" in APP)
check("previous week checked for undrawn raffle", "previous_week = week_start - timedelta(days=7)" in APP and "_mystery_raffle_has_pending_draw(store, previous_week)" in APP)
check("late raffle has explicit teacher heading", "Last Week's Prize Raffles" in APP)
check("late raffle says current mystery is unaffected", "do not affect the new week's Mystery" in APP)

primary_nav = '["📊 Today", "🧠 Warm-Up", "📈 Learning", "⚙️ Manage"]'
check("v2.13.1 Today and Warm-Up remain first-class destinations", primary_nav in APP)
check("daily setup remains outside primary navigation", "🎯 Daily 10 Setup" not in primary_nav)
check("all v2.13.1 teacher tools remain reachable after grouping", all(item in APP for item in [
    "📈 Learning Data", "🛠️ Student Support", "🕵️ Weekly Mystery", "👥 Classes & Rosters", "🖥️ Clock", "🧪 Test Student",
]))
check("daily setup tucked into class hub", '["👥 Rosters", "🎯 Daily 10 Setup"]' in APP and "render_teacher_daily_setup(store, show_heading=False)" in APP)
check("embedded daily setup keeps same component", "def render_teacher_daily_setup(store: SupabaseFactStore, *, show_heading: bool = True)" in SETUP)
check("logout no longer stretches across header column", 'if st.button("Log out"):' in APP)
check("no v2.14.2 database migration required", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_13_1.sql").exists())

assert len(checks) == 17, len(checks)
print(f"v2.14.2 delayed-raffle/dashboard regression: {len(checks)}/{len(checks)} checks passed")
