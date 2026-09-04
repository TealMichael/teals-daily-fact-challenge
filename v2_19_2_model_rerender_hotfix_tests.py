from __future__ import annotations

"""v2.19.3 model-rerender reliability regression.

The classroom failure was caused by WATCH IT animation timers being cleared when
Streamlit re-rendered the custom component mid-sequence. The fix persists the
sequence start time and resumes the teaching sequence after same-session renders.
"""

from pathlib import Path
from fact_engine import APP_VERSION

ROOT = Path(__file__).parent
FIX = (ROOT / "alt_fix_component" / "index.html").read_text()
FOCUS = (ROOT / "alt_focus_component" / "index.html").read_text()

checks: list[str] = []
def check(name: str, condition: bool):
    assert condition, name
    checks.append(name)

check("v2.19.3 version", APP_VERSION == "2.19.3")

for label, src in (("Fix", FIX), ("Focus", FOCUS)):
    check(f"{label} stores coach sequence timestamp", "coachStartedAt" in src)
    check(f"{label} saves WATCH IT start before animating", "state.coachStartedAt=Date.now();save();resumeSequence()" in src)
    check(f"{label} resumes sequence after render", "bind();resumeSequence();setHeight()" in src)
    check(f"{label} derives animation progress from elapsed time", "Date.now()-started" in src)
    check(f"{label} restores SEE stage", "elapsed>=a" in src and "seq-see" in src)
    check(f"{label} restores CONNECT stage", "elapsed>=b" in src and "seq-connect" in src)
    check(f"{label} restores YOUR TURN stage", "elapsed>=c" in src and "sequence-complete" in src)
    check(f"{label} resets timestamp when leaving coach", "state.coachStartedAt=0" in src)

# Fix used to reload localStorage on every Streamlit render. Same-attempt renders
# must preserve live in-memory state so a storage/privacy limitation cannot reset
# an already-started WATCH IT sequence.
check(
    "Fix preserves in-memory state on same attempt rerender",
    "newKey=String(newArgs.attempt_key||'')" in FIX
    and "oldKey=String(args&&args.attempt_key||'')" in FIX
    and "if(!state||newKey!==oldKey){state=load();digits=''}render()" in FIX,
)

# Focus already had same-session state preservation; keep that contract too.
check(
    "Focus preserves in-memory state on same session rerender",
    "newKey=String(newArgs.session_key||'session')" in FOCUS
    and "if(!state||newKey!==oldKey){state=load();digits=''}render()" in FOCUS,
)

# The hotfix must remain inside the alternate components; multiplication browser
# code is protected by the established hash regressions.
check("Fix still uses WATCH IT coaching", "▶ WATCH IT" in FIX and "TRY AGAIN →" in FIX)
check("Focus still uses WATCH IT coaching", "▶ WATCH IT" in FOCUS and "TRY AGAIN →" in FOCUS)

print(f"v2.19.3 Model Rerender Hotfix: PASS ({len(checks)}/{len(checks)} checks)")
