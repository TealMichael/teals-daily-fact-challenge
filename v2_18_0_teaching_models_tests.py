from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
import re

from alternate_teaching import teaching_plan_for_question
from daily_modes import questions_for_mode
from fact_coach import coach_plan
from fact_engine import APP_VERSION, CHALLENGE_VERSION
from fact_store import InMemoryFactStore

ROOT = Path(__file__).resolve().parent
checks: list[str] = []


def check(label: str, value) -> None:
    if not value:
        raise AssertionError(label)
    checks.append(label)


check("v2.18 version", APP_VERSION == "2.18.0")
check("multiplication challenge unchanged", CHALLENGE_VERSION == "TDFC-DAILY-v1")

# Canonical high-quality model choices.
cases = [
    ({"prompt": "7 + 8", "category": "Addition Facts"}, "make_ten", "ten_frame", 15),
    ({"prompt": "6 + 6", "category": "Addition Facts"}, "double", "double", 12),
    ({"prompt": "4 + 5", "category": "Addition Facts"}, "near_double", "near_double", 9),
    ({"prompt": "2 + 6", "category": "Addition Facts"}, "count_on", "number_line", 8),
    ({"prompt": "0 + 9", "category": "Addition Facts"}, "add_zero", "counters", 9),
    ({"prompt": "14 − 6", "category": "Subtraction Facts"}, "missing_addend", "part_whole", 8),
    ({"prompt": "9 − 0", "category": "Subtraction Facts"}, "subtract_zero", "part_whole", 9),
    ({"prompt": "7 − 7", "category": "Subtraction Facts"}, "take_all", "part_whole", 0),
    ({"prompt": "42 ÷ 6", "category": "Division Facts"}, "think_multiplication", "equal_groups", 7),
    ({"prompt": "-4 + 7", "category": "Integers"}, "integer_add_right", "integer_line", 3),
    ({"prompt": "-2 + (-8)", "category": "Integers"}, "integer_add_left", "integer_line", -10),
    ({"prompt": "5 − (-3)", "category": "Integers"}, "integer_subtract_right", "integer_line", 8),
    ({"prompt": "4 − 7", "category": "Integers"}, "integer_subtract_left", "integer_line", -3),
]
for q, strategy, visual, answer in cases:
    plan = teaching_plan_for_question(q)
    check(f"strategy {q['prompt']}", plan.strategy_id == strategy)
    check(f"visual {q['prompt']}", plan.visual_type == visual)
    check(f"recap contains result {q['prompt']}", str(answer) in plan.recap)
    check(f"final equation contains result {q['prompt']}", str(answer) in plan.final_equation)
    check(f"model has three teaching steps {q['prompt']}", len(plan.steps) >= 3)

# Specific mathematical model quality.
add = teaching_plan_for_question({"prompt": "7 + 8", "category": "Addition Facts"})
check("make-ten creates a full ten", add.visual["target"] + add.visual["move"] == 10)
check("make-ten conserves source", add.visual["move"] + add.visual["remainder"] == add.visual["source"])
check("make-ten total remains 15", 10 + add.visual["remainder"] == add.visual["total"] == 15)
sub = teaching_plan_for_question({"prompt": "14 − 6", "category": "Subtraction Facts"})
check("subtraction part-whole recombines", sub.visual["known"] + sub.visual["unknown"] == sub.visual["total"] == 14)
div = teaching_plan_for_question({"prompt": "42 ÷ 6", "category": "Division Facts"})
check("division equal groups reconstruct dividend", div.visual["groups"] * div.visual["size"] == div.visual["total"] == 42)
integer = teaching_plan_for_question({"prompt": "5 − (-3)", "category": "Integers"})
check("integer line lands at correct value", integer.visual["start"] + integer.visual["delta"] == integer.visual["end"] == 8)
check("subtract negative explicitly teaches right movement", "right" in integer.relationship.casefold())

# Mixed multiplication borrows the exact existing Fact Coach strategy plan, read-only.
mixed_mul = teaching_plan_for_question({"prompt": "7 × 8", "category": "Multiplication"})
source_mul = coach_plan(7, 8)
check("Mixed multiplication uses multiplication array", mixed_mul.visual_type == "multiplication_array")
check("Mixed multiplication strategy mirrors Fact Coach", mixed_mul.strategy_id == f"mixed_{source_mul.strategy_id}")
check("Mixed multiplication relationship mirrors Fact Coach", mixed_mul.relationship == source_mul.relationship)
check("Mixed multiplication final equation mirrors Fact Coach", mixed_mul.final_equation == source_mul.final_equation)

# Every generated alternate question across a full leap-free school year gets a deterministic, correct model.
def expected_answer(q: dict) -> int:
    return int(q["correct_answer"])

def validate_plan_math(q: dict, plan) -> bool:
    ans = expected_answer(q)
    v = plan.visual
    if plan.visual_type == "ten_frame":
        return int(v["target"]) + int(v["move"]) == 10 and 10 + int(v["remainder"]) == ans
    if plan.visual_type in ("double", "near_double", "counters"):
        return str(ans) in plan.final_equation
    if plan.visual_type == "number_line":
        return int(v["start"]) + int(v["delta"]) == int(v["end"]) == ans
    if plan.visual_type == "part_whole":
        return int(v["known"]) + int(v["unknown"]) == int(v["total"]) and int(v["unknown"]) == ans
    if plan.visual_type == "equal_groups":
        return int(v["groups"]) * int(v["size"]) == int(v["total"]) and int(v["size"]) == ans
    if plan.visual_type == "integer_line":
        return int(v["start"]) + int(v["delta"]) == int(v["end"]) == ans
    if plan.visual_type == "multiplication_array":
        return str(ans) in plan.final_equation
    return False

start = date(2026, 1, 1)
for offset in range(365):
    day = start + timedelta(days=offset)
    for mode in ("Addition Facts", "Subtraction Facts", "Division Facts", "Integers", "Mixed"):
        questions = questions_for_mode(day, mode)
        for q in questions:
            plan1 = teaching_plan_for_question(q, None if mode == "Mixed" else mode)
            plan2 = teaching_plan_for_question(q, None if mode == "Mixed" else mode)
            if plan1 != plan2:
                raise AssertionError(f"nondeterministic model {day} {mode} {q}")
            if not validate_plan_math(q, plan1):
                raise AssertionError(f"bad model math {day} {mode} {q} {plan1}")
check("all 2026 generated alternate questions have deterministic correct models", True)

# The student flow now sends model plans into the follow-up component.
student_ui = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
component = (ROOT / "alt_fix_component" / "index.html").read_text(encoding="utf-8")
check("student UI imports alternate teaching", "from alternate_teaching import teaching_plan_for_question" in student_ui)
check("student UI builds model items", "model_items" in student_ui and '"model": plan.as_dict()' in student_ui)
check("student UI uses teaching component v2", 'version="TDFC-ALT-FIX-v2"' in student_ui)
check("model component starts every missed item in coach", "phase:'coach'" in component and "state.phase='coach'" in component)
check("model component has multiplication-style learning stages", "SEE IT" in component and "CONNECT IT" in component and "YOUR TURN" in component)
check("model component has watch and replay", "▶ WATCH IT" in component and "↻ REPLAY" in component)
check("model component requires Try Again after coaching", "TRY AGAIN →" in component)
check("model component supports addition ten frames", "ten_frame" in component and "ten-block" in component)
check("model component supports subtraction part whole", "part_whole" in component and "bar-known" in component)
check("model component supports division equal groups", "equal_groups" in component and "group-box" in component)
check("model component supports integer number line", "integer_line" in component and "number-line" in component and "walker" in component)
check("model component supports Mixed multiplication arrays", "multiplication_array" in component and "mult-array" in component)
check("retry recap remains visible", "boss-hint" in component and "m.recap" in component)
check("wrong retry stays on same question", "Almost — use the model and try once more." in component)
check("component allows negative integer answers", "toggleMinus" in component and 'id="minus"' in component)
check("component does not print the answer directly before retry", "${item.correct_answer}" not in component)
# Rapid multi-digit entry should only update the answer display, not rebuild the root.
add_digit_body = re.search(r"function addDigit\(d\)\{(.*?)\}\nfunction toggleMinus", component, re.S).group(1)
check("alternate teaching keypad keeps DOM stable between digits", "render()" not in add_digit_body and "updateEntry()" in add_digit_body)

# v2.17 storage/follow-up contract remains intact; no new migration is needed for teaching presentation.
check("v2.17 learning migration retained", (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_17.sql").exists())
check("v2.18 adds no migration", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_18.sql").exists())
check("alternate teaching does not import adaptive engine", "adaptive_engine" not in (ROOT / "alternate_teaching.py").read_text())
check("alternate teaching does not import stores", "fact_store" not in (ROOT / "alternate_teaching.py").read_text() and "supabase_fact_store" not in (ROOT / "alternate_teaching.py").read_text())

# End-to-end storage behavior remains v2.17: models change presentation, not official scores/mastery.
for mode in ("Addition Facts", "Subtraction Facts", "Division Facts", "Integers", "Mixed"):
    store = InMemoryFactStore()
    klass = store.create_class("Block 1")
    student = store.create_student(klass.class_id, "Falcon", "2468")
    # Challenge facts remain multiplication-owned even for alternate UI.
    from fact_engine import daily_facts_for_date
    challenge = store.get_or_create_challenge(date(2026, 9, 2), CHALLENGE_VERSION, daily_facts_for_date(date(2026, 9, 2)))
    questions = questions_for_mode(date(2026, 9, 2), mode)
    attempt = store.get_or_create_attempt(student.student_id, challenge.challenge_id, daily_mode=mode, custom_questions=questions)
    values = [int(q["correct_answer"]) for q in questions]
    values[0] += 1
    saved = store.complete_custom_attempt(attempt.attempt_id, values, 19.5)
    check(f"{mode} official score remains original", saved.correct_count == 9)
    miss_q = questions[0]
    plan = teaching_plan_for_question(miss_q, None if mode == "Mixed" else mode)
    check(f"{mode} missed item has model", bool(plan.title and plan.recap))
    store.record_alternate_fix_batch(attempt.attempt_id, [{"question_number": 1, "student_answer": int(miss_q["correct_answer"])}])
    saved_after = store.get_attempt(attempt.attempt_id)
    check(f"{mode} correction does not rewrite Daily score", saved_after.correct_count == 9)
    check(f"{mode} teaching remains outside multiplication mastery", store.get_mastery(student.student_id) == [])

# Hard multiplication/source-of-truth protection. These hashes are the known-good v2.17 files.
expected_hashes = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "daily_modes.py": "2e6633604d9ea2f21b4054e38827eea1eec99f47e5562befa4c1e62f840f3b5e",
    "student_igniter_ui.py": "043f3905b3e37a926cbae66d40de5e9ff963b2af3676f6bc4678336ca08e39ed",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
}
# Keep this explicit instead of relying on a prior package at test time.
for rel, expected in expected_hashes.items():
    check(f"multiplication gold-standard unchanged {rel}", sha256((ROOT / rel).read_bytes()).hexdigest() == expected)

print(f"v2.18.0 Teaching Models: PASS ({len(checks)}/{len(checks)} checks)")
