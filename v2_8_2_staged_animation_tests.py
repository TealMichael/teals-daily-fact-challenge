from pathlib import Path
from fact_engine import APP_VERSION

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "guided_practice_component" / "index.html").read_text()
APP = (ROOT / "app.py").read_text()

checks = {
    "version 2.8.3": APP_VERSION == "2.8.3",
    "explicit WATCH IT gate": "▶ WATCH IT" in HTML and 'id="watch-coach"' in HTML,
    "student can replay": "↻ REPLAY" in HTML and 'id="replay-coach"' in HTML,
    "teach sequence is JS staged": "function startTeachSequence()" in HTML,
    "whole array stage": "seq-see" in HTML and "later(120" in HTML,
    "relationship transform stage": "seq-break" in HTML and "later(1050" in HTML,
    "anchor question waits": "coachSequenceReady = false" in HTML and "seq-turn" in HTML,
    "question hidden before stage": ".coach-question { display:none" in HTML,
    "keypad blocked before animation": "&& !coachSequenceReady) return" in HTML,
    "subtraction removes groups visually": ".coach-cell.removed" in HTML and "opacity:.22" in HTML,
    "additive parts recolor": "background:var(--orange)" in HTML and "background:var(--purple)" in HTML,
    "combine equations are staged": "eq-step-1" in HTML and "eq-step-4" in HTML,
    "final answer pops": "finalPop" in HTML,
    "retry waits for explanation": "action-ready" in HTML,
    "reduce motion still stages math": "Accessibility: remove motion, but JS still reveals each math stage in order" in HTML,
    "reduce motion does not force all content visible": "opacity:1 !important" not in HTML,
    "silent classroom coach": all(token not in HTML.lower() for token in ("<audio", "audiocontext", "speechsynthesis", ".play()")),
    "guided component still browser local": "streamlit:setComponentValue" in HTML and "submitSession" in HTML,
    "teacher dashboard filter fix retained": "family_options" in APP or "heat_filter" in APP,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("PASS" if ok else "FAIL") + ": " + name)
if failed:
    raise AssertionError(f"{len(failed)} staged-animation checks failed: {failed}")
print(f"v2.8.3 staged animation regression: {len(checks)}/{len(checks)} checks passed")
