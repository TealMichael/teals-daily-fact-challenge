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
from weekly_quiz import (
    QUIZ_QUESTION_COUNT,
    grade_quiz_response,
    pack_response,
    question_for_slot,
    quiz_is_friday,
)


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
        st.error("Today's Quiz of the Week could not be loaded. Show your teacher this screen.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return "blocked"
    if quiz is None:
        return "not_assigned"

    complete_cache_key = f"weekly_quiz_complete::{student_id}::{quiz.quiz_id}"
    if st.session_state.get(complete_cache_key, False):
        return "complete"

    try:
        answers = store.get_weekly_quiz_answers(student_id, quiz.quiz_id)
    except Exception as exc:
        st.error("Your Quiz of the Week progress could not be loaded. Show your teacher this screen.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return "blocked"

    answered_slots = {int(row.question_slot) for row in answers}
    completed = len(answered_slots) >= QUIZ_QUESTION_COUNT
    just_completed_key = f"weekly_quiz_just_completed::{quiz.quiz_id}"

    if completed:
        if st.session_state.get(just_completed_key):
            st.markdown("## 📝 Quiz of the Week complete!")
            st.success("Your quiz has been submitted. Your teacher will see your results.")
            st.caption("Next up: your regular Daily 10. Your final Weekly Mystery guess comes after your normal Friday learning routine.")
            if st.button(
                "Start Daily 10 →", type="primary", use_container_width=True,
                key=f"weekly_quiz_start_daily_{quiz.quiz_id}",
            ):
                st.session_state[just_completed_key] = False
                st.session_state[complete_cache_key] = True
                st.rerun()
            return "blocked"
        st.session_state[complete_cache_key] = True
        return "complete"

    slot = next(index for index in range(1, QUIZ_QUESTION_COUNT + 1) if index not in answered_slots)
    question = question_for_slot(quiz, slot)
    qtype = str(question.get("question_type") or "Number")

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

    form_key = f"weekly_quiz_answer_{quiz.quiz_id}_{student_id}_{slot}"
    response = ""
    label = ""
    with st.form(form_key, clear_on_submit=False):
        if qtype == "Multiple choice":
            options = [str(item) for item in (question.get("options") or [])]
            response = st.radio("Choose your answer", options, index=None, key=f"quiz_choice_{quiz.quiz_id}_{slot}") if options else ""
        elif qtype == "Number + Label":
            left, right = st.columns([1.15, 1])
            with left:
                response = st.text_input(
                    "Number", key=f"quiz_number_{quiz.quiz_id}_{slot}", placeholder="Type the number",
                )
            with right:
                labels = [str(item) for item in (question.get("label_options") or [])]
                label = st.selectbox(
                    "Label / unit", labels, index=None, placeholder="Choose a label",
                    key=f"quiz_label_{quiz.quiz_id}_{slot}",
                ) if labels else ""
        else:
            placeholder = "Example: 3/4 or 2 1/3" if qtype == "Fraction" else "Type your answer"
            response = st.text_input("Your answer", key=f"quiz_text_{quiz.quiz_id}_{slot}", placeholder=placeholder)
            if qtype in {"Number", "Fraction"}:
                st.caption("Equivalent numerical values count the same when mathematically equal (for example, 3 and 3.0).")
        submitted = st.form_submit_button("Submit answer →", type="primary", use_container_width=True)

    if submitted:
        response = str(response or "").strip()
        label = str(label or "").strip()
        if not response:
            st.warning("Enter an answer first.")
            return "blocked"
        if qtype == "Number + Label" and not label:
            st.warning("Choose the label or unit before submitting.")
            return "blocked"
        result = grade_quiz_response(question, response, label)
        try:
            store.record_weekly_quiz_answer(
                quiz_id=quiz.quiz_id,
                student_id=student_id,
                class_id=class_id,
                quiz_date=day,
                question_slot=slot,
                question_type=qtype,
                prompt=str(question.get("prompt") or ""),
                student_response=pack_response(response, label),
                correct=result["correct"],
                number_correct=result["number_correct"],
                label_correct=result["label_correct"],
            )
        except Exception as exc:
            st.error("That answer did not save. Tap Submit answer again; your earlier quiz answers are still saved.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
            return "blocked"
        if slot == QUIZ_QUESTION_COUNT:
            st.session_state[just_completed_key] = True
        st.rerun()

    return "blocked"
