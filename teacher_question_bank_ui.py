from __future__ import annotations

"""Teacher-facing browser for the built-in Indiana Standards Question Bank."""

import random
import streamlit as st

from indiana_math_standards import BY_CODE
from indiana_question_bank import (
    BANK_GRADES,
    bank_summary,
    domains_for_grade,
    questions_for_standard,
    is_essential_standard,
    resolve_bank_image_path,
    standard_codes_for,
    standard_label,
)


def _queue_question(question: dict, destination: str) -> None:
    st.session_state["question_bank_pending"] = dict(question)
    st.session_state["question_bank_destination"] = destination
    st.session_state["teacher_primary_redirect"] = "🧠 Warm-Up" if destination == "warmup" else "📝 Quiz of the Week"


def _render_teacher_answer(question: dict) -> None:
    qtype = str(question.get("question_type") or "Number")
    answer = str(question.get("correct_answer") or "")
    if qtype == "Number + Label":
        answer = f"{answer} {question.get('correct_label') or ''}".strip()
    st.markdown(f"**Answer:** {answer}")
    alternates = list(question.get("accepted_answers") or ())
    if alternates:
        st.caption("Also accepts: " + " · ".join(str(item) for item in alternates))


def _render_question(question: dict) -> None:
    st.markdown(f"### Question {int(question.get('question_number') or 1)} of 10")
    meta = [str(question.get("flavor") or "Practice"), str(question.get("difficulty") or "On-level"), str(question.get("question_type") or "Number")]
    st.caption(" · ".join(meta))
    st.markdown(f"**{question.get('prompt', '')}**")

    image_path = resolve_bank_image_path(question.get("bank_image_path") or "")
    if image_path:
        st.image(image_path, width=460)
        if question.get("bank_image_alt"):
            st.caption(str(question.get("bank_image_alt")))

    qtype = str(question.get("question_type") or "")
    if qtype == "Multiple choice":
        for letter, option in zip("ABCD", question.get("options") or ()):
            st.write(f"{letter}. {option}")
    elif qtype == "Number + Label":
        st.caption("Unit choices: " + " · ".join(str(item) for item in (question.get("label_options") or ())))

    with st.expander("Teacher answer", expanded=False):
        _render_teacher_answer(question)


def render_teacher_question_bank(store=None) -> None:
    summary = bank_summary()
    st.markdown("### 📚 Indiana Standards Question Bank")
    st.caption("Ready-to-use Grade 5–7 questions aligned to the 2023 Indiana Academic Standards. Built-in bank content contains no student data and does not use Supabase storage.")

    a, b, c = st.columns(3)
    a.metric("Questions", summary["questions"])
    b.metric("Standards", summary["standards"])
    c.metric("Essential standards", summary["essential_standards"])

    grade = st.radio("Grade", BANK_GRADES, horizontal=True, format_func=lambda value: f"Grade {value}", key="question_bank_grade")
    domains = domains_for_grade(grade)
    domain = st.selectbox("Domain", domains, key=f"question_bank_domain_{grade}")
    essential_only = st.checkbox("Show Essential standards only", value=False, key=f"question_bank_essential_{grade}_{domain}")
    codes = standard_codes_for(grade, domain, essential_only=essential_only)
    if not codes:
        st.info("No standards match those filters.")
        return

    selected_code = st.selectbox(
        "Standard", codes,
        format_func=standard_label,
        key=f"question_bank_standard_{grade}_{domain}_{essential_only}",
    )
    standard = BY_CODE.get(selected_code)
    if standard is not None:
        badge = " · ★ Essential" if is_essential_standard(selected_code) else ""
        st.info(f"**{selected_code}{badge}** — {standard.description}")

    questions = list(questions_for_standard(selected_code))
    index_key = f"question_bank_index_{selected_code}"
    index = int(st.session_state.get(index_key, 0)) % len(questions)

    prev_col, random_col, next_col = st.columns(3)
    with prev_col:
        if st.button("← Previous", use_container_width=True, key=f"bank_prev_{selected_code}"):
            st.session_state[index_key] = (index - 1) % len(questions)
            st.rerun()
    with random_col:
        if st.button("🎲 Random", use_container_width=True, key=f"bank_random_{selected_code}"):
            choices = [i for i in range(len(questions)) if i != index] or [index]
            st.session_state[index_key] = random.SystemRandom().choice(choices)
            st.rerun()
    with next_col:
        if st.button("Next →", use_container_width=True, key=f"bank_next_{selected_code}"):
            st.session_state[index_key] = (index + 1) % len(questions)
            st.rerun()

    question = questions[index]
    with st.container(border=True):
        _render_question(question)
        left, right = st.columns(2)
        with left:
            if st.button("🧠 Use in Igniter", type="primary", use_container_width=True, key=f"bank_igniter_{question['id']}"):
                _queue_question(question, "warmup")
                st.rerun()
        with right:
            if st.button("📝 Use in Quiz of the Week", use_container_width=True, key=f"bank_quiz_{question['id']}"):
                _queue_question(question, "quiz")
                st.rerun()
        st.caption("The question is copied into the normal editor. You can change any wording, numbers, choices, units, or image before saving.")

    with st.expander("See all 10 questions for this standard", expanded=False):
        for row in questions:
            essential = " ★" if row.get("essential") else ""
            st.markdown(f"**{row['question_number']}. {row['prompt']}**{essential}")
            _render_teacher_answer(row)
