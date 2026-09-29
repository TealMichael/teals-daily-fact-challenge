from __future__ import annotations

from pathlib import Path

from fact_engine import APP_VERSION
from indiana_question_bank import question_by_id, seed_editor_state

ROOT = Path(__file__).resolve().parent


def test_release_version():
    assert APP_VERSION == "2.22.2"


def test_inline_picker_is_available_in_both_builders():
    warmup = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
    quiz = (ROOT / "teacher_weekly_quiz_ui.py").read_text(encoding="utf-8")
    bank_ui = (ROOT / "teacher_question_bank_ui.py").read_text(encoding="utf-8")

    assert "render_inline_question_bank_picker" in warmup
    assert "render_inline_question_bank_picker" in quiz
    assert "def render_inline_question_bank_picker" in bank_ui
    assert 'st.expander("📚 Add from Indiana Question Bank"' in bank_ui
    assert '"Grade"' in bank_ui
    assert '"Standard"' in bank_ui
    assert '"Question"' in bank_ui
    assert '"Random"' in bank_ui
    assert '"Replace current question"' in bank_ui
    assert '"Load into this question"' in bank_ui


def test_picker_renders_before_normal_editor_widgets():
    warmup = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
    quiz = (ROOT / "teacher_weekly_quiz_ui.py").read_text(encoding="utf-8")

    warmup_picker = warmup.index("render_inline_question_bank_picker(")
    warmup_prompt = warmup.index('prompt = st.text_area(', warmup_picker)
    assert warmup_picker < warmup_prompt

    quiz_picker = quiz.index("render_inline_question_bank_picker(")
    quiz_prompt = quiz.index('prompt = st.text_area(', quiz_picker)
    assert quiz_picker < quiz_prompt


def test_loading_one_slot_does_not_overwrite_other_draft_slots():
    question = question_by_id("5.M.5-Q01")
    assert question is not None

    state = {
        "demo_prompt_2": "Keep my second draft",
        "demo_correct_2": "99",
        "demo_type_2": "Number",
    }
    seed_editor_state(
        state,
        prefix="demo",
        slot=1,
        question=question,
        include_standard=True,
    )

    assert state["demo_prompt_1"] == question["prompt"]
    assert state["demo_bank_question_id_1"] == question["id"]
    assert state["demo_standard_choice_1"] == "5.M.5"
    assert state["demo_prompt_2"] == "Keep my second draft"
    assert state["demo_correct_2"] == "99"
    assert state["demo_type_2"] == "Number"


def test_quiz_load_can_seed_without_standard_widget_state():
    question = question_by_id("6.NS.1-Q01")
    assert question is not None

    state = {}
    seed_editor_state(
        state,
        prefix="quiz",
        slot=4,
        question=question,
        include_standard=False,
    )

    assert state["quiz_prompt_4"] == question["prompt"]
    assert state["quiz_bank_question_id_4"] == question["id"]
    assert "quiz_standard_choice_4" not in state


def test_partial_deploy_guard_keeps_builders_importable():
    warmup = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
    quiz = (ROOT / "teacher_weekly_quiz_ui.py").read_text(encoding="utf-8")
    for source in (warmup, quiz):
        assert "except ImportError" in source
        assert "render_inline_question_bank_picker = None" in source
        assert "if callable(render_inline_question_bank_picker):" in source
