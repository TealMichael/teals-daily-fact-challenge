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
from warmup import (correct_answer_for_storage, display_student_response, grade_question, pack_multi_part_response, question_for_slot)

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

    # Once today's two saved Igniter responses have been observed complete, the
    # rest of the student routine should not re-download the same Warm-Up set +
    # answer rows on every Daily/Fix/Focus rerun.  The cache is scoped to this
    # student, class, and date, so tomorrow (or another student) always rechecks.
    complete_cache_key = f"warmup_complete::{student_id}::{class_id}::{day.isoformat()}"
    if st.session_state.get(complete_cache_key, False):
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
                st.session_state[complete_cache_key] = True
                st.rerun()
            return False
        st.session_state[complete_cache_key] = True
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
    qtype = str(question.get("question_type") or "Short answer")
    response_two = ""
    with st.form(form_key, clear_on_submit=False):
        if qtype == "Multiple choice":
            options = [str(value) for value in (question.get("options") or [])]
            response = st.radio("Choose your answer", options, key=f"warmup_choice_{warmup.warmup_set_id}_{slot}") if options else ""
        elif qtype == "Multi-Part — 2 answers":
            response = st.text_input("Part 1", key=f"warmup_text_{warmup.warmup_set_id}_{slot}_1", placeholder="First answer")
            response_two = st.text_input("Part 2", key=f"warmup_text_{warmup.warmup_set_id}_{slot}_2", placeholder="Second answer")
        else:
            placeholder = "Type the expanded form" if qtype == "Expanded Form" else "Type your answer"
            response = st.text_input("Your answer", key=f"warmup_text_{warmup.warmup_set_id}_{slot}", placeholder=placeholder)
        submitted = st.form_submit_button("Check answer →", type="primary", use_container_width=True)

    if submitted:
        response = str(response or "").strip()
        response_two = str(response_two or "").strip()
        if not response or (qtype == "Multi-Part — 2 answers" and not response_two):
            st.warning("Enter both answers first." if qtype == "Multi-Part — 2 answers" else "Enter an answer first.")
            return False
        correct = grade_question(question, response, response_two)
        stored_response = pack_multi_part_response(response, response_two) if qtype == "Multi-Part — 2 answers" else response
        correct_answer = correct_answer_for_storage(question)
        try:
            store.record_warmup_answer(
                warmup_set_id=warmup.warmup_set_id,
                student_id=student_id,
                class_id=class_id,
                warmup_date=day,
                question_slot=slot,
                question_type=qtype,
                prompt=str(question.get("prompt") or ""),
                standard_code=str(question.get("standard_code") or ""),
                standard_description=str(question.get("standard_description") or ""),
                student_answer=stored_response,
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
            "correct_answer": display_student_response(correct_answer, qtype),
        }
        if slot == 2:
            st.session_state.warmup_just_completed = warmup.warmup_set_id
        st.rerun()
    return False
