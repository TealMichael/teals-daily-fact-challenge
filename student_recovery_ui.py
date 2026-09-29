from __future__ import annotations

"""Student-facing Monday Recovery between Igniter and Daily 10."""

from datetime import date
import html
import re

import streamlit as st

from indiana_question_bank import resolve_bank_image_path
from standards_recovery import build_recovery_plan, previous_friday_for_recovery
from weekly_quiz import grade_quiz_response, pack_response


def render_monday_recovery(store, day: date) -> str:
    """Render short standards Recovery on Monday after the Igniter.

    Returns: not_applicable, none, complete, or blocked. Recovery is deliberately
    fail-open: if this supplemental feature cannot load, Daily 10 remains usable.
    """
    friday = previous_friday_for_recovery(day)
    if friday is None:
        return "not_applicable"

    class_id = str(st.session_state.get("student_class_id") or "")
    student_id = str(st.session_state.get("student_id") or "")
    if not class_id or not student_id:
        return "none"

    try:
        quiz = store.get_weekly_quiz_set(class_id, friday)
        if quiz is None:
            return "none"
        quiz_answers = store.get_weekly_quiz_answers(student_id, quiz.quiz_id)
        plan = build_recovery_plan(quiz, quiz_answers, student_id=student_id, recovery_date=day)
        if not plan:
            return "none"
        saved = store.get_standard_recovery_answers(student_id, quiz.quiz_id)
    except Exception as exc:
        st.caption("Monday Recovery could not load just now. Continue with your Daily 10.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return "none"

    saved_codes = {str(row.standard_code) for row in saved}
    pending = [item for item in plan if item["standard_code"] not in saved_codes]
    just_completed_key = f"standards_recovery_just_completed::{student_id}::{quiz.quiz_id}::{day.isoformat()}"

    if not pending:
        if st.session_state.get(just_completed_key):
            st.markdown("## 🔁 Recovery complete!")
            st.success("Nice work. Your Recovery check has been saved to your standards progress.")
            st.caption("Next up: your regular Daily 10.")
            if st.button(
                "Start Daily 10 →", type="primary", use_container_width=True,
                key=f"recovery_start_daily_{quiz.quiz_id}_{day.isoformat()}",
            ):
                st.session_state[just_completed_key] = False
                st.rerun()
            return "blocked"
        return "complete"

    current = pending[0]
    question = dict(current["question"])
    standard_code = str(current["standard_code"])
    standard_description = str(current["standard_description"])
    qtype = str(question.get("question_type") or "Number")
    completed_count = len(plan) - len(pending)

    st.markdown("## 🔁 Monday Recovery")
    st.caption(
        f"Recovery {completed_count + 1} of {len(plan)} · {standard_code} · "
        "One quick check from Friday before your Daily 10."
    )
    st.progress(completed_count / max(1, len(plan)))
    if standard_description:
        st.caption(standard_description)

    raw_prompt = str(question.get("prompt") or "").strip()
    clean_prompt = re.sub(r"(?:\*\*|__|`)", "", raw_prompt).strip()
    prompt_html = html.escape(clean_prompt).replace("\n", "<br>")
    st.markdown(
        f"<div style='font-size:1.35rem;font-weight:750;line-height:1.45;margin:0.45rem 0 1rem 0;'>{prompt_html}</div>",
        unsafe_allow_html=True,
    )
    bank_image = resolve_bank_image_path(question.get("bank_image_path") or "")
    if bank_image:
        st.image(bank_image, width=460)

    response = ""
    label = ""
    bank_id = str(current.get("bank_question_id") or "")
    form_key = f"standards_recovery_{quiz.quiz_id}_{student_id}_{standard_code}_{bank_id}"
    with st.form(form_key, clear_on_submit=False):
        if qtype == "Multiple choice":
            options = [str(item) for item in (question.get("options") or [])]
            response = st.radio("Choose your answer", options, index=None, key=f"{form_key}_choice") if options else ""
        elif qtype == "Number + Label":
            left, right = st.columns([1.15, 1])
            with left:
                response = st.text_input("Your answer", key=f"{form_key}_number", placeholder="Enter a number")
            labels = [str(item) for item in (question.get("label_options") or [])]
            with right:
                label = st.selectbox("Label / unit", [""] + labels, key=f"{form_key}_label") if labels else ""
        else:
            placeholder = "Example: 3/4 or 2 1/3" if qtype == "Fraction" else "Enter your answer"
            response = st.text_input("Your answer", key=f"{form_key}_answer", placeholder=placeholder)
            if qtype in {"Number", "Fraction"}:
                st.caption("Equivalent numerical values count the same when mathematically equal.")
        submitted = st.form_submit_button("Save Recovery →", type="primary", use_container_width=True)

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
            store.record_standard_recovery_answer(
                source_quiz_id=quiz.quiz_id,
                student_id=student_id,
                class_id=class_id,
                recovery_date=day,
                source_quiz_date=friday,
                standard_code=standard_code,
                standard_description=standard_description,
                bank_question_id=bank_id,
                question_type=qtype,
                prompt=str(question.get("prompt") or ""),
                student_response=pack_response(response, label),
                correct=result["correct"],
                number_correct=result["number_correct"],
                label_correct=result["label_correct"],
            )
        except Exception as exc:
            st.error("That Recovery answer did not save. Tap Save Recovery again; your Friday quiz is still safe.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
            return "blocked"
        if len(pending) == 1:
            st.session_state[just_completed_key] = True
        st.rerun()

    return "blocked"
