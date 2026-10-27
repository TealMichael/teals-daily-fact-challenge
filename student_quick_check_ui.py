from __future__ import annotations

"""One teacher-assigned, independent standards check after small-group teaching.

Completely separate from the official Daily attempt, timer, leaderboard,
Recovery, and Mystery. Supplemental errors fail open to the normal daily flow.
"""

from datetime import date
import html
import re
from time import monotonic

import streamlit as st

from curriculum_question_types import (
    COMPARE_QUESTION_TYPE, COMPARISON_SYMBOLS, ORDER_QUESTION_TYPE,
    deterministic_start_order, pack_order_response,
)
from indiana_question_bank import resolve_bank_image_path
from interactive_math_questions import render_order_tiles
from student_growth_ui import (note_new_standard_answer, render_standard_progress,
                               standard_snapshot)
from weekly_quiz import grade_quiz_response, pack_response


def render_assigned_quick_check(store, day: date) -> bool:
    """True means continue the usual routine; False means show this one check."""
    sid = str(st.session_state.get("student_id") or "")
    cid = str(st.session_state.get("student_class_id") or "")
    if not sid or not cid:
        return True

    feedback_key = f"quick_check_feedback::{sid}::{cid}"
    feedback = st.session_state.get(feedback_key)
    if isinstance(feedback, dict):
        st.markdown("## ✅ Quick Check complete!")
        if feedback.get("correct"):
            st.success("Nice work! Your independent check has been saved.")
        else:
            st.info("Your check is saved. Your teacher can use it to plan what's next.")
        render_standard_progress(store, sid, cid, day,
                                 code=feedback.get("code", ""),
                                 description=feedback.get("description", ""),
                                 previous_progress=feedback.get("before"),
                                 show_growth=bool(feedback.get("correct")),
                                 suppress_decline=not bool(feedback.get("correct")))
        if st.button("Return to my daily routine →", type="primary", use_container_width=True,
                     key=f"quick_check_continue_{feedback.get('check_id')}"):
            st.session_state.pop(feedback_key, None)
            st.rerun()
        return False

    poll_key = f"quick_check_poll::{sid}::{cid}"
    state = st.session_state.get(poll_key)
    if isinstance(state, tuple) and monotonic() - state[0] < 12.0:
        check = state[1]
    else:
        try:
            check = store.get_pending_standard_quick_check(sid, cid)
        except Exception:
            # A missing additive migration cannot strand a student.
            check = None
        st.session_state[poll_key] = (monotonic(), check)
    if not check:
        return True

    question = dict(check.get("question") or {})
    code = str(check.get("standard_code") or "")
    description = str(check.get("standard_description") or "")
    check_id = str(check.get("check_id") or "")
    qtype = str(question.get("question_type") or "Number")

    st.markdown("## 🧠 Your Small-Group Quick Check")
    st.caption(f"{code} · Just one new question from your teacher, then you're done.")
    prompt = re.sub(r"(?:\*\*|__|`)", "", str(question.get("prompt") or "")).strip()
    st.markdown(
        f"<div style='font-size:1.35rem;font-weight:750;line-height:1.45;margin:.4rem 0 1rem'>"
        f"{html.escape(prompt).replace(chr(10), '<br>')}</div>", unsafe_allow_html=True,
    )
    bank_image = resolve_bank_image_path(question.get("bank_image_path") or "")
    if bank_image:
        st.image(bank_image, width=460)
    render_standard_progress(store, sid, cid, day, code=code, description=description)

    response, label = "", ""
    form_key = f"quick_check_answer_{check_id}"
    order_response = ""
    if qtype == ORDER_QUESTION_TYPE:
        items = [str(item) for item in question.get("order_items") or []]
        direction = str(question.get("order_direction") or "Least to greatest")
        try:
            start = deterministic_start_order(items, seed=f"{sid}:{check_id}", direction=direction)
        except ValueError:
            start = items
        st.caption(f"Drag the tiles from {direction.lower()}.")
        current = render_order_tiles(items, initial_order=start,
                                     key=f"quick_check_tiles_{sid}_{check_id}",
                                     instruction=f"Order from {direction.lower()}.")
        order_response = pack_order_response(current)

    with st.form(form_key, clear_on_submit=False):
        if qtype == "Multiple choice":
            choices = [str(item) for item in question.get("options") or []]
            response = st.radio("Choose your answer", choices, index=None,
                                key=f"{form_key}_choices") if choices else ""
        elif qtype == COMPARE_QUESTION_TYPE:
            left, right = question.get("compare_left", ""), question.get("compare_right", "")
            st.markdown(f"**{html.escape(str(left))} &nbsp; ? &nbsp; {html.escape(str(right))}**",
                        unsafe_allow_html=True)
            response = st.radio("Choose the symbol", list(COMPARISON_SYMBOLS), index=None,
                                horizontal=True, key=f"{form_key}_compare")
        elif qtype == ORDER_QUESTION_TYPE:
            response = order_response
            st.caption("When your tiles are ready, submit your check.")
        elif qtype == "Number + Label":
            a, b = st.columns([1.15, 1])
            with a:
                response = st.text_input("Number", key=f"{form_key}_number")
            labels = [str(item) for item in question.get("label_options") or []]
            with b:
                label = st.selectbox("Label / unit", [""] + labels, key=f"{form_key}_label")
        else:
            response = st.text_input("Your answer", key=f"{form_key}_answer",
                                     placeholder="Example: 3/4" if qtype == "Fraction" else "Type your answer")
        submitted = st.form_submit_button("Submit Quick Check →", type="primary", use_container_width=True)

    if submitted:
        response, label = str(response or "").strip(), str(label or "").strip()
        if not response or (qtype == "Number + Label" and not label):
            st.warning("Enter your complete answer before submitting.")
            return False
        before = standard_snapshot(store, sid, cid, day, code)
        graded = grade_quiz_response(question, response, label)
        try:
            store.complete_standard_quick_check(check_id, sid,
                student_response=pack_response(response, label), correct=bool(graded["correct"]))
        except Exception:
            st.error("Your check did not save. Try submitting again. Your Daily 10 is safe.")
            return False
        note_new_standard_answer(sid, cid, day, code=code, description=description,
                                 prompt=str(question.get("prompt") or ""),
                                 correct=bool(graded["correct"]), source="Quick Check")
        st.session_state[feedback_key] = {
            "check_id": check_id, "code": code, "description": description,
            "correct": bool(graded["correct"]),
            "before": before.progress if before is not None else None,
        }
        st.session_state.pop(poll_key, None)
        st.rerun()
    return False
