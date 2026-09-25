from __future__ import annotations

from datetime import date
from pathlib import Path

from fact_engine import APP_VERSION
from fact_store import InMemoryFactStore
from weekly_quiz import grade_quiz_response, pack_response, prepare_quiz_question, unpack_response

ROOT = Path(__file__).resolve().parent
checks = []

def check(name, condition):
    assert condition, name
    checks.append(name)

def questions():
    return [
        prepare_quiz_question(slot=1, prompt="Enter 3.", question_type="Number", correct_answer="3"),
        prepare_quiz_question(slot=2, prompt="Enter 3/4.", question_type="Fraction", correct_answer="3/4"),
        prepare_quiz_question(slot=3, prompt="Choose 12.", question_type="Multiple choice", correct_answer="12", options=["8", "10", "12", "14"]),
        prepare_quiz_question(slot=4, prompt="Area is 16 ___.", question_type="Number + Label", correct_answer="16", label_options=["feet", "square feet"], correct_label="square feet"),
        prepare_quiz_question(slot=5, prompt="Enter 7/3.", question_type="Fraction", correct_answer="7/3"),
    ]

check("v2.21.3 version", APP_VERSION == "2.21.3")

store = InMemoryFactStore()
klass = store.create_class("Block 1")
student = store.create_student(klass.class_id, "Otter", "1234")
quiz = store.save_weekly_quiz_set(
    klass.class_id, date(2026, 9, 25), assignment_name="Quiz of the Week",
    category_code="SUMM", max_score=5, questions=questions(),
)

# First answer is saved, then revised in the same slot. The record is replaced,
# not duplicated, which is what Back/Edit requires.
q1 = quiz.questions[0]
r1 = grade_quiz_response(q1, "4")
first = store.record_weekly_quiz_answer(
    quiz_id=quiz.quiz_id, student_id=student.student_id, class_id=klass.class_id,
    quiz_date="2026-09-25", question_slot=1, question_type="Number", prompt=q1["prompt"],
    student_response=pack_response("4"), correct=r1["correct"],
    number_correct=r1["number_correct"], label_correct=r1["label_correct"],
)
r2 = grade_quiz_response(q1, "3.0")
second = store.record_weekly_quiz_answer(
    quiz_id=quiz.quiz_id, student_id=student.student_id, class_id=klass.class_id,
    quiz_date="2026-09-25", question_slot=1, question_type="Number", prompt=q1["prompt"],
    student_response=pack_response("3.0"), correct=r2["correct"],
    number_correct=r2["number_correct"], label_correct=r2["label_correct"],
)
rows = store.get_weekly_quiz_answers(student.student_id, quiz.quiz_id)
check("edit keeps one row", len(rows) == 1)
check("edit preserves answer record id", first.quiz_answer_id == second.quiz_answer_id)
answer, label = unpack_response(rows[0].student_response)
check("revised response stored", answer == "3.0" and label == "")
check("revised grading stored", rows[0].correct is True)

student_ui = (ROOT / "student_weekly_quiz_ui.py").read_text(encoding="utf-8")
igniter_ui = (ROOT / "student_igniter_ui.py").read_text(encoding="utf-8")
supabase_store = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
check("Back control present", '"← Back"' in student_ui)
check("Save and Next control present", '"Save & Next →"' in student_ui)
check("final Submit Quiz control present", '"Submit Quiz →"' in student_ui)
check("saved responses prefill", "unpack_response(saved_row.student_response)" in student_ui)
check("explicit navigation state", "weekly_quiz_slot::" in student_ui)
check("Quiz image is compact", "st.image(image_url, width=460)" in student_ui)
check("Igniter image is compact", "st.image(image_url, width=460)" in igniter_ui)
check("Supabase answer edit uses upsert", '.upsert(' in supabase_store and 'on_conflict="student_id,quiz_id,question_slot"' in supabase_store)

print(f"v2_21_3_quiz_navigation_tests: PASS ({len(checks)}/{len(checks)})")
