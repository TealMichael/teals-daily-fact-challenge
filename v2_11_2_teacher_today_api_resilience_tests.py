from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(APP)


def function_node(name: str) -> ast.FunctionDef:
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing function: {name}")


def try_wraps_daily_status(fn: ast.FunctionDef) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr == "daily_status":
                    return bool(node.handlers)
    return False


today = function_node("render_teacher_today")
projector = function_node("render_teacher_projector")

assert try_wraps_daily_status(today), "Teacher Today daily_status must be exception-isolated"
assert try_wraps_daily_status(projector), "Projector daily_status must be exception-isolated"

assert 'daily_status_error = None' in APP
assert 'Daily 10 status could not load just now. Igniter results and other teacher tools are still available' in APP
assert 'Igniter results above are unaffected' in APP
assert 'if str(st.query_params.get("dbcheck", "0")) == "1":' in APP

# A Daily-status outage must not prevent the independent Igniter reads.
today_source = ast.get_source_segment(APP, today) or ""
assert 'store.get_warmup_set(selected.class_id, day)' in today_source
assert 'store.list_warmup_answers(day, day, class_id=selected.class_id)' in today_source
assert today_source.index('daily_status_error = None') < today_source.index('store.get_warmup_set(selected.class_id, day)')

# Do not fabricate Daily/Top-10 data when the Daily status query is unavailable.
assert 'c1.metric("🟢 Done", "—")' in today_source
assert 'if daily_status_error is not None:' in today_source
assert 'Daily standings are temporarily unavailable' in today_source

# The projector keeps Back/Refresh usable and surfaces diagnostics only under dbcheck.
projector_source = ast.get_source_segment(APP, projector) or ""
assert 'status_error = None' in projector_source
assert 'st.session_state.pop("teacher_refresh_pending", False)' in projector_source
assert 'Tap Refresh data to try again, or go back to the Teacher Dashboard.' in projector_source

print("v2.11.2 Teacher Today API resilience: PASS (12 checks)")
