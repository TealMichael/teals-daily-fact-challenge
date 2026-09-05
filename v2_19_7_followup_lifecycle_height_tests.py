from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import hashlib

from fact_engine import APP_VERSION
from daily_modes import questions_for_mode
from alternate_followup import ALT_MODES
from alternate_teaching import teaching_plan_for_question

ROOT = Path(__file__).resolve().parent
CHECKS = 0

def check(label: str, condition: bool) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1

check("v2.19.9 version", APP_VERSION == "2.19.9")
ui = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
fix = (ROOT / "alt_fix_component" / "index.html").read_text(encoding="utf-8")
focus = (ROOT / "alt_focus_component" / "index.html").read_text(encoding="utf-8")
daily = (ROOT / "daily_alt_component" / "index.html").read_text(encoding="utf-8")
mult = (ROOT / "guided_practice_component" / "index.html").read_text(encoding="utf-8")

check("Fix component identity advanced", '"tdfc_alt_fix_v2197"' in ui)
check("Focus component identity advanced", '"tdfc_alt_focus_v2197"' in ui)
check("Fix state contract advanced", 'version="TDFC-ALT-FIX-v4"' in ui and "tdfc-alt-fix-v4:" in fix)
check("Focus state contract advanced", 'version="TDFC-ALT-FOCUS-v3"' in ui and "tdfc-alt-focus-v3:" in focus)
check("alternate Daily typed-answer hotfix retained", 'id="entry"' in daily and "entry.textContent=digits||'Tap your answer'" in daily)

# Literal interaction contracts copied from the proven multiplication component.
check("multiplication uses startTeachSequence", "function startTeachSequence()" in mult)
check("multiplication Watch binds to startTeachSequence", "watch.addEventListener('click', startTeachSequence)" in mult)
check("multiplication Replay binds to startTeachSequence", "replay.addEventListener('click', startTeachSequence)" in mult)

for label, src in (("Fix", fix), ("Focus", focus)):
    compact = src.replace(" ", "")
    check(f"{label} has teach-view controller", 'class="coach-card teach-view"' in src and "function startTeachSequence()" in src)
    check(f"{label} Watch uses multiplication controller", "watch.addEventListener('click',startTeachSequence)" in src)
    check(f"{label} Replay uses same multiplication controller", "replay.addEventListener('click',startTeachSequence)" in src)
    check(f"{label} reset-before-replay behavior", "clearTimers();resetTeachClasses(card)" in src)
    check(f"{label} no timestamp/resume state machine", "coachStartedAt" not in src and "resumeSequence" not in src)
    check(f"{label} ignores routine same-key render instead of rebuilding DOM", "else{args=newArgs;setHeight()}" in compact)
    check(f"{label} stale teach phase normalizes safely", "p.phase==='teach'" in src and "p.phase='coach'" in src)
    check(f"{label} exact simple-stage pacing", "return [180,1350,2650]" in src)
    check(f"{label} Try Again stays blocked until sequence ready", "if(!coachSequenceReady)return" in src)
    check(f"{label} future visual stage removed from initial layout", ".coach-stage-visual,.coach-stage-connect,.coach-stage-turn{display:none}" in src)
    check(f"{label} SEE stage mounts visual content", ".coach-card.seq-see .coach-stage-visual" in src)
    check(f"{label} CONNECT stage mounts explanation", ".coach-card.seq-connect .coach-stage-connect" in src)
    check(f"{label} YOUR TURN stage mounts final action", ".coach-card.seq-turn .coach-stage-turn" in src)
    check(f"{label} height measures rendered root not stale viewport scrollHeight", "getBoundingClientRect()" in src and "document.documentElement.scrollHeight" not in src)
    check(f"{label} observes root for grow/shrink", "new ResizeObserver(setHeight).observe(rootObserverTarget)" in src)
    check(f"{label} session-scoped state like multiplication", "sessionStorage" in src)
    check(f"{label} no localStorage follow-up state", "localStorage" not in src)
    check(f"{label} keypad digit buttons bound", "querySelectorAll('[data-digit]')" in src)
    check(f"{label} minus bound", "getElementById('minus')" in src and "toggleMinus" in src)
    check(f"{label} delete bound", "getElementById('erase')" in src and "erase" in src)
    check(f"{label} checkmark bound", "getElementById('submit')" in src and "submit" in src)
    check(f"{label} typed answer display retained", 'id="entry"' in src and "el.textContent=digits||'Tap your answer'" in src)

# All generated alternate Daily content must still map to a visual supported by both copied controllers.
supported = {"ten_frame", "double", "near_double", "counters", "part_whole", "equal_groups", "integer_line", "number_line", "multiplication_array"}
seen = set()
start = date(2026, 1, 1)
for mode in ALT_MODES:
    for offset in range(365):
        day = start + timedelta(days=offset)
        for question in questions_for_mode(day, mode):
            plan = teaching_plan_for_question(question, None if mode == "Mixed" else mode)
            seen.add(plan.visual_type)
            if plan.visual_type not in supported:
                raise AssertionError(f"unsupported teaching visual {plan.visual_type!r} for {mode}: {question}")
            if not plan.final_equation or not plan.steps:
                raise AssertionError(f"incomplete teaching plan for {mode}: {question}")
    check(f"{mode} 2026 teaching models valid", True)
check("generated model family coverage remains broad", len(seen) >= 7)

# Multiplication remains literal source-of-truth bytes and is not edited by this release.
EXPECTED = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
}
for rel, expected in EXPECTED.items():
    actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    check(f"protected multiplication source unchanged: {rel}", actual == expected)

print(f"v2.19.9 Follow-Up Lifecycle + Height: PASS ({CHECKS}/{CHECKS} checks)")
