from pathlib import Path

from fact_coach import coach_plan
from fact_engine import APP_VERSION, Fact

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
GUIDED = (ROOT / "guided_practice_component" / "index.html").read_text(encoding="utf-8")
COACH = (ROOT / "fact_coach.py").read_text(encoding="utf-8")
UI_HELPERS = (ROOT / "ui_helpers.py").read_text(encoding="utf-8")


def run():
    checks = {}
    checks["version 2.8.0"] = APP_VERSION == "2.13.0"
    checks["coach module imported"] = "from fact_coach import" in APP
    checks["guided items receive coach plan"] = '"coach": coach_plan_for_fact(fact)' in APP
    checks["fix starts in coach"] = 'start_state="coach"' in APP
    checks["focus resumes in coach"] = 'start_state="coach" if first is not None and not first.correct else "question"' in APP
    checks["extra Practice uses same coach"] = 'mode="practice"' in APP and 'step_label="Extra Practice"' in APP

    seven = coach_plan(7, 7)
    checks["7x7 uses 5 plus 2"] = seven.strategy_id == "five_plus_two" and seven.first_groups == 5 and seven.second_groups == 2
    checks["7x7 anchor is 5x7"] = (seven.anchor_a, seven.anchor_b, seven.anchor_answer) == (5, 7, 35)
    checks["7x7 combines to 49"] = seven.second_equation == "2 × 7 = 14" and seven.combine_equation == "35 + 14 = 49" and seven.final_equation == "7 × 7 = 49"

    turned = coach_plan(7, 4)
    checks["commutative rotation taught explicitly"] = turned.groups == 4 and turned.size == 7 and "Turn it around: 7 × 4 = 4 × 7" in turned.relationship
    checks["retry returns to original orientation"] = turned.final_equation == "7 × 4 = 28"

    expected = {
        (4, 7): "double_double",
        (6, 8): "five_plus_one",
        (7, 8): "five_plus_two",
        (8, 8): "ten_minus_two",
        (9, 6): "ten_minus_one",
        (11, 7): "ten_plus_one",
        (12, 7): "ten_plus_two",
    }
    checks["priority fact strategies"] = all(coach_plan(*fact).strategy_id == strategy for fact, strategy in expected.items())

    # Every supported fact has a mathematically consistent plan.
    all_plans_ok = True
    anchor_plans = 0
    direct_plans = 0
    for a in range(2, 13):
        for b in range(2, 13):
            plan = coach_plan(a, b)
            if plan.groups * plan.size != a * b:
                all_plans_ok = False
            if str(a * b) not in plan.final_equation:
                all_plans_ok = False
            if plan.needs_anchor:
                anchor_plans += 1
                if plan.anchor_a * plan.anchor_b != plan.anchor_answer:
                    all_plans_ok = False
            else:
                direct_plans += 1
    checks["all 2-12 plans mathematically consistent"] = all_plans_ok
    checks["library includes anchor and direct teaching"] = anchor_plans > 0 and direct_plans > 0

    checks["browser-local array animation"] = "startTeachSequence" in GUIDED and "seq-see" in GUIDED and "coachArrayMarkup" in GUIDED
    checks["additive split visual"] = "split_add" in GUIDED and "part-a" in GUIDED and "part-b" in GUIDED
    checks["subtractive visual"] = "split_subtract" in GUIDED and "coach-cell.removed" in GUIDED and "opacity:.22" in GUIDED
    checks["student answers anchor"] = "anchor-fact" in GUIDED and "p.anchor_answer" in GUIDED
    checks["wrong anchor is retaught"] = "anchor-miss" in GUIDED and "p.anchor_answer" in GUIDED
    checks["combine stage"] = "PUT THE PARTS TOGETHER" in GUIDED and "combineMarkup" in GUIDED
    checks["final retry stage"] = "Now you try it" in GUIDED and "phase='retry'" in GUIDED
    checks["coach motto"] = "See it · Connect it · Solve it" in GUIDED

    # Critical data rule: scaffolded anchor answers never enter the server evidence list.
    submit_slice = GUIDED[GUIDED.index("function submitAnswer()"):GUIDED.index("function submitSession()")]
    anchor_branch = submit_slice[submit_slice.index("Scaffolded anchor retrieval"):submit_slice.index("const isRetry")]
    checks["anchor excluded from mastery evidence"] = "recordOriginalAttempt" not in anchor_branch and "events.push" not in anchor_branch
    checks["first Focus miss still recorded"] = "recordOriginalAttempt(item, value, isRetry)" in submit_slice
    checks["retry remains marked retry"] = "phase === 'retry'" in submit_slice and "is_retry:!!isRetry" in GUIDED
    checks["component submits batch only at end"] = "setValue({submitted:true" in GUIDED and "function submitSession()" in GUIDED
    checks["digit taps remain browser local"] = "setValue(" not in GUIDED[GUIDED.index("function addDigit"):GUIDED.index("function submitSession")]
    checks["session recovery retained"] = "sessionStorage.setItem" in GUIDED and "sessionStorage.getItem" in GUIDED
    checks["dynamic height retained"] = "ResizeObserver" in GUIDED and "scrollHeight" in GUIDED
    checks["keyboard retained"] = "document.addEventListener('keydown'" in GUIDED

    # Teacher-facing strategy text now uses the same plan rather than a contradictory square-fact rule.
    checks["teacher strategy aligned to coach"] = "plan = coach_plan(fact.a, fact.b)" in UI_HELPERS and "Put it together" in UI_HELPERS
    checks["old square-only strategy removed"] = "This is a square fact" not in APP

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.8 Interactive Fact Coach regression: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
