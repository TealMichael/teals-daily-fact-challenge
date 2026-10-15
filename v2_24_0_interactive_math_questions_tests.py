from __future__ import annotations

from pathlib import Path
from datetime import date

from curriculum_question_types import (
    COMMON_QUESTION_TYPES,
    COMPARE_QUESTION_TYPE,
    ORDER_QUESTION_TYPE,
    comparison_answer_matches,
    comparison_symbol,
    deterministic_start_order,
    order_response_matches,
    pack_order_response,
    sorted_order_items,
)
from fact_engine import APP_VERSION
from fact_store import InMemoryFactStore
from indiana_question_bank import SUPPORTED_BANK_TYPES, question_by_id
from warmup import QUESTION_TYPES, grade_question, prepare_question
from weekly_quiz import QUIZ_QUESTION_TYPES, grade_quiz_response, prepare_quiz_question

ROOT = Path(__file__).resolve().parent
checks: list[str] = []


def check(name: str, condition: bool):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


check("release version", APP_VERSION == "2.24.4")
for qtype in (COMPARE_QUESTION_TYPE, ORDER_QUESTION_TYPE):
    check(f"{qtype} shared common type", qtype in COMMON_QUESTION_TYPES)
    check(f"{qtype} Igniter type", qtype in QUESTION_TYPES)
    check(f"{qtype} Quiz type", qtype in QUIZ_QUESTION_TYPES)
    check(f"{qtype} bank type", qtype in SUPPORTED_BANK_TYPES)

# Compare uses exact Fraction-backed math, not binary floating-point comparisons.
check("decimal compare less", comparison_symbol("0.507", "0.57") == "<")
check("decimal compare equivalent zeros", comparison_symbol("0.50", "0.5") == "=")
check("fraction decimal compare", comparison_symbol("7/10", "0.705") == "<")
check("mixed number compare", comparison_symbol("1 1/4", "1.2") == ">")
check("comparison grader", comparison_answer_matches("=", "0.500", "1/2"))

w_compare = prepare_question(
    slot=1, prompt="Compare.", question_type=COMPARE_QUESTION_TYPE,
    correct_answer="WRONG-IGNORED", standard_code="5.NS.1",
    compare_left="0.50", compare_right="0.5",
)
q_compare = prepare_quiz_question(
    slot=1, prompt="Compare.", question_type=COMPARE_QUESTION_TYPE,
    correct_answer="WRONG-IGNORED", standard_code="5.NS.1",
    compare_left="0.50", compare_right="0.5",
)
check("compare auto answer warmup", w_compare["correct_answer"] == "=")
check("compare auto answer quiz", q_compare["correct_answer"] == "=")
check("compare grading parity correct", grade_question(w_compare, "=") and grade_quiz_response(q_compare, "=")["correct"])
check("compare grading parity wrong", not grade_question(w_compare, "<") and not grade_quiz_response(q_compare, "<")["correct"])

items = ["0.45", "0.405", "0.54", "0.5"]
correct_order = sorted_order_items(items, "Least to greatest")
check("order canonical", correct_order == ["0.405", "0.45", "0.5", "0.54"])
packed = pack_order_response(correct_order)
check("order grader correct", order_response_matches(packed, items, "Least to greatest"))
check("order grader wrong", not order_response_matches(pack_order_response(list(reversed(correct_order))), items, "Least to greatest"))

# Equivalent values are allowed in either adjacent order.
equiv_items = ["0.5", "0.50", "0.45"]
check("equivalent order A", order_response_matches(pack_order_response(["0.45", "0.5", "0.50"]), equiv_items, "Least to greatest"))
check("equivalent order B", order_response_matches(pack_order_response(["0.45", "0.50", "0.5"]), equiv_items, "Least to greatest"))

w_order = prepare_question(
    slot=1, prompt="Order.", question_type=ORDER_QUESTION_TYPE,
    correct_answer="ignored", standard_code="5.NS.1",
    order_items=items, order_direction="Least to greatest",
)
q_order = prepare_quiz_question(
    slot=1, prompt="Order.", question_type=ORDER_QUESTION_TYPE,
    correct_answer="ignored", standard_code="5.NS.1",
    order_items=items, order_direction="Least to greatest",
)
check("order auto answer warmup", w_order["correct_answer"] == packed)
check("order auto answer quiz", q_order["correct_answer"] == packed)
check("order grading parity", grade_question(w_order, packed) and grade_quiz_response(q_order, packed)["correct"])


# Store round-trip: new question metadata lives inside existing JSON question sets,
# so no Supabase schema migration is required.
store = InMemoryFactStore()
klass = store.create_class("Interactive Test")
roundtrip_warmup = store.save_warmup_set(klass.class_id, date(2026, 10, 15), w_compare, w_order)
loaded_warmup = store.get_warmup_set(klass.class_id, date(2026, 10, 15))
check("warmup compare fields roundtrip", loaded_warmup.question_one["compare_left"] == "0.50" and loaded_warmup.question_one["compare_right"] == "0.5")
check("warmup order fields roundtrip", loaded_warmup.question_two["order_items"] == items and loaded_warmup.question_two["order_direction"] == "Least to greatest")
quiz_questions = []
for slot in range(1, 6):
    if slot % 2:
        quiz_questions.append(prepare_quiz_question(
            slot=slot, prompt="Compare.", question_type=COMPARE_QUESTION_TYPE, correct_answer="",
            standard_code="5.NS.1", compare_left="0.50", compare_right="0.5",
        ))
    else:
        quiz_questions.append(prepare_quiz_question(
            slot=slot, prompt="Order.", question_type=ORDER_QUESTION_TYPE, correct_answer="",
            standard_code="5.NS.1", order_items=items, order_direction="Least to greatest",
        ))
roundtrip_quiz = store.save_weekly_quiz_set(
    klass.class_id, date(2026, 10, 16), assignment_name="Interactive Quiz", category_code="SUMM", max_score=5, questions=quiz_questions
)
loaded_quiz = store.get_weekly_quiz_set(klass.class_id, date(2026, 10, 16))
check("quiz compare fields roundtrip", loaded_quiz.questions[0]["compare_left"] == "0.50")
check("quiz order fields roundtrip", loaded_quiz.questions[1]["order_items"] == items)

start_a = deterministic_start_order(items, seed="student-question", direction="Least to greatest")
start_b = deterministic_start_order(items, seed="student-question", direction="Least to greatest")
check("stable starting shuffle", start_a == start_b)
check("starting shuffle keeps tiles", sorted(start_a) == sorted(items))
check("starting shuffle not already solved", not order_response_matches(pack_order_response(start_a), items, "Least to greatest"))

# Built-in bank immediately demonstrates both new interactions for current Grade 5 work.
for qid, qtype in {
    "5.NS.1-Q02": ORDER_QUESTION_TYPE,
    "5.NS.1-Q03": COMPARE_QUESTION_TYPE,
    "5.NS.1-Q05": COMPARE_QUESTION_TYPE,
    "5.NS.1-Q06": ORDER_QUESTION_TYPE,
    "6.NS.3-Q02": ORDER_QUESTION_TYPE,
    "6.NS.3-Q03": COMPARE_QUESTION_TYPE,
    "6.NS.3-Q07": COMPARE_QUESTION_TYPE,
    "6.NS.3-Q09": ORDER_QUESTION_TYPE,
}.items():
    row = question_by_id(qid)
    check(f"{qid} exists", row is not None)
    check(f"{qid} interactive type", row["question_type"] == qtype)

component_source = (ROOT / "interactive_math_questions.py").read_text(encoding="utf-8")
check("component v2", "components" in component_source and "v2" in component_source and "component" in component_source)
check("touch pointer drag", "onpointerdown" in component_source and "onpointermove" in component_source and "onpointerup" in component_source)
check("component persists order", 'setStateValue("order"' in component_source)
check("keyboard reorder", 'event.key === "ArrowLeft"' in component_source and 'event.key === "ArrowRight"' in component_source)

for filename in ("student_igniter_ui.py", "student_weekly_quiz_ui.py", "student_recovery_ui.py"):
    source = (ROOT / filename).read_text(encoding="utf-8")
    check(f"{filename} order tiles UI", "render_order_tiles(" in source)
    check(f"{filename} compare UI", "COMPARISON_SYMBOLS" in source)

editor_source = (ROOT / "teacher_question_editor.py").read_text(encoding="utf-8")
check("teacher compare inputs", '"Left value"' in editor_source and '"Right value"' in editor_source)
check("teacher order inputs", '"Number tiles — one per line"' in editor_source and '"Order direction"' in editor_source)
check("no new SQL migration", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_24.sql").exists())

print(f"v2_24_0_interactive_math_questions_tests: PASS ({len(checks)}/{len(checks)})")
