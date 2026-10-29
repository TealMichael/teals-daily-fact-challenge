"""Offline v2.29.0 Today redesign regression tests (anonymous students only).

Run from UPLOAD_TO_GITHUB with: python3 v2_29_0_today_redesign_tests.py
No Supabase credentials or classroom data are used.
"""

from datetime import date
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace as Row
from unittest.mock import patch

# These pure Today helpers can be exercised on a machine without Streamlit or
# Supabase. In the deployed application, all real imports and widgets are used.
if importlib.util.find_spec("streamlit") is None:
    fake_streamlit = ModuleType("streamlit")
    fake_streamlit.session_state = {}
    sys.modules["streamlit"] = fake_streamlit
    popout = ModuleType("igniter_popout")
    popout.render_igniter_window_button = lambda *_args, **_kw: None
    sys.modules["igniter_popout"] = popout
    overview = ModuleType("teacher_today_overview")
    overview.load_today_lessons = lambda *_args: []
    overview.recent_mastery_checkins = lambda *_args: []
    overview.today_reteach = lambda *_args: []
    sys.modules["teacher_today_overview"] = overview
    warmup_ui = ModuleType("teacher_warmup_ui")
    for name in ("_warmup_email_recipients", "_warmup_grouping",
                 "_warmup_instruction_recommendation", "_warmup_outlook_url",
                 "_warmup_report_text"):
        setattr(warmup_ui, name, lambda *_args, **_kw: None)
    warmup_ui._warmup_instruction_recommendation = lambda *_args: "Quick small-group check-in."
    sys.modules["teacher_warmup_ui"] = warmup_ui

import teacher_today_ui as today


DAY = date(2026, 10, 29)


def _lesson(*, kind="Igniter", answers=(), questions=None, completed=("s1", "s2", "s3")):
    questions = questions or [
        {"prompt": "408 × 23 =", "standard_code": "5.CA.1", "standard_description": "Multiply"},
        {"prompt": "672 ÷ 24 =", "standard_code": "5.CA.2", "standard_description": "Divide"},
    ]
    return Row(
        error=False, kind=kind,
        class_record=Row(class_id="c1", class_name="Block 1"),
        students=[Row(student_id="s1", nickname="Alpha"),
                  Row(student_id="s2", nickname="Beta"),
                  Row(student_id="s3", nickname="Gamma")],
        assignment=Row(question_one=questions[0], question_two=questions[1], questions=questions),
        rows=list(answers), completed_ids=set(completed), complete=len(completed), total=3,
    )


def _answer(student, slot, correct):
    return Row(student_id=student, question_slot=slot, correct=correct)


def _check(student, code, *, klass="c1", completed_at=None, correct=None):
    return Row(student_id=student, class_id=klass, standard_code=code,
               completed_at=completed_at, correct=correct, prompt="Question")


def test_subset_assignment_does_not_clear_current_priorities():
    lesson = _lesson(answers=[
        _answer("s1", 1, False), _answer("s1", 2, True),
        _answer("s2", 1, False), _answer("s2", 2, True),
        _answer("s3", 1, True), _answer("s3", 2, True),
    ])
    targets = today._today_standard_targets(lesson, {"completed_count": 3})
    assert targets == {"5.CA.1": {"s1", "s2"}}, targets
    one_check = [_check("s1", "5.CA.1")]
    partial = today._today_followup_coverage(lesson, targets, one_check)
    assert (partial["required"], partial["assigned"], partial["clear"]) == (2, 1, False)
    assert partial["remaining"] == {("s2", "5.CA.1")}
    complete = today._today_followup_coverage(
        lesson, targets, one_check + [_check("s2", "5.CA.1")])
    assert complete["clear"] is True


def test_both_missed_same_standard_counts_one_check_per_student():
    questions = [
        {"prompt": "408 × 23 =", "standard_code": "5.CA.1", "standard_description": "Multiply"},
        {"prompt": "634 × 25 =", "standard_code": "5.CA.1", "standard_description": "Multiply"},
    ]
    lesson = _lesson(questions=questions, answers=[
        _answer("s1", 1, False), _answer("s1", 2, False),
        _answer("s2", 1, True), _answer("s2", 2, True),
    ])
    targets = today._today_standard_targets(lesson, {"completed_count": 2})
    assert targets == {"5.CA.1": {"s1"}}, targets
    assert today._today_followup_coverage(
        lesson, targets, [_check("s1", "5.CA.1")])["clear"]


def test_missed_both_different_standards_needs_two_checks():
    lesson = _lesson(answers=[_answer("s1", 1, False), _answer("s1", 2, False)])
    targets = today._today_standard_targets(lesson, {"completed_count": 1})
    assert targets == {"5.CA.1": {"s1"}, "5.CA.2": {"s1"}}, targets
    partial = today._today_followup_coverage(lesson, targets, [_check("s1", "5.CA.1")])
    assert not partial["clear"] and partial["assigned"] == 1


def test_incomplete_responses_and_wrong_class_are_not_misses_or_coverage():
    lesson = _lesson(answers=[
        _answer("s1", 1, False), _answer("s2", 1, False),
        _answer("s2", 2, True),
    ], completed=("s2",))
    targets = today._today_standard_targets(lesson, {"completed_count": 1})
    assert targets == {"5.CA.1": {"s2"}}
    assert not today._today_followup_coverage(
        lesson, targets, [_check("s2", "5.CA.1", klass="c2")])["clear"]


def test_quiz_targets_group_by_missed_tagged_standard():
    lesson = _lesson(kind="Quiz", answers=[_answer("s1", 1, False)], completed=("s1",))
    with patch.object(today, "today_reteach", return_value=[
        {"code": "5.CA.1", "student_ids": ["s1"]},
        {"code": "5.CA.2", "student_ids": ["s1", "s2"]},
    ]):
        assert today._today_standard_targets(lesson, None) == {
            "5.CA.1": {"s1"}, "5.CA.2": {"s1", "s2"},
        }


def test_history_waits_for_students_or_followup_assignments():
    lesson = _lesson(completed=())
    targets = {"5.CA.1": {"s1", "s2"}}
    assert not today._history_is_next_priority(lesson, targets, None)
    lesson.complete = 2
    assert not today._history_is_next_priority(
        lesson, targets, {"clear": False})
    assert not today._history_is_next_priority(lesson, targets, None)
    assert today._history_is_next_priority(lesson, targets, {"clear": True})
    assert today._history_is_next_priority(lesson, {}, None)
    lesson.assignment = None
    assert today._history_is_next_priority(lesson, {}, None)
    lesson.error = True
    assert not today._history_is_next_priority(lesson, {}, None)


def test_bad_standard_tag_never_looks_like_an_addressed_group():
    bad_questions = [
        {"prompt": "Find the volume of a rectangular prism with sides 3, 4, and 5.",
         "standard_code": "5.CA.2", "standard_description": "Division"},
        {"prompt": "672 ÷ 24 =", "standard_code": "5.CA.2",
         "standard_description": "Division"},
    ]
    lesson = _lesson(questions=bad_questions, completed=("s1",), answers=[
        _answer("s1", 1, False), _answer("s1", 2, True),
    ])
    assert today._today_standard_targets(lesson, {"completed_count": 1}) == {}
    assert today._today_has_unmatched_misses(lesson)
    assert not today._history_is_next_priority(
        lesson, {}, None, unmatched_misses=True)
    lesson.assignment.question_one = {
        "prompt": "408 × 23 =", "standard_code": "5.CA.1",
        "standard_description": "Multiplication",
    }
    assert not today._today_has_unmatched_misses(lesson)


def test_cache_reuses_recent_reads_and_refreshes_when_asked():
    class Store:
        calls = 0

        def list_standard_quick_checks(self, *_args, **_kwargs):
            self.calls += 1
            return [_check("s1", "5.CA.1"), _check("stranger", "5.CA.1")]

    saved_session = today.st.session_state
    try:
        today.st.session_state = {}
        lesson = _lesson()
        store = Store()
        first = today._today_quick_checks(store, lesson, DAY)
        second = today._today_quick_checks(store, lesson, DAY)
        assert len(first) == len(second) == 1 and store.calls == 1
        today._today_quick_checks(store, lesson, DAY, fresh=True)
        assert store.calls == 2
    finally:
        today.st.session_state = saved_session


def test_four_compact_cards_in_a_desktop_row():
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {}
            self.widths = []
            self.labels = []

        def markdown(self, *_args, **_kwargs):
            pass

        def columns(self, n, **_kwargs):
            self.widths.append(n)
            return [nullcontext() for _ in range(n)]

        def container(self, **_kwargs):
            return nullcontext()

        def button(self, label, **_kwargs):
            self.labels.append(label)
            return False

    fake = FakeStreamlit()
    lessons = [Row(
        class_record=Row(class_id=f"c{i}", class_name=f"Block {i}"),
        error=False, assignment=Row(), kind="Igniter", complete=i, total=24,
    ) for i in range(1, 5)]
    original = today.st
    try:
        today.st = fake
        selected = today._render_class_cards(lessons, {})
        assert fake.widths == [4]
        assert len(fake.labels) == 4
        assert selected.class_record.class_id == "c1"
        assert all("Missed" not in label and "Awaiting" not in label for label in fake.labels)
    finally:
        today.st = original


def test_missed_question_buttons_retain_correct_student_ids():
    from v2_28_1_quick_check_picker_tests import FakeStore, FakeStreamlit

    class RenderStreamlit(FakeStreamlit):
        def expander(self, *_args, **_kwargs):
            return nullcontext()

        def container(self, **_kwargs):
            return nullcontext()

    lesson = _lesson(answers=[
        _answer("s1", 1, False), _answer("s1", 2, True),
        _answer("s2", 1, False), _answer("s2", 2, True),
        _answer("s3", 1, True), _answer("s3", 2, True),
    ])
    grouping = {
        "missed_both": [], "q1_support": ["Alpha", "Beta"], "q2_support": [],
        "q1_only": ["Alpha", "Beta"], "q2_only": [], "completed_count": 3,
        "unfinished": [],
    }
    fake = RenderStreamlit(session={})
    store = FakeStore()
    original = today.st
    try:
        today.st = fake
        today._render_igniter_priorities(store, lesson, grouping, DAY)
        assert len(store.assignments) == 1
        assert store.assignments[0]["standard_code"] == "5.CA.1"
        assert store.assignments[0]["student_ids"] == ["s1", "s2"]
    finally:
        today.st = original


def test_history_is_lazily_read_only_when_visible():
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {}
            self.clicked = False
            self.labels = []

        def container(self, **_kwargs):
            from contextlib import nullcontext
            return nullcontext()

        def button(self, label, **_kwargs):
            self.labels.append(label)
            clicked, self.clicked = self.clicked, False
            return clicked

        def markdown(self, *_args, **_kwargs):
            pass

        def caption(self, *_args, **_kwargs):
            pass

    fake = FakeStreamlit()
    prior_streamlit = today.st
    try:
        today.st = fake
        with patch.object(today, "_render_historical_rows") as history:
            today._render_historical_checkins(None, _lesson(), DAY, ready=False)
            history.assert_not_called()
            assert fake.labels[-1] == "Review previous missed standards (optional)"
            fake.clicked = True
            today._render_historical_checkins(None, _lesson(), DAY, ready=False)
            history.assert_called_once()
            today._render_historical_checkins(None, _lesson(), DAY, ready=False)
            assert fake.labels[-1] == "Hide previous missed standards"
            assert history.call_count == 2
            fake.clicked = True
            today._render_historical_checkins(None, _lesson(), DAY, ready=False)
            assert history.call_count == 2  # Closed: no historical fetch.
            assert fake.labels[-1] == "Hide previous missed standards"
            # The first completed follow-up cycle opens history automatically.
            today._render_historical_checkins(None, _lesson(), DAY, ready=True)
            assert history.call_count == 3
            fake.clicked = True
            today._render_historical_checkins(None, _lesson(), DAY, ready=True)
            assert history.call_count == 3  # Can hide after automatic open.
            today._render_historical_checkins(None, _lesson(), DAY, ready=True)
            assert history.call_count == 3  # Does not reopen on every rerun.
    finally:
        today.st = prior_streamlit


def test_small_card_labels_and_version():
    lesson = _lesson()
    lesson.completed_ids = {"s1"}
    lesson.complete = 1
    label = today._card_label(lesson, {"completed_count": 1})
    assert "1/3 Igniter complete" in label
    assert "Awaiting" not in label and "Missed Q1" not in label
    src = Path(__file__).parent
    assert 'APP_VERSION = "2.29.2"' in (src / "fact_engine.py").read_text()


if __name__ == "__main__":
    test_subset_assignment_does_not_clear_current_priorities()
    test_both_missed_same_standard_counts_one_check_per_student()
    test_missed_both_different_standards_needs_two_checks()
    test_incomplete_responses_and_wrong_class_are_not_misses_or_coverage()
    test_quiz_targets_group_by_missed_tagged_standard()
    test_history_waits_for_students_or_followup_assignments()
    test_bad_standard_tag_never_looks_like_an_addressed_group()
    test_cache_reuses_recent_reads_and_refreshes_when_asked()
    test_four_compact_cards_in_a_desktop_row()
    test_missed_question_buttons_retain_correct_student_ids()
    test_history_is_lazily_read_only_when_visible()
    test_small_card_labels_and_version()
    print("v2.29.1 Today redesign + history toggle: 12 offline tests passed")
