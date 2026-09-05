from __future__ import annotations

"""Model-rerender reliability regression, updated for the v2.19.9 lifecycle.

The current fix follows multiplication's safer rule: same-session Streamlit render
messages do not rebuild the live teaching DOM, so WATCH/REPLAY timers cannot be
cleared by routine parent rerenders.
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

check("current version", APP_VERSION == "2.19.9")
for label, src in (("Fix", FIX), ("Focus", FOCUS)):
    check(f"{label} no longer depends on rerender timestamps", "coachStartedAt" not in src and "resumeSequence" not in src)
    check(f"{label} has multiplication-style start controller", "function startTeachSequence()" in src)
    check(f"{label} Watch binds directly to start controller", "watch.addEventListener('click',startTeachSequence)" in src)
    check(f"{label} Replay binds to same start controller", "replay.addEventListener('click',startTeachSequence)" in src)
    check(f"{label} sequence clears only its own timers", "clearTimers();resetTeachClasses(card)" in src)
    check(f"{label} uses multiplication pacing", "return [180,1350,2650]" in src)
    check(f"{label} same-session parent rerender does not call render", "else{args=newArgs;setHeight()}" in src.replace(" ", ""))
    check(f"{label} stale teach state normalizes to coach", "p.phase==='teach'" in src and "p.phase='coach'" in src)
    check(f"{label} still has Watch and Try Again", "▶ WATCH IT" in src and "TRY AGAIN →" in src)

print(f"Model Rerender Reliability: PASS ({len(checks)}/{len(checks)} checks)")
