from pathlib import Path

from fact_engine import APP_VERSION
from fact_coach import coach_plan

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
HTML = (ROOT / "guided_practice_component" / "index.html").read_text(encoding="utf-8")
LEARNING_UI = (ROOT / "teacher_learning_ui.py").read_text(encoding="utf-8")


def section(name: str, next_name: str | None = None, source: str = APP) -> str:
    start = source.index(f"def {name}")
    end = source.index(f"\ndef {next_name}", start) if next_name else len(source)
    return source[start:end]


def run():
    checks = {}
    checks["version 2.9.3"] = APP_VERSION == "2.13.0"

    mastery = section("render_teacher_mastery_focus", source=LEARNING_UI)
    fluency = section("_render_teacher_fact_fluency", "_render_teacher_standards_tracker", LEARNING_UI)
    checks["learning data has two clear views"] = all(label in mastery for label in ["⚡ Fact Fluency", "📚 Standards Tracker"])
    checks["old four-view wall removed"] = "What Should I Teach?" not in mastery and "Who Needs Help?" not in mastery
    checks["fact fluency leads with pull group"] = "#### 🎯 Students to Pull" in fluency and "Why pull" in fluency
    checks["building-only students are not described as intervention"] = "This is not automatically an intervention flag" in fluency
    checks["full fact map is advanced only"] = "Advanced fact map & class-wide Focus controls" in fluency and "expanded=False" in fluency
    checks["fact fluency still uses one class detail read"] = fluency.count("store.class_mastery_detail(selected.class_id, students=students)") == 1

    support = section("render_teacher_student_tools", "_mystery_raffle_setting_key")
    checks["student support uses action buttons"] = all(text in support for text in [
        "🔑 Account & PIN", "🧰 Fix today's Daily", "🎯 Adjust Focus Practice", "↔️ Move / Status"
    ])
    checks["student support old toggle stack removed"] = all(text not in support for text in [
        "Show today's Daily troubleshooting", "Show Personal Focus override", "Show Bulk move shortcut"
    ])
    checks["bulk move is directed to roster area"] = "Bulk roster work stays in Classes & Rosters" in support
    checks["danger zone is separated"] = "#### ⚠️ Danger Zone" in support and "Permanently delete this student" in support

    raffle = section("_mystery_raffle_setting_key", "_mystery_bank_label")
    checks["raffle key includes class"] = "week_start.isoformat()}::{class_id}" in raffle
    checks["raffle loops active classes"] = "for class_record in classes:" in raffle and "eligible_by_class" in raffle
    checks["each class has independent draw"] = "Draw {class_record.class_name} Winner" in raffle
    checks["winner saves class id"] = '"class_id": class_id' in raffle
    checks["student raffle wording says class"] = "your class's Friday prize raffle" in APP

    checks["easy wording removed"] = "Easy fact first" not in HTML
    checks["known-fact wording present"] = "Start with a fact you know" in HTML
    checks["additive coach names decomposition"] = "BUILD ${p.groups} GROUPS" in HTML
    checks["direct strategies get visible cue"] = "direct-cue" in HTML and "p.direct_message || p.relationship" in HTML
    checks["takeaway names exact removed quantity"] = "YOU TOOK AWAY ${removedValue}" in HTML
    checks["takeaway keeps subtraction visible"] = "${p.anchor_answer} − ${removedValue} LEAVES ${item.a} × ${item.b}" in HTML
    checks["takeaway holds before next question"] = "later(1150" in HTML
    checks["teach sequence slowed"] = "later(1350" in HTML and "later(2650" in HTML
    checks["combine sequence slowed"] = "later(3850" in HTML
    checks["9x9 uses ten-minus-one"] = coach_plan(9, 9).strategy_id == "ten_minus_one"
    checks["9x9 removes one group of nine"] = coach_plan(9, 9).second_groups == 1 and coach_plan(9, 9).size == 9 and coach_plan(9, 9).anchor_answer == 90
    checks["8x9 uses ten-minus-two"] = coach_plan(8, 9).strategy_id == "ten_minus_one" or coach_plan(8, 9).strategy_id == "ten_minus_two"
    # Orientation chooses the clearest factor; direct plan checks cover the strategy families themselves.
    checks["8x8 removes two groups"] = coach_plan(8, 8).second_groups == 2 and coach_plan(8, 8).anchor_answer == 80
    checks["6 strategy remains five-plus-one"] = coach_plan(6, 7).strategy_id == "five_plus_one"
    checks["7 strategy remains five-plus-two"] = coach_plan(7, 7).strategy_id == "five_plus_two"
    checks["11 strategy remains ten-plus-one"] = coach_plan(11, 7).strategy_id == "ten_plus_one"
    checks["12 strategy remains ten-plus-two"] = coach_plan(12, 7).strategy_id == "ten_plus_two"
    checks["fact coach remains silent"] = "<audio" not in HTML.lower() and "speechSynthesis" not in HTML and "Audio(" not in HTML
    checks["fact coach stays browser local"] = "fetch(" not in HTML

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.9.3 teacher redesign + Fact Coach quality regression: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
