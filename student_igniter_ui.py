from __future__ import annotations

"""Student Igniter UI.

The optional two-question Igniter is isolated from the Daily 10 renderer so
future curriculum-question changes cannot accidentally alter the Daily flow.
"""

from datetime import date
import html
import re

import streamlit as st

from supabase_fact_store import SupabaseFactStore
from warmup import answer_matches as warmup_answer_matches, question_for_slot

def render_quick_warmup(store: SupabaseFactStore, day: date) -> bool:
    """Render the optional two-question curriculum Warm-Up.

    Returns True when no Warm-Up is assigned or the student has already
    completed it. Warm-Up responses never touch multiplication mastery or the
    Daily leaderboard.
    """
    class_id = str(st.session_state.get("student_class_id") or "")
    student_id = str(st.session_state.get("student_id") or "")
    if not class_id or not student_id:
        return True

    try:
        warmup = store.get_warmup_set(class_id, day)
    except Exception as exc:
        st.error("Today's Igniter could not be loaded. Show your teacher this screen.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return False
    if warmup is None:
        return True

    try:
        answers = store.get_warmup_answers(student_id, warmup.warmup_set_id)
    except Exception as exc:
        st.error("Your Igniter progress could not be loaded. Show your teacher this screen.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return False

    answered_slots = {int(row.question_slot) for row in answers}
    completed = len(answered_slots) >= 2
    feedback = st.session_state.get("warmup_feedback")
    feedback_matches = isinstance(feedback, dict) and feedback.get("warmup_set_id") == warmup.warmup_set_id

    if completed:
        if st.session_state.get("warmup_just_completed") == warmup.warmup_set_id:
            # Completion and correctness are deliberately separate.  Students
            # should never read a green completion check as evidence that Q2
            # was correct.
            if feedback_matches:
                if feedback.get("correct"):
                    st.success("✅ Correct!")
                else:
                    answer_text = html.escape(str(feedback.get("correct_answer", "")))
                    st.error(f"❌ Not quite. The answer is {answer_text}.")
                st.session_state.warmup_feedback = None
            st.markdown("## 🧠 Igniter complete!")
            st.info("Both questions are finished. Ready for your Daily 10!")
            if st.button("Start Daily 10 →", type="primary", use_container_width=True, key=f"warmup_start_daily_{warmup.warmup_set_id}"):
                st.session_state.warmup_just_completed = None
                st.session_state.warmup_feedback = None
                st.rerun()
            return False
        return True

    if feedback_matches:
        if feedback.get("correct"):
            st.success("✅ Correct!")
        else:
            answer_text = html.escape(str(feedback.get("correct_answer", "")))
            st.error(f"❌ Not quite. The answer is {answer_text}.")
        st.session_state.warmup_feedback = None

    slot = 1 if 1 not in answered_slots else 2
    question = question_for_slot(warmup, slot)
    st.markdown(f"## 🧠 Igniter Question {slot}")
    raw_prompt = str(question.get("prompt") or "").strip()
    # Teacher-entered Markdown should never leak literal ** / __ / backticks to students.
    clean_prompt = re.sub(r"(?:\*\*|__|`)", "", raw_prompt).strip()
    prompt_html = html.escape(clean_prompt).replace("\n", "<br>")
    st.markdown(
        f"<div style='font-size:1.35rem;font-weight:700;line-height:1.45;margin:0.35rem 0 1rem 0;'>{prompt_html}</div>",
        unsafe_allow_html=True,
    )

    form_key = f"warmup_answer_{warmup.warmup_set_id}_{student_id}_{slot}"
    with st.form(form_key, clear_on_submit=False):
        if question.get("question_type") == "Multiple choice":
            options = [str(value) for value in (question.get("options") or [])]
            response = st.radio("Choose your answer", options, key=f"warmup_choice_{warmup.warmup_set_id}_{slot}") if options else ""
        else:
            response = st.text_input("Your answer", key=f"warmup_text_{warmup.warmup_set_id}_{slot}", placeholder="Type your answer")
        submitted = st.form_submit_button("Check answer →", type="primary", use_container_width=True)

    if submitted:
        response = str(response or "").strip()
        if not response:
            st.warning("Enter an answer first.")
            return False
        correct_answer = str(question.get("correct_answer") or "")
        correct = warmup_answer_matches(response, correct_answer, question.get("accepted_answers") or ())
        try:
            store.record_warmup_answer(
                warmup_set_id=warmup.warmup_set_id,
                student_id=student_id,
                class_id=class_id,
                warmup_date=day,
                question_slot=slot,
                question_type=str(question.get("question_type") or "Short answer"),
                prompt=str(question.get("prompt") or ""),
                standard_code=str(question.get("standard_code") or ""),
                standard_description=str(question.get("standard_description") or ""),
                student_answer=response,
                correct_answer=correct_answer,
                correct=correct,
            )
        except Exception as exc:
            st.error("That answer did not save. Tap Check answer again; you do not need to redo anything else.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
            return False
        st.session_state.warmup_feedback = {
            "warmup_set_id": warmup.warmup_set_id,
            "correct": bool(correct),
            "correct_answer": correct_answer,
        }
        if slot == 2:
            st.session_state.warmup_just_completed = warmup.warmup_set_id
        st.rerun()
    return False
