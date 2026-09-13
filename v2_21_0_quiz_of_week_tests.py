from __future__ import annotations

from datetime import date
from pathlib import Path
import hashlib

from fact_store import InMemoryFactStore, FactStoreError
from weekly_quiz import (
    grade_quiz_response,
    numeric_value,
    prepare_quiz_question,
    skyward_score,
    student_export_key,
    validate_quiz_questions,
)

ROOT = Path(__file__).resolve().parent


def questions():
    return [
        prepare_quiz_question(slot=1, prompt="Enter 3 as a number.", question_type="Number", correct_answer="3"),
        prepare_quiz_question(slot=2, prompt="Enter three fourths.", question_type="Fraction", correct_answer="3/4"),
        prepare_quiz_question(slot=3, prompt="Choose the product.", question_type="Multiple choice", correct_answer="12", options=["8", "10", "12", "14"]),
        prepare_quiz_question(slot=4, prompt="A square has area 16 ___.", question_type="Number + Label", correct_answer="16", label_options=["feet", "square feet"], correct_label="square feet"),
        prepare_quiz_question(slot=5, prompt="Enter 2 1/3.", question_type="Fraction", correct_answer="2 1/3"),
    ]


def run():
    assert numeric_value("3") == numeric_value("3.0") == numeric_value("3.00")
    assert numeric_value("3/4") == numeric_value("6/8") == numeric_value("0.75")
    assert numeric_value("2 1/3") == numeric_value("7/3")
    assert numeric_value("-2 1/3") == numeric_value("-7/3")

    q_num, q_frac, _, q_label, q_mixed = questions()
    assert grade_quiz_response(q_num, "3.0")["correct"]
    assert grade_quiz_response(q_frac, "6/8")["correct"]
    assert grade_quiz_response(q_mixed, "7/3")["correct"]
    assert grade_quiz_response(q_label, "16", "square feet")["correct"]
    assert not grade_quiz_response(q_label, "16", "feet")["correct"]
    assert grade_quiz_response(q_label, "16", "feet")["number_correct"]
    assert not grade_quiz_response(q_label, "16", "feet")["label_correct"]
    assert len(validate_quiz_questions(questions())) == 5
    try:
        validate_quiz_questions(questions()[:4])
        raise AssertionError("4-question quiz should fail")
    except ValueError:
        pass

    assert skyward_score(5, 5) == 5
    assert skyward_score(4, 10) == 8
    assert skyward_score(3, 7) == 4.2
    key = student_export_key("00000000-0000-4000-8000-000000000001")
    assert key.startswith("QW-") and len(key) == 15
    assert "00000000" not in key

    store = InMemoryFactStore()
    klass = store.create_class("Block 1")
    student = store.create_student(klass.class_id, "Otter", "1234")
    quiz = store.save_weekly_quiz_set(
        klass.class_id, date(2026, 9, 18), assignment_name="Quiz of the Week - Sep 18",
        category_code="SUMM", max_score=5, questions=questions(),
    )
    assert quiz.category_code == "SUMM" and len(quiz.questions) == 5
    result = grade_quiz_response(quiz.questions[0], "3.0")
    store.record_weekly_quiz_answer(
        quiz_id=quiz.quiz_id, student_id=student.student_id, class_id=klass.class_id,
        quiz_date="2026-09-18", question_slot=1, question_type="Number", prompt="Enter 3 as a number.",
        student_response='{"answer":"3.0","label":""}', correct=result["correct"],
        number_correct=result["number_correct"], label_correct=result["label_correct"],
    )
    assert store.weekly_quiz_locked(quiz.quiz_id)
    try:
        store.save_weekly_quiz_set(
            klass.class_id, "2026-09-18", assignment_name="Changed", category_code="SUMM",
            max_score=5, questions=questions(),
        )
        raise AssertionError("real-student-started quiz should lock")
    except FactStoreError:
        pass

    # Test Student can trial a quiz without locking it.
    klass2 = store.create_class("Block 2")
    test_student = store.reset_test_student(klass2.class_id)
    quiz2 = store.save_weekly_quiz_set(
        klass2.class_id, "2026-09-18", assignment_name="Quiz", category_code="FORM", max_score=5,
        questions=questions(),
    )
    result2 = grade_quiz_response(quiz2.questions[0], "3")
    store.record_weekly_quiz_answer(
        quiz_id=quiz2.quiz_id, student_id=test_student.student_id, class_id=klass2.class_id,
        quiz_date="2026-09-18", question_slot=1, question_type="Number", prompt="Enter 3 as a number.",
        student_response='{"answer":"3","label":""}', correct=result2["correct"],
        number_correct=result2["number_correct"], label_correct=result2["label_correct"],
    )
    assert not store.weekly_quiz_locked(quiz2.quiz_id)

    # Friday routing: quiz check occurs before the legacy Igniter, and a completed quiz skips Igniter.
    app = (ROOT / "app.py").read_text()
    quiz_pos = app.index("weekly_quiz_state = render_friday_quiz(store, day)")
    warmup_pos = app.index("weekly_quiz_state != \"complete\" and not render_quick_warmup(store, day)")
    assert quiz_pos < warmup_pos

    # Privacy boundary: new database tables add no roster-name or Skyward-ID columns.
    sql = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_21.sql").read_text().lower()
    body = sql[sql.index("create table if not exists public.weekly_quiz_sets"):]
    for forbidden_column in ("first_name text", "last_name text", "skyward_student", "email text"):
        assert forbidden_column not in body
    assert "enable row level security" in body
    assert "create policy" not in body

    # Protected v2.20.3 behavior files remain byte-for-byte unchanged.
    expected_hashes = {
        "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
        "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
        "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
        "daily_alt_component/index.html": "332ee7265c450b00d4848a059f000439dba2089c4ec765bf18f41e2bed734c4d",
        "alt_fix_component/index.html": "6a60d52ce0775250b54477c2cafb909f3cf5e4cb6fe53d51795ca30aacda64d4",
        "alt_focus_component/index.html": "3fbc588093066e786dd4e579f9a4f0659d5480c5108f632a63f109ffd3460a86",
        "student_alt_daily_ui.py": "8ee99c33158a7de165bde0dcfcd59fcf4b1bce4395e1031ebe1ed8153b087afe",
        "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
        "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
        "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
        "persistent_login.py": "bace7a3ae337c5cb651afe16face0262ebae482d56e1b435de1e997293a289f2",
    }
    for relative, expected in expected_hashes.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected, relative

    print("v2_21_0_quiz_of_week_tests: PASS")


if __name__ == "__main__":
    run()
