from __future__ import annotations

import ast
from pathlib import Path

from fact_engine import APP_VERSION, CHALLENGE_VERSION

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

check("v2.16.0 version", APP_VERSION == "2.16.1")
check("Daily challenge contract unchanged", CHALLENGE_VERSION == "TDFC-DAILY-v1")

# Isolate the Weekly Mystery teacher renderer so ordering assertions do not
# accidentally match unrelated student Mystery text elsewhere in app.py.
tree = ast.parse(APP)
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_teacher_weekly_mystery")
MYSTERY_RENDER = ast.get_source_segment(APP, node) or ""

check("current week appears before previous week history", MYSTERY_RENDER.index('#### This Week') < MYSTERY_RENDER.index("Last Week's Prize Raffles"))
check("prior-week raffle block is after next-week planner", MYSTERY_RENDER.index("Plan Next Week's Mystery") < MYSTERY_RENDER.index("previous_week = week_start - timedelta(days=7)"))
check("blue projector-safety banner removed", "Projector-safe by default" not in MYSTERY_RENDER)
check("green saved-results banner removed", "Last week's raffle results are saved" not in MYSTERY_RENDER)
check("pending-results warning banner removed", "Last week's raffle still needs attention" not in MYSTERY_RENDER)
check("prior raffle caption is teacher-facing and concise", "Saved winners and any remaining drawings from last week." in MYSTERY_RENDER)

# Safety behavior remains even though the explanatory banners are gone.
check("current answer remains collapsed", 'with st.expander("🔒 Teacher Mystery details · contains the answer and clues", expanded=False):' in MYSTERY_RENDER)
check("next week planner remains collapsed", 'with st.expander(f"🔒 Plan Next Week\'s Mystery' in MYSTERY_RENDER and 'expanded=False' in MYSTERY_RENDER)
check("prior saved winners still render after final draw", "if previous_pending or previous_saved:" in MYSTERY_RENDER)

# Top navigation requested by the teacher.
check("top navigation has five destinations in requested order", '["📊 Today", "🧠 Warm-Up", "📈 Learning", "🕵️ Weekly Mystery", "⚙️ Manage"]' in APP)
check("Weekly Mystery routes directly to top nav", '"Weekly Mystery": ("🕵️ Weekly Mystery", None, None)' in APP)
check("Weekly Mystery has direct render branch", 'elif primary == "🕵️ Weekly Mystery":\n        render_teacher_weekly_mystery(store)' in APP)
check("Manage now contains only administrative destinations", '["👥 Classes & Rosters", "🖥️ Clock", "🧪 Test Student"]' in APP)
check("Manage no longer duplicates Weekly Mystery", 'manage_sections = ["🕵️ Weekly Mystery"' not in APP)
check("teacher nav caption simplified", "Your everyday classroom tools stay one tap away." in APP)
check("no v2.16.0 SQL migration", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_14_3.sql").exists())

assert len(checks) == 18, len(checks)
print(f"v2.16.0 Mystery/nav polish regression: {len(checks)}/{len(checks)} checks passed")
