from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(APP)
TODAY_UI = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")
TODAY_TREE = ast.parse(TODAY_UI)


def fn(name: str, *, tree=TREE) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing function: {name}")


def source(name: str) -> str:
    return ast.get_source_segment(APP, fn(name)) or ""

def today_source(name: str) -> str:
    return ast.get_source_segment(TODAY_UI, fn(name, tree=TODAY_TREE)) or ""

# The clock integration must remain teacher-only. It may be imported globally,
# but student Daily/Practice must not call its queue/setup helpers.
for name in (
    "render_student_sign_in",
    "render_daily",
    "render_completed_daily",
    "render_fix_misses",
    "render_focus_practice",
    "render_day_complete",
    "render_practice",
):
    text = source(name)
    assert "queue_clock_top10_for_class" not in text, f"Clock queue leaked into student flow: {name}"
    assert "render_teacher_clock" not in text, f"Clock setup leaked into student flow: {name}"
print("PASS: AWTRIX remains out of student flow")

# Teacher Clock stays lazy behind its own selected section.
teacher = source("render_teacher")
assert 'teacher_primary_sections = ["📊 Today", "🧠 Warm-Up", "📈 Learning", "🕵️ Weekly Mystery", "⚙️ Manage"]' in teacher
assert 'manage_sections = ["👥 Classes & Rosters", "🖥️ Clock", "🧪 Test Student"]' in teacher
assert 'elif manage_section == "🖥️ Clock":' in teacher
assert "render_teacher_clock(store)" in teacher
print("PASS: Clock setup remains teacher-section only")

# Teacher Today keeps the manual clock send, while its read-only Daily snapshot
# remains exception-isolated so a PostgREST hiccup cannot block Igniter results.
today = today_source("render_teacher_today_command_center")
assert "queue_clock_top10_for_class(store, selected.class_id)" in today
assert "daily_status_error = selected_snapshot.get(\"error\")" in today
assert "Daily standings are temporarily unavailable" in today
assert "store.get_warmup_set(selected.class_id, day)" in today
print("PASS: Teacher Today keeps clock send plus Daily-status isolation")

projector = source("render_teacher_projector")
assert "status_error = None" in projector
assert "Tap Refresh data to try again" in projector
print("PASS: Projector remains recoverable on Daily-status failure")

# Existing v2.12 behavior/contracts that matter for tomorrow.
engine = (ROOT / "fact_engine.py").read_text(encoding="utf-8")
assert 'APP_VERSION = "2.19.3"' in engine
assert 'CHALLENGE_VERSION = "TDFC-DAILY-v1"' in engine
print("PASS: Daily challenge version unchanged")

req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
assert "streamlit==1.61.1" in req
assert "supabase==2.28.3" in req
print("PASS: proven dependency pins retained")

# Both clock migrations must still ship; Hotfix1 fixes pgcrypto visibility.
assert (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_12.sql").exists()
assert (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_12_HOTFIX1.sql").exists()
hotfix = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_12_HOTFIX1.sql").read_text(encoding="utf-8")
assert "public, extensions, pg_temp" in hotfix
print("PASS: AWTRIX live SQL hotfix retained")

print("v2.12.0 classroom safety audit: PASS (7 protections)")
