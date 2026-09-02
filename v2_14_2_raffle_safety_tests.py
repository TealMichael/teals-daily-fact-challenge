from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from fact_engine import APP_VERSION, CHALLENGE_VERSION
from fact_store import InMemoryFactStore

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

check("v2.16.0 version", APP_VERSION == "2.19.1")
check("Daily challenge contract unchanged", CHALLENGE_VERSION == "TDFC-DAILY-v1")

# Execute real pure raffle-state helpers from app.py without importing Streamlit.
tree = ast.parse(APP)
helper_names = {
    "_mystery_raffle_setting_key",
    "_mystery_raffle_has_pending_draw",
    "_mystery_raffle_saved_winners",
    "_mystery_raffle_has_saved_winner",
}
helper_nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in helper_names]
check("all raffle state helpers present", {n.name for n in helper_nodes} == helper_names)
module = ast.Module(body=helper_nodes, type_ignores=[])
namespace = {"SupabaseFactStore": object}
exec(compile(module, "app.py", "exec"), namespace)
setting_key = namespace["_mystery_raffle_setting_key"]
has_pending = namespace["_mystery_raffle_has_pending_draw"]
saved_winners = namespace["_mystery_raffle_saved_winners"]
has_saved = namespace["_mystery_raffle_has_saved_winner"]

store = InMemoryFactStore()
classes = [store.create_class(f"Block {i}") for i in (1, 2, 3)]
students = []
week = date(2026, 8, 24)
for i, klass in enumerate(classes, start=1):
    student = store.create_student(klass.class_id, f"Winner{i}", f"24{i}8")
    students.append(student)
    store.submit_mystery_guess(student.student_id, week, "answer", correct=True, clue_count=5, guess_day=5)

check("three-class prior raffle starts pending", has_pending(store, week))
for klass, student in zip(classes[:2], students[:2]):
    store.set_app_setting(setting_key(week, klass.class_id), {
        "student_id": student.student_id,
        "nickname": student.nickname,
        "class_id": klass.class_id,
        "class_name": klass.class_name,
        "drawn_at": "2026-08-28T19:00:00+00:00",
    })
check("two saved winners still leaves final class pending", has_pending(store, week))
check("saved prior results are discoverable before final draw", len(saved_winners(store, week)) == 2 and has_saved(store, week))

klass = classes[2]
student = students[2]
store.set_app_setting(setting_key(week, klass.class_id), {
    "student_id": student.student_id,
    "nickname": student.nickname,
    "class_id": klass.class_id,
    "class_name": klass.class_name,
    "drawn_at": "2026-08-31T18:45:00+00:00",
})
check("final draw clears pending state", not has_pending(store, week))
results = saved_winners(store, week)
check("final draw remains recoverable after pending clears", len(results) == 3 and has_saved(store, week))
check("saved winner nickname is preserved", any(r.get("nickname") == "Winner3" for r in results))

# The exact regression: prior raffle section must render when saved results exist,
# not only while an undrawn class exists.
check("prior raffle stays visible after final draw", "if previous_pending or previous_saved:" in APP)
check("previous saved raffle state is checked", "previous_saved = _mystery_raffle_has_saved_winner(store, previous_week)" in APP)
check("final draw no longer immediately reruns away", "st.caption(\"Winner saved.\")" in APP)
check("final draw celebrates winner", "st.balloons()" in APP)
check("historical saved winner displays even if current eligibility changes", "The student is no longer on the current eligible list." in APP)

# Projector safety: no answer/clue preview is rendered by default.
check("projector safety no longer needs a dashboard banner", "Projector-safe by default" not in APP)
check("current mystery answer is behind collapsed teacher expander", 'with st.expander("🔒 Teacher Mystery details · contains the answer and clues", expanded=False):' in APP)
check("next-week mystery planner is behind collapsed teacher expander", "with st.expander(f\"🔒 Plan Next Week's Mystery" in APP and "expanded=False" in APP)
check("current preview only appears inside protected render function region", APP.index('_render_teacher_mystery_preview(mystery, label="Teacher preview")') > APP.index('with st.expander("🔒 Teacher Mystery details'))
check("no v2.14.2 SQL migration", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_14_2.sql").exists())

assert len(checks) == 19, len(checks)
print(f"v2.14.2 raffle safety regression: {len(checks)}/{len(checks)} checks passed")
