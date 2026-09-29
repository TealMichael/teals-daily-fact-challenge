from __future__ import annotations

"""Focused regression checks for v2.22.0 Indiana Standards Question Bank."""

from collections import Counter
from pathlib import Path

from curriculum_question_types import numeric_value
from fact_engine import APP_VERSION
from indiana_math_standards import BY_CODE, ESSENTIAL_CODES, STANDARDS
from indiana_question_bank import (
    EXPECTED_QUESTION_COUNT,
    EXPECTED_STANDARD_COUNT,
    SUPPORTED_BANK_TYPES,
    all_questions,
    bank_summary,
    domains_for_grade,
    questions_for_standard,
    resolve_bank_image_path,
    standard_codes_for,
)
from warmup import prepare_question
from weekly_quiz import prepare_quiz_question

checks: list[str] = []

def check(name: str, condition: bool):
    if not condition:
        raise AssertionError(name)
    checks.append(name)

rows = all_questions()
check("current version", APP_VERSION == "2.23.0")
check("750 questions", len(rows) == EXPECTED_QUESTION_COUNT == 750)
check("unique ids", len({row["id"] for row in rows}) == 750)

counts = Counter(row["standard_code"] for row in rows)
check("75 standards", len(counts) == EXPECTED_STANDARD_COUNT == 75)
check("ten per standard", set(counts.values()) == {10})
check("grade question counts", Counter(row["grade"] for row in rows) == {5: 260, 6: 250, 7: 240})

standards_5_7 = [standard for standard in STANDARDS if standard.grade in (5, 6, 7)]
check("all grade 5-7 standards represented", {s.code for s in standards_5_7} == set(counts))
check("42 essential standards", len(ESSENTIAL_CODES) == 42)
check("14 essential per grade", Counter(int(code.split(".", 1)[0]) for code in ESSENTIAL_CODES) == {5: 14, 6: 14, 7: 14})
check("420 essential questions", sum(bool(row["essential"]) for row in rows) == 420)

for row in rows:
    qid = row["id"]
    qtype = row["question_type"]
    check(f"{qid} supported type", qtype in SUPPORTED_BANK_TYPES)
    check(f"{qid} prompt", bool(str(row.get("prompt") or "").strip()))
    check(f"{qid} answer", bool(str(row.get("correct_answer") or "").strip()))
    standard = BY_CODE[row["standard_code"]]
    check(f"{qid} grade matches standard", int(row["grade"]) == standard.grade)
    check(f"{qid} domain matches standard", str(row["domain"]) == standard.domain)
    check(f"{qid} description matches standard", str(row["standard_description"]) == standard.description)
    check(f"{qid} essential flag matches standard", bool(row["essential"]) == (row["standard_code"] in ESSENTIAL_CODES))
    if qtype in {"Number", "Fraction", "Number + Label"}:
        check(f"{qid} numeric answer parses", numeric_value(row["correct_answer"]) is not None)
    if qtype == "Multiple choice":
        options = list(row.get("options") or ())
        check(f"{qid} four options", len(options) == 4)
        check(f"{qid} unique options", len(options) == len(set(options)))
        check(f"{qid} correct option present", row["correct_answer"] in options)
    if qtype == "Number + Label":
        labels = list(row.get("label_options") or ())
        check(f"{qid} label choices", len(labels) >= 2)
        check(f"{qid} correct label present", row["correct_label"] in labels)
    bank_image = str(row.get("bank_image_path") or "")
    if bank_image:
        check(f"{qid} bank image exists", bool(resolve_bank_image_path(bank_image)))


# Content sentinels for issues caught during manual v2.22.0 bank QA.
by_id = {row["id"]: row for row in rows}
check("whole-number division sentinel", by_id["5.CA.1-Q03"]["correct_answer"] == "40")
check("grade 5 comparison sentinel", by_id["5.NS.1-Q04"]["correct_answer"] == "6/5")
check("marathon conversion sentinel", by_id["6.GM.1-Q10"]["correct_answer"] == "42.16" and "nearest hundredth" in by_id["6.GM.1-Q10"]["prompt"])
check("equation context sentinel", "game costs $6 less than a book" in by_id["6.AF.3-Q09"]["prompt"] and by_id["6.AF.3-Q09"]["correct_answer"] == "28")
check("negative slope sentinel", by_id["7.AF.6-Q07"]["options"].count("Down 3 and right 4") == 1)
check("outlier mean sentinel", by_id["7.DSP.3-Q05"]["correct_answer"] == "10.83")

# The loader/filter API should match the bank manifest.
check("grade 5 domains", len(domains_for_grade(5)) >= 5)
check("grade 6 domains", len(domains_for_grade(6)) >= 5)
check("grade 7 domains", len(domains_for_grade(7)) >= 5)
check("grade 5 standard count", len(standard_codes_for(5)) == 26)
check("grade 6 standard count", len(standard_codes_for(6)) == 25)
check("grade 7 standard count", len(standard_codes_for(7)) == 24)
check("essential filters", sum(len(standard_codes_for(g, essential_only=True)) for g in (5, 6, 7)) == 42)
check("ten volume questions", len(questions_for_standard("5.M.5")) == 10)

# Every bank question must survive the normal Igniter + Quiz preparation models.
for code in counts:
    for row in questions_for_standard(code):
        warmup = prepare_question(
            slot=1,
            prompt=row["prompt"],
            question_type=row["question_type"],
            correct_answer=row["correct_answer"],
            standard_code=row["standard_code"],
            standard_description=row["standard_description"],
            options=row.get("options") or (),
            accepted_answers=row.get("accepted_answers") or (),
            label_options=row.get("label_options") or (),
            correct_label=row.get("correct_label") or "",
            bank_image_path=row.get("bank_image_path") or "",
            bank_image_alt=row.get("bank_image_alt") or "",
            bank_question_id=row["id"],
        )
        quiz = prepare_quiz_question(
            slot=1,
            prompt=row["prompt"],
            question_type=row["question_type"],
            correct_answer=row["correct_answer"],
            options=row.get("options") or (),
            accepted_answers=row.get("accepted_answers") or (),
            label_options=row.get("label_options") or (),
            correct_label=row.get("correct_label") or "",
            bank_image_path=row.get("bank_image_path") or "",
            bank_image_alt=row.get("bank_image_alt") or "",
            bank_question_id=row["id"],
        )
        check(f"{row['id']} warmup bank id preserved", warmup.get("bank_question_id") == row["id"])
        check(f"{row['id']} quiz bank id preserved", quiz.get("bank_question_id") == row["id"])

summary = bank_summary()
check("summary counts", summary == {"questions": 750, "standards": 75, "essential_standards": 42, "essential_questions": 420})

app_text = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
check("question bank teacher navigation", "📚 Question Bank" in app_text and "render_teacher_question_bank" in app_text)
check("no new Supabase dependency", "indiana_question_bank" not in Path(__file__).with_name("supabase_fact_store.py").read_text(encoding="utf-8"))

print(f"v2_22_0_question_bank_tests: PASS ({len(checks)}/{len(checks)})")
