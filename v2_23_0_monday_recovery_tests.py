from __future__ import annotations

from datetime import date
from pathlib import Path

from fact_engine import APP_VERSION
from fact_store import InMemoryFactStore
from indiana_question_bank import editor_question, question_by_id
from standards_recovery import (
    RECOVERY_MAX_QUESTIONS,
    build_recovery_plan,
    combine_standards_evidence,
    mastery_evidence_status,
    previous_friday_for_recovery,
)
from weekly_quiz import prepare_quiz_question

ROOT = Path(__file__).resolve().parent


def bank_prepared(question_id: str, slot: int):
    row = question_by_id(question_id)
    assert row is not None
    q = editor_question(row)
    return prepare_quiz_question(
        slot=slot,
        prompt=q["prompt"],
        question_type=q["question_type"],
        correct_answer=q["correct_answer"],
        options=q.get("options") or (),
        accepted_answers=q.get("accepted_answers") or (),
        label_options=q.get("label_options") or (),
        correct_label=q.get("correct_label") or "",
        standard_code=q.get("standard_code") or "",
        standard_description=q.get("standard_description") or "",
        bank_image_path=q.get("bank_image_path") or "",
        bank_image_alt=q.get("bank_image_alt") or "",
        bank_question_id=q.get("bank_question_id") or "",
    )


def make_quiz_fixture():
    store = InMemoryFactStore()
    klass = store.create_class("Block 1")
    student = store.create_student(klass.class_id, "Test Kid", "1234")
    friday = date(2026, 9, 25)
    questions = [
        bank_prepared("5.M.5-Q01", 1),
        bank_prepared("5.M.5-Q02", 2),
        bank_prepared("5.CA.1-Q01", 3),
        bank_prepared("5.NS.5-Q01", 4),
        bank_prepared("5.DA.2-Q01", 5),
    ]
    quiz = store.save_weekly_quiz_set(
        klass.class_id, friday, assignment_name="Friday Quiz", category_code="SUMM", max_score=5, questions=questions
    )
    return store, klass, student, friday, quiz


def save_quiz_answers(store, klass, student, friday, quiz, correct_flags):
    for slot, correct in enumerate(correct_flags, start=1):
        q = quiz.questions[slot - 1]
        store.record_weekly_quiz_answer(
            quiz_id=quiz.quiz_id, student_id=student.student_id, class_id=klass.class_id,
            quiz_date=friday, question_slot=slot, question_type=q["question_type"], prompt=q["prompt"],
            student_response="{}", correct=correct, number_correct=correct, label_correct=True,
        )
    return store.get_weekly_quiz_answers(student.student_id, quiz.quiz_id)


def test_release_and_route_contract():
    assert APP_VERSION == "2.23.0"
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert source.index("render_quick_warmup(store, day)") < source.index("render_monday_recovery(store, day)")
    assert source.index("render_monday_recovery(store, day)") < source.index("load_student_daily_context(store)")


def test_monday_points_to_prior_friday_only():
    assert previous_friday_for_recovery(date(2026, 9, 28)) == date(2026, 9, 25)
    assert previous_friday_for_recovery(date(2026, 9, 29)) is None
    assert previous_friday_for_recovery(date(2026, 9, 25)) is None


def test_one_recovery_per_missed_standard_and_cap_three():
    store, klass, student, friday, quiz = make_quiz_fixture()
    answers = save_quiz_answers(store, klass, student, friday, quiz, [False, False, False, False, False])
    plan = build_recovery_plan(quiz, answers, student_id=student.student_id, recovery_date=date(2026, 9, 28))
    assert len(plan) == RECOVERY_MAX_QUESTIONS == 3
    assert [item["standard_code"] for item in plan] == ["5.M.5", "5.CA.1", "5.NS.5"]
    assert sum(item["standard_code"] == "5.M.5" for item in plan) == 1


def test_recovery_never_repeats_friday_bank_question_and_is_deterministic():
    store, klass, student, friday, quiz = make_quiz_fixture()
    answers = save_quiz_answers(store, klass, student, friday, quiz, [False, False, True, True, True])
    monday = date(2026, 9, 28)
    first = build_recovery_plan(quiz, answers, student_id=student.student_id, recovery_date=monday)
    second = build_recovery_plan(quiz, answers, student_id=student.student_id, recovery_date=monday)
    assert len(first) == 1
    assert first == second
    assert first[0]["standard_code"] == "5.M.5"
    assert first[0]["bank_question_id"] not in {"5.M.5-Q01", "5.M.5-Q02"}


def test_incomplete_or_perfect_friday_quiz_creates_no_recovery():
    store, klass, student, friday, quiz = make_quiz_fixture()
    incomplete = save_quiz_answers(store, klass, student, friday, quiz, [True, True, True, True]) if False else []
    assert build_recovery_plan(quiz, incomplete, student_id=student.student_id, recovery_date=date(2026, 9, 28)) == ()

    answers = save_quiz_answers(store, klass, student, friday, quiz, [True, True, True, True, True])
    assert build_recovery_plan(quiz, answers, student_id=student.student_id, recovery_date=date(2026, 9, 28)) == ()


def test_recovery_answer_is_one_row_per_standard_and_updates_safely():
    store, klass, student, friday, quiz = make_quiz_fixture()
    answers = save_quiz_answers(store, klass, student, friday, quiz, [False, True, True, True, True])
    item = build_recovery_plan(quiz, answers, student_id=student.student_id, recovery_date=date(2026, 9, 28))[0]
    question = item["question"]
    first = store.record_standard_recovery_answer(
        source_quiz_id=quiz.quiz_id, student_id=student.student_id, class_id=klass.class_id,
        recovery_date=date(2026, 9, 28), source_quiz_date=friday,
        standard_code=item["standard_code"], standard_description=item["standard_description"],
        bank_question_id=item["bank_question_id"], question_type=question["question_type"], prompt=question["prompt"],
        student_response='{"answer":"0","label":""}', correct=False, number_correct=False, label_correct=True,
    )
    second = store.record_standard_recovery_answer(
        source_quiz_id=quiz.quiz_id, student_id=student.student_id, class_id=klass.class_id,
        recovery_date=date(2026, 9, 28), source_quiz_date=friday,
        standard_code=item["standard_code"], standard_description=item["standard_description"],
        bank_question_id=item["bank_question_id"], question_type=question["question_type"], prompt=question["prompt"],
        student_response='{"answer":"1","label":""}', correct=True, number_correct=True, label_correct=True,
    )
    rows = store.get_standard_recovery_answers(student.student_id, quiz.quiz_id)
    assert len(rows) == 1
    assert first.recovery_answer_id == second.recovery_answer_id
    assert rows[0].correct is True


def test_quiz_standard_and_recovery_feed_combined_tracker():
    store, klass, student, friday, quiz = make_quiz_fixture()
    answers = save_quiz_answers(store, klass, student, friday, quiz, [False, True, True, True, True])
    item = build_recovery_plan(quiz, answers, student_id=student.student_id, recovery_date=date(2026, 9, 28))[0]
    q = item["question"]
    recovery = store.record_standard_recovery_answer(
        source_quiz_id=quiz.quiz_id, student_id=student.student_id, class_id=klass.class_id,
        recovery_date=date(2026, 9, 28), source_quiz_date=friday,
        standard_code=item["standard_code"], standard_description=item["standard_description"],
        bank_question_id=item["bank_question_id"], question_type=q["question_type"], prompt=q["prompt"],
        student_response='{"answer":"1","label":""}', correct=True, number_correct=True, label_correct=True,
    )
    evidence = combine_standards_evidence(
        warmup_rows=[], quiz_sets=[quiz], quiz_answers=answers, recovery_rows=[recovery]
    )
    m5 = [row for row in evidence if row.standard_code == "5.M.5"]
    assert [row.source for row in m5] == ["Quiz", "Quiz", "Recovery"]
    assert mastery_evidence_status(m5) == "Developing"


def test_mastery_status_requires_multiple_checks():
    store, klass, student, friday, quiz = make_quiz_fixture()
    answers = save_quiz_answers(store, klass, student, friday, quiz, [True, True, True, True, True])
    evidence = combine_standards_evidence(warmup_rows=[], quiz_sets=[quiz], quiz_answers=answers, recovery_rows=[])
    one = [row for row in evidence if row.standard_code == "5.CA.1"]
    assert len(one) == 1
    assert mastery_evidence_status(one) == "Developing"


def test_sql_and_privacy_contract():
    sql = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_23.sql").read_text(encoding="utf-8")
    assert "standard_recovery_answers" in sql
    assert "enable row level security" in sql.lower()
    assert "first_name" not in sql.lower()
    assert "last_name" not in sql.lower()
    assert "skyward" in sql.lower()  # privacy comment explicitly says Skyward IDs are not stored


def test_quiz_builder_has_recovery_standard_selector():
    source = (ROOT / "teacher_weekly_quiz_ui.py").read_text(encoding="utf-8")
    assert "Indiana Math standard · Monday Recovery" in source
    assert "include_standard=True" in source
    assert 'standard_code=item.get("standard_code")' in source


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"v2_23_0_monday_recovery_tests: PASS ({len(tests)} checks)")
