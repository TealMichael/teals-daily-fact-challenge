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

check("current version", APP_VERSION == "2.19.7")
ui = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
fix = (ROOT / "alt_fix_component" / "index.html").read_text(encoding="utf-8")
focus = (ROOT / "alt_focus_component" / "index.html").read_text(encoding="utf-8")
daily = (ROOT / "daily_alt_component" / "index.html").read_text(encoding="utf-8")

check("Fix component browser identity current", '"tdfc_alt_fix_v2197"' in ui)
check("Focus component browser identity current", '"tdfc_alt_focus_v2197"' in ui)
check("Fix stored state version current", 'version="TDFC-ALT-FIX-v4"' in ui and "tdfc-alt-fix-v4:" in fix)
check("Focus stored state version current", 'version="TDFC-ALT-FOCUS-v3"' in ui and "tdfc-alt-focus-v3:" in focus)
check("alternate Daily keypad display fix retained", 'id="entry"' in daily and "entry.textContent=digits||'Tap your answer'" in daily)

for label, src in (("Fix", fix), ("Focus", focus)):
    compact = src.replace(" ", "")
    check(f"{label} does not auto-play coaching", "function startTeachSequence()" in src)
    check(f"{label} Watch uses multiplication-style click", "watch.addEventListener('click',startTeachSequence)" in src)
    check(f"{label} Replay uses the same restart path", "replay.addEventListener('click',startTeachSequence)" in src)
    check(f"{label} avoids duplicate pointer/touch bindings", "addEventListener('pointerup'" not in src and "addEventListener('touchend'" not in src)
    check(f"{label} has no timestamp-rerender state machine", "coachStartedAt" not in src and "resumeSequence" not in src)
    check(f"{label} sequence survives same-session rerender by preserving DOM", "else{args=newArgs;setHeight()}" in compact)
    check(f"{label} paced like multiplication before Your Turn", "return [180,1350,2650]" in src)
    check(f"{label} Try Again stays locked until teaching reaches Your Turn", "if(!coachSequenceReady)return" in src)
    check(f"{label} Try Again transitions to retry", "const next=document.getElementById('to-retry')" in src and "state.phase='retry'" in src)
    check(f"{label} keypad digit buttons bound", "querySelectorAll('[data-digit]')" in src and "addDigit" in src)
    check(f"{label} minus button bound", "getElementById('minus')" in src and "toggleMinus" in src)
    check(f"{label} delete button bound", "getElementById('erase')" in src and "erase" in src)
    check(f"{label} green check bound", "getElementById('submit')" in src and "submit" in src)
    check(f"{label} retry keypad displays typed answer", 'id="entry"' in src and "el.textContent=digits||'Tap your answer'" in src)

check("Fix records only corrected retry answers", "value!==Number(item.correct_answer)" in fix and "state.corrections.push" in fix)
check("Focus miss enters coach before retry", "state.phase='coach'" in focus and "if(isRetry)" in focus)
check("Focus retry remains required after a second miss", "state.retryMissed=true" in focus)

supported = {"ten_frame", "double", "near_double", "counters", "part_whole", "equal_groups", "integer_line", "number_line", "multiplication_array"}
start = date(2026, 1, 1)
for mode in ALT_MODES:
    seen = set()
    for offset in range(365):
        day = start + timedelta(days=offset)
        for question in questions_for_mode(day, mode):
            plan = teaching_plan_for_question(question, None if mode == "Mixed" else mode)
            seen.add(plan.visual_type)
            if plan.visual_type not in supported:
                raise AssertionError(f"unsupported teaching visual {plan.visual_type!r} for {mode}: {question}")
            if not plan.final_equation or not plan.steps:
                raise AssertionError(f"incomplete teaching plan for {mode}: {question}")
    check(f"{mode} 2026 Daily questions all build teaching models", bool(seen))

EXPECTED_MULTIPLICATION = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
}
for rel, expected in EXPECTED_MULTIPLICATION.items():
    actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    check(f"multiplication source unchanged: {rel}", actual == expected)

print(f"Alternate Follow-Up Parity Regression: PASS ({CHECKS}/{CHECKS} checks)")
