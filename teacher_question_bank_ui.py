from __future__ import annotations

"""Teacher-facing browser for the built-in Indiana Standards Question Bank."""

import random
import streamlit as st

from indiana_math_standards import BY_CODE
from indiana_question_bank import (
    BANK_GRADES,
    SUPPLEMENTAL_CODES,
    bank_summary,
    domains_for_grade,
    questions_for_standard,
    is_essential_standard,
    resolve_bank_image_path,
    seed_editor_state,
    standard_codes_for,
    standard_label,
)


def _default_bank_grade(existing: dict | None) -> int:
    code = str((existing or {}).get("standard_code") or "").strip()
    try:
        grade = int(code.split(".", 1)[0])
    except (ValueError, IndexError):
        grade = 5
    return grade if grade in BANK_GRADES else 5


def _current_draft_prompt(existing: dict | None, *, prefix: str, slot: int) -> str:
    key = f"{prefix}_prompt_{int(slot)}"
    return str(st.session_state.get(key, (existing or {}).get("prompt") or "") or "").strip()


def render_inline_question_bank_picker(
    existing: dict | None,
    *,
    prefix: str,
    slot: int,
    include_standard: bool,
    disabled: bool = False,
) -> None:
    """Compact Grade → Standard → Question picker for one editor slot.

    It renders before the slot's normal widgets. Loading therefore seeds only
    that slot's widget state and reruns before the editor widgets are created,
    preserving draft work in every other slot. The surrounding builder's normal
    Save button remains the only action that writes the question set.
    """
    slot = int(slot)
    with st.expander("📚 Add from Indiana Question Bank", expanded=False):
        default_grade = _default_bank_grade(existing)
        grade = st.selectbox(
            "Grade",
            BANK_GRADES,
            index=BANK_GRADES.index(default_grade),
            format_func=lambda value: f"Grade {value}",
            key=f"{prefix}_bank_grade_{slot}",
            disabled=disabled,
        )

        codes = list(standard_codes_for(grade))
        if not codes:
            st.info("No Question Bank standards are available for this grade.")
            return

        existing_code = str((existing or {}).get("standard_code") or "").strip()
        default_code = existing_code if existing_code in codes else codes[0]
        standard_code = st.selectbox(
            "Standard",
            codes,
            index=codes.index(default_code),
            format_func=standard_label,
            key=f"{prefix}_bank_standard_{slot}_{grade}",
            disabled=disabled,
        )

        questions = list(questions_for_standard(standard_code))
        if not questions:
            st.info("No questions are available for this standard.")
            return

        choices = [str(index) for index in range(1, len(questions) + 1)] + ["Random"]
        choice = st.selectbox(
            "Question",
            choices,
            key=f"{prefix}_bank_question_{slot}_{standard_code}",
            disabled=disabled,
        )

        selected = None
        if choice == "Random":
            st.caption(f"Random chooses one of this standard's {len(questions)} questions when you press Load.")
        else:
            selected = questions[int(choice) - 1]
            image_note = " · 🖼 diagram" if selected.get("bank_image_path") else ""
            st.caption(
                f"{selected.get('question_type', 'Number')}{image_note} · "
                f"{str(selected.get('prompt') or '')}"
            )

        has_draft = bool(_current_draft_prompt(existing, prefix=prefix, slot=slot))
        button_label = "Replace current question" if has_draft else "Load into this question"
        st.caption("Loading changes only this question slot. Other draft questions stay in place.")
        if st.button(
            button_label,
            type="primary",
            use_container_width=True,
            disabled=disabled,
            key=f"{prefix}_bank_load_{slot}_{standard_code}_{choice}",
        ):
            if choice == "Random":
                selected = random.SystemRandom().choice(questions)
            seed_editor_state(
                st.session_state,
                prefix=prefix,
                slot=slot,
                question=selected,
                include_standard=include_standard,
            )
            st.rerun()


def _queue_question(question: dict, destination: str) -> None:
    st.session_state["question_bank_pending"] = dict(question)
    st.session_state["question_bank_destination"] = destination
    # v2.27 groups both individual editors under Plan. Retain the pending
    # question so its original destination editor can pick it up unchanged.
    st.session_state["teacher_plan_redirect"] = "Warm-Up Editor" if destination == "warmup" else "Quiz Builder"
    st.session_state["teacher_primary_redirect"] = "Plan"


def _render_teacher_answer(question: dict) -> None:
    qtype = str(question.get("question_type") or "Number")
    answer = str(question.get("correct_answer") or "")
    if qtype == "Number + Label":
        answer = f"{answer} {question.get('correct_label') or ''}".strip()
    elif qtype == "Compare Values":
        answer = f"{question.get('compare_left', '')} {answer} {question.get('compare_right', '')}".strip()
    elif qtype == "Order Tiles":
        from curriculum_question_types import order_display, sorted_order_items
        try:
            answer = order_display(
                sorted_order_items(question.get("order_items") or (), question.get("order_direction") or ""),
                question.get("order_direction") or "",
            )
        except ValueError:
            answer = "Invalid order question"
    st.markdown(f"**Answer:** {answer}")
    if question.get("worked_solution"):
        st.write(question["worked_solution"])
    if question.get("dok"):
        st.caption(f"Estimated DOK {question['dok']} · {question.get('dok_rationale', '')}")
    if question.get("teacher_extension"):
        st.markdown("**Optional discussion:** " + question["teacher_extension"])
        st.caption("Teacher-led extension; not part of the auto-scored question.")
    alternates = list(question.get("accepted_answers") or ())
    if alternates:
        st.caption("Also accepts: " + " · ".join(str(item) for item in alternates))


def _render_question(question: dict) -> None:
    count = len(questions_for_standard(question.get("standard_code") or ""))
    st.markdown(f"### Question {int(question.get('question_number') or 1)} of {count}")
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
    elif qtype == "Compare Values":
        st.write(f"{question.get('compare_left', '')}   [ <  =  > ]   {question.get('compare_right', '')}")
    elif qtype == "Order Tiles":
        st.caption(f"Drag tiles · {question.get('order_direction', 'Least to greatest')}")
        st.write(" · ".join(str(item) for item in (question.get("order_items") or ())))

    with st.expander("Teacher answer", expanded=False):
        _render_teacher_answer(question)


def render_teacher_question_bank(store=None) -> None:
    summary = bank_summary()
    st.markdown("### 📚 Indiana Standards Question Bank")
    st.caption("Grade 5: 40 questions for each of the 23 standards in the supplied current framework, plus 30 retained supplemental questions. Grades 6–7 retain 10 questions per standard. Built-in content contains no student data and does not use Supabase storage.")
    st.caption("Fastest multi-question workflow: open Igniter or Quiz of the Week and use the inline Question Bank picker inside each question slot.")

    a, b, c = st.columns(3)
    a.metric("Questions", summary["questions"])
    b.metric("Standards", summary["curriculum_standards"])
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
        badge = " · Supplemental" if selected_code in SUPPLEMENTAL_CODES else (" · ★ Essential" if is_essential_standard(selected_code) else "")
        st.info(f"**{selected_code}{badge}** — {standard.description}")
        if selected_code in SUPPLEMENTAL_CODES:
            st.caption("Retained for existing lessons; this code is not listed among the 23 Grade 5 standards in the supplied current framework.")

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

    with st.expander(f"See all {len(questions)} questions for this standard", expanded=False):
        for row in questions:
            essential = " ★" if row.get("essential") else ""
            st.markdown(f"**{row['question_number']}. {row['prompt']}**{essential}")
            _render_teacher_answer(row)
