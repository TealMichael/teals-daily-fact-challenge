from pathlib import Path

from fact_engine import APP_VERSION

ROOT = Path(__file__).resolve().parent
GUIDED = (ROOT / "guided_practice_component" / "index.html").read_text(encoding="utf-8")


def run():
    checks = {}
    checks["version 2.8.3"] = APP_VERSION == "2.11.0.1"
    checks["short visual stages"] = all(text in GUIDED for text in ["SEE IT", "BREAK IT", "YOUR TURN", "PUT IT TOGETHER", "TRY AGAIN"])
    checks["whole array transforms after appearing"] = "seq-see" in GUIDED and "seq-break" in GUIDED and "background:var(--orange)" in GUIDED and "background:var(--purple)" in GUIDED
    checks["subtraction visibly fades removed groups"] = ".coach-cell.removed" in GUIDED and "opacity:.22" in GUIDED
    checks["anchor question waits for visual"] = "coachSequenceReady = false" in GUIDED and ".coach-card.seq-turn .coach-question" in GUIDED
    checks["equations reveal in stages"] = "eq-step-1" in GUIDED and "eq-step-4" in GUIDED and "finalPop" in GUIDED and "combine-action" in GUIDED
    checks["written explanation optional"] = "details class=\"why\"" in GUIDED and "<summary>💡 Why?</summary>" in GUIDED
    checks["digit taps do not rerender"] = "saveLocal(); updateDigitDisplay();" in GUIDED and "saveLocal(); render();" not in GUIDED[GUIDED.index("function addDigit"):GUIDED.index("function recordOriginalAttempt")]
    checks["browser local evidence rule retained"] = "Scaffolded anchor retrieval is deliberately NOT sent as mastery evidence" in GUIDED
    checks["batch submit retained"] = "function submitSession()" in GUIDED and "setValue({submitted:true" in GUIDED
    checks["no sound or audio"] = all(token not in GUIDED.lower() for token in ["<audio", "audiocontext", "new audio(", "speechsynthesis"])
    checks["reduced motion supported"] = "prefers-reduced-motion" in GUIDED
    checks["low-reading miss card"] = "Missed: ${item.a} × ${item.b}" in GUIDED and "worth learning, not just memorizing" not in GUIDED
    checks["silent visual success"] = "✅ Nice!" in GUIDED and "flash-good" in GUIDED

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.8.3 Visual Fact Coach regression: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
