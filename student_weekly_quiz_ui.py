from __future__ import annotations

"""Student-facing Friday Quiz of the Week.

The quiz is intentionally isolated from Igniter and Daily 10 code. It writes
only anonymous app student IDs + responses; no roster names or Skyward fields.
"""

from datetime import date
import html
import re

import streamlit as st

from supabase_fact_store import SupabaseFactStore
from question_images import signed_question_image_url
from indiana_question_bank import resolve_bank_image_path
from curriculum_question_types import (
    COMPARE_QUESTION_TYPE,
    COMPARISON_SYMBOLS,
    ORDER_QUESTION_TYPE,
    deterministic_start_order,
    pack_order_response,
    unpack_order_response,
)
from interactive_math_questions import render_order_tiles
from student_curriculum_support import render_curriculum_retry
from quiz_review import (
    display_review_response, missing_response_slots, pending_review_saves,
    response_complete, review_responses,
)
from weekly_quiz import (
    QUIZ_QUESTION_COUNT,
    grade_quiz_response,
    pack_response,
    unpack_response,
    question_for_slot,
    quiz_is_friday,
)


def _save_answer(store, quiz, student_id, class_id, day, slot, answer, label):
    question = question_for_slot(quiz, slot)
    result = grade_quiz_response(question, answer, label)
    return store.record_weekly_quiz_answer(
        quiz_id=quiz.quiz_id, student_id=student_id, class_id=class_id,
        quiz_date=day, question_slot=slot,
        question_type=str(question.get("question_type") or "Number"),
        prompt=str(question.get("prompt") or ""),
        student_response=pack_response(answer, label),
        correct=result["correct"], number_correct=result["number_correct"],
        label_correct=result["label_correct"],
    )


def _render_review(store, quiz, student_id, class_id, day, answers_by_slot,
                   drafts, slot_state_key, review_key, just_completed_key):
    responses = review_responses(answers_by_slot, drafts)
    missing = missing_response_slots(quiz, responses)
    st.markdown("## 📝 Review your quiz")
    st.caption("Check all five answers. You can change any answer before you submit.")
    st.info("Your quiz is not submitted yet. Keep this tab open until you see the confirmation.")
    for slot in range(1, QUIZ_QUESTION_COUNT + 1):
        question = question_for_slot(quiz, slot)
        with st.container(border=True):
            st.markdown(f"**Question {slot}**")
            st.text(str(question.get("prompt") or ""))
            if question.get("question_type") == COMPARE_QUESTION_TYPE:
                st.text(f"{question.get('compare_left', '')}   ?   {question.get('compare_right', '')}")
            elif question.get("question_type") == ORDER_QUESTION_TYPE:
                st.caption(str(question.get("order_direction") or ""))
            st.text("Your answer: " + display_review_response(question, *responses.get(slot, ("", ""))))
            if st.button(f"Edit Question {slot}", key=f"quiz_edit::{student_id}::{quiz.quiz_id}::{slot}"):
                st.session_state[slot_state_key] = slot
                st.session_state[review_key] = False
                st.session_state[f"{review_key}::editing"] = True
                st.rerun()
    if missing:
        st.warning("Finish these questions before submitting: " + ", ".join(map(str, missing)))
    if st.button("Submit Quiz →", type="primary", use_container_width=True,
                 disabled=bool(missing), key=f"quiz_final_submit::{student_id}::{quiz.quiz_id}"):
        try:
            # Question 5 is withheld until this explicit action. Save changed
            # earlier answers first so a failed write cannot export a partial
            # review as a completed quiz. Upserts make a retry duplicate-safe.
            for slot in pending_review_saves(quiz, responses, answers_by_slot):
                _save_answer(store, quiz, student_id, class_id, day, slot, *responses[slot])
        except Exception as exc:
            st.error("Your quiz has not finished saving. Keep this tab open and tap Submit Quiz again. Your answers are still here.")
            st.session_state["tdfc_force_fresh_store_once"] = True
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
            return "blocked"
        st.session_state[just_completed_key] = True
        st.session_state[review_key] = False
        st.rerun()
    return "blocked"


def render_friday_quiz(store: SupabaseFactStore, day: date) -> str:
    """Render Friday quiz when assigned.

    Returns one of:
      * not_applicable — Monday–Thursday
      * not_assigned — Friday with no quiz for this class (Igniter fallback)
      * complete — quiz already completed; caller should skip Igniter
      * blocked — quiz UI is currently on screen; caller should stop routing
    """
    if not quiz_is_friday(day):
        return "not_applicable"

    class_id = str(st.session_state.get("student_class_id") or "")
    student_id = str(st.session_state.get("student_id") or "")
    if not class_id or not student_id:
        return "not_assigned"

    try:
        quiz = store.get_weekly_quiz_set(class_id, day)
    except Exception as exc:
        render_curriculum_retry("Today's Quiz of the Week could not be loaded.", exc, key="retry_quiz_set")
        return "blocked"
    if quiz is None:
        return "not_assigned"

    complete_cache_key = f"weekly_quiz_complete::{student_id}::{quiz.quiz_id}"
    if st.session_state.get(complete_cache_key, False):
        return "complete"

    try:
        answers = store.get_weekly_quiz_answers(student_id, quiz.quiz_id)
    except Exception as exc:
        render_curriculum_retry("Your Quiz of the Week progress could not be loaded.", exc, key="retry_quiz_progress")
        return "blocked"

    answers_by_slot = {int(row.question_slot): row for row in answers}
    answered_slots = set(answers_by_slot)
    completed = set(range(1, QUIZ_QUESTION_COUNT + 1)).issubset(answered_slots)
    just_completed_key = f"weekly_quiz_just_completed::{student_id}::{quiz.quiz_id}"
    slot_state_key = f"weekly_quiz_slot::{student_id}::{quiz.quiz_id}"
    # Non-widget state survives Streamlit's cleanup when a question is hidden.
    # The quiz revision also isolates a teacher's reset/rebuilt Test Student quiz.
    draft_key = f"weekly_quiz_drafts::{student_id}::{quiz.quiz_id}::{quiz.updated_at}"
    review_key = f"{draft_key}::review"
    drafts = st.session_state.setdefault(draft_key, {})

    if completed:
        st.session_state.pop(draft_key, None)
        st.session_state.pop(review_key, None)
        st.session_state.pop(f"{review_key}::editing", None)
        if st.session_state.get(just_completed_key):
            st.markdown("## 📝 Quiz of the Week complete!")
            st.success("Your quiz has been submitted. Your teacher will see your results.")
            st.caption("Next up: your regular Daily 10. Your final Weekly Mystery guess comes after your normal Friday learning routine.")
            if st.button(
                "Start Daily 10 →", type="primary", use_container_width=True,
                key=f"weekly_quiz_start_daily_{quiz.quiz_id}_{student_id}",
            ):
                st.session_state[just_completed_key] = False
                st.session_state[complete_cache_key] = True
                st.session_state.pop(slot_state_key, None)
                st.rerun()
            return "blocked"
        st.session_state[complete_cache_key] = True
        st.session_state.pop(slot_state_key, None)
        return "complete"

    if st.session_state.get(review_key):
        return _render_review(
            store, quiz, student_id, class_id, day, answers_by_slot, drafts,
            slot_state_key, review_key, just_completed_key,
        )

    # Start on the first unanswered item. During this browser session the
    # explicit slot state allows students to move backward and revise saved
    # answers before the fifth question is finally submitted.
    first_unanswered = next(
        (index for index in range(1, QUIZ_QUESTION_COUNT + 1) if index not in answered_slots),
        QUIZ_QUESTION_COUNT,
    )
    slot = int(st.session_state.get(slot_state_key) or first_unanswered)
    if not 1 <= slot <= QUIZ_QUESTION_COUNT:
        slot = first_unanswered
    st.session_state[slot_state_key] = slot

    question = question_for_slot(quiz, slot)
    qtype = str(question.get("question_type") or "Number")
    saved_row = answers_by_slot.get(slot)
    saved_answer, saved_label = unpack_response(saved_row.student_response) if saved_row else ("", "")
    if slot in drafts:
        saved_answer, saved_label = unpack_response(drafts[slot])

    st.markdown("## 📝 Quiz of the Week")
    st.caption(f"Question {slot} of {QUIZ_QUESTION_COUNT} · Take your time and show your work on paper when needed.")
    st.progress((slot - 1) / QUIZ_QUESTION_COUNT)

    raw_prompt = str(question.get("prompt") or "").strip()
    clean_prompt = re.sub(r"(?:\*\*|__|`)", "", raw_prompt).strip()
    prompt_html = html.escape(clean_prompt).replace("\n", "<br>")
    st.markdown(
        f"<div style='font-size:1.35rem;font-weight:750;line-height:1.45;margin:0.45rem 0 1rem 0;'>{prompt_html}</div>",
        unsafe_allow_html=True,
    )
    image_path = str(question.get("image_path") or "")
    image_shown = False
    if image_path:
        image_url = signed_question_image_url(store, image_path)
        if image_url:
            st.image(image_url, width=460)
            image_shown = True
    if not image_shown:
        bank_image = resolve_bank_image_path(question.get("bank_image_path") or "")
        if bank_image:
            st.image(bank_image, width=460)
            image_shown = True
    if image_path and not image_shown:
        st.caption("The question image is no longer available. Show your teacher before answering.")

    form_key = f"weekly_quiz_answer_{quiz.quiz_id}_{student_id}_{slot}"
    response = ""
    label = ""
    order_response = ""
    if qtype == ORDER_QUESTION_TYPE:
        order_items = [str(item) for item in (question.get("order_items") or [])]
        direction = str(question.get("order_direction") or "Least to greatest")
        saved_order = unpack_order_response(saved_answer)
        try:
            initial_order = saved_order or deterministic_start_order(
                order_items,
                seed=f"{student_id}:{quiz.quiz_id}:{slot}",
                direction=direction,
            )
        except ValueError:
            initial_order = saved_order or order_items
        st.caption(f"Drag the tiles from {direction.lower()}.")
        current_order = render_order_tiles(
            order_items,
            initial_order=initial_order,
            key=f"quiz_order_tiles::{quiz.quiz_id}::{student_id}::{slot}",
            instruction=f"Order from {direction.lower()}.",
        )
        order_response = pack_order_response(current_order)

    # Enter would otherwise activate the FIRST submit control (Back on Q2–5).
    with st.form(form_key, clear_on_submit=False, enter_to_submit=False):
        if qtype == "Multiple choice":
            options = [str(item) for item in (question.get("options") or [])]
            choice_key = f"quiz_choice_{quiz.quiz_id}_{student_id}_{slot}"
            if choice_key not in st.session_state and saved_answer in options:
                st.session_state[choice_key] = saved_answer
            response = st.radio("Choose your answer", options, index=None, key=choice_key) if options else ""
        elif qtype == COMPARE_QUESTION_TYPE:
            compare_left = str(question.get("compare_left") or "")
            compare_right = str(question.get("compare_right") or "")
            compare_key = f"quiz_compare_{quiz.quiz_id}_{student_id}_{slot}"
            if compare_key not in st.session_state and saved_answer in COMPARISON_SYMBOLS:
                st.session_state[compare_key] = saved_answer
            st.markdown(
                f"<div style='text-align:center;font-size:1.55rem;font-weight:750;margin:0.2rem 0 0.45rem 0;'>"
                f"{html.escape(compare_left)} &nbsp;&nbsp; ? &nbsp;&nbsp; {html.escape(compare_right)}</div>",
                unsafe_allow_html=True,
            )
            response = st.radio(
                "Choose the symbol", list(COMPARISON_SYMBOLS), index=None, horizontal=True, key=compare_key,
            )
        elif qtype == ORDER_QUESTION_TYPE:
            response = order_response
            st.caption("When the tiles are in the order you want, save and continue.")
        elif qtype == "Number + Label":
            left, right = st.columns([1.15, 1])
            number_key = f"quiz_number_{quiz.quiz_id}_{student_id}_{slot}"
            label_key = f"quiz_label_{quiz.quiz_id}_{student_id}_{slot}"
            if number_key not in st.session_state:
                st.session_state[number_key] = saved_answer
            with left:
                response = st.text_input(
                    "Number", key=number_key, placeholder="Type the number",
                )
            with right:
                labels = [str(item) for item in (question.get("label_options") or [])]
                if label_key not in st.session_state and saved_label in labels:
                    st.session_state[label_key] = saved_label
                label = st.selectbox(
                    "Label / unit", labels, index=None, placeholder="Choose a label",
                    key=label_key,
                ) if labels else ""
        else:
            placeholder = "Example: 3/4 or 2 1/3" if qtype == "Fraction" else "Type your answer"
            text_key = f"quiz_text_{quiz.quiz_id}_{student_id}_{slot}"
            if text_key not in st.session_state:
                st.session_state[text_key] = saved_answer
            response = st.text_input("Your answer", key=text_key, placeholder=placeholder)
            if qtype in {"Number", "Fraction"}:
                st.caption("Equivalent numerical values count the same when mathematically equal (for example, 3 and 3.0).")

        if slot > 1:
            back_col, next_col = st.columns([0.85, 1.4])
            with back_col:
                went_back = st.form_submit_button("← Back", use_container_width=True)
            with next_col:
                next_label = "Review answers →" if slot == QUIZ_QUESTION_COUNT or st.session_state.get(f"{review_key}::editing") else "Save & Next →"
                submitted = st.form_submit_button(next_label, type="primary", use_container_width=True)
        else:
            went_back = False
            next_label = "Review answers →" if slot == QUIZ_QUESTION_COUNT or st.session_state.get(f"{review_key}::editing") else "Save & Next →"
            submitted = st.form_submit_button(next_label, type="primary", use_container_width=True)

    if went_back or submitted:
        response = str(response or "").strip()
        label = str(label or "").strip()
        drafts[slot] = pack_response(response, label)
        st.session_state[draft_key] = drafts

    if went_back:
        st.session_state[slot_state_key] = max(1, slot - 1)
        st.rerun()

    if submitted:
        response = str(response or "").strip()
        label = str(label or "").strip()
        if not response:
            st.warning("Enter an answer first.")
            return "blocked"
        if qtype == "Number + Label" and not label:
            st.warning("Choose the label or unit before submitting.")
            return "blocked"
        if not response_complete(question, response, label):
            st.warning("Choose a complete answer before continuing.")
            return "blocked"
        if slot == QUIZ_QUESTION_COUNT:
            st.session_state[review_key] = True
            st.session_state.pop(f"{review_key}::editing", None)
            st.rerun()
        try:
            _save_answer(store, quiz, student_id, class_id, day, slot, response, label)
        except Exception as exc:
            st.error("That answer did not save. Tap the save button again; your earlier quiz answers are still saved.")
            st.session_state["tdfc_force_fresh_store_once"] = True
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
            return "blocked"
        if st.session_state.pop(f"{review_key}::editing", False):
            st.session_state[review_key] = True
        else:
            st.session_state[slot_state_key] = min(QUIZ_QUESTION_COUNT, slot + 1)
        st.rerun()

    return "blocked"
