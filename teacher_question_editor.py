from __future__ import annotations

"""Shared teacher-side answer editor for Igniter and Quiz of the Week.

The surrounding builders own prompt/standards/assignment metadata. This module
owns the answer-type selector and all answer-specific fields so common question
types cannot drift between the two teacher workflows.
"""

from collections.abc import Sequence

import streamlit as st


def _lines(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def render_answer_editor(
    existing: dict,
    *,
    slot: int,
    prefix: str,
    question_types: Sequence[str],
    default_type: str,
) -> dict:
    types = list(question_types)
    current_type = str(existing.get("question_type") or default_type)
    if current_type not in types:
        current_type = default_type if default_type in types else types[0]
    qtype = st.selectbox(
        "Answer type", types,
        index=types.index(current_type),
        key=f"{prefix}_type_{slot}",
    )

    correct_caption = "Correct answer — Part 1" if qtype == "Multi-Part — 2 answers" else "Correct answer"
    correct = st.text_input(
        correct_caption,
        value=str(existing.get("correct_answer") or ""),
        key=f"{prefix}_correct_{slot}",
        help=(
            "Equivalent numerical values are graded mathematically. Example: 3 and 3.0 match; 3/4 and 6/8 match."
            if qtype in {"Number", "Fraction", "Number + Label"} else None
        ),
    )

    correct_two = ""
    if qtype == "Multi-Part — 2 answers":
        correct_two = st.text_input(
            "Correct answer — Part 2",
            value=str(existing.get("correct_answer_two") or ""),
            key=f"{prefix}_correct_two_{slot}",
        )

    options = ""
    if qtype == "Multiple choice":
        options = st.text_area(
            "Choices — one per line",
            value="\n".join(str(item) for item in (existing.get("options") or [])),
            key=f"{prefix}_options_{slot}", height=90,
        )
        st.caption("Type the correct answer above exactly as it appears in the choices.")

    labels = ""
    correct_label = ""
    if qtype == "Number + Label":
        labels = st.text_area(
            "Label / unit choices — one per line",
            value="\n".join(str(item) for item in (existing.get("label_options") or [])),
            key=f"{prefix}_labels_{slot}", height=82,
            placeholder="feet\nsquare feet\nyards\nsquare yards",
        )
        correct_label = st.text_input(
            "Correct label / unit",
            value=str(existing.get("correct_label") or ""),
            key=f"{prefix}_correct_label_{slot}",
        )
        st.caption("The question counts correct only when both the numerical answer and label are correct.")

    alternates = ""
    if qtype != "Multiple choice":
        alternates = st.text_area(
            "Accepted alternate answers — optional, one per line",
            value="\n".join(str(item) for item in (existing.get("accepted_answers") or [])),
            key=f"{prefix}_alternates_{slot}", height=70,
        )

    alternates_two = ""
    if qtype == "Multi-Part — 2 answers":
        alternates_two = st.text_area(
            "Accepted Part 2 alternate answers — optional, one per line",
            value="\n".join(str(item) for item in (existing.get("accepted_answers_two") or [])),
            key=f"{prefix}_alternates_two_{slot}", height=70,
        )

    if qtype == "Fraction":
        st.caption("Students can type fractions and mixed numbers, such as 3/4 or 2 1/3. Equivalent values are accepted.")
    elif qtype == "Number":
        st.caption("Equivalent numerical values count the same, such as 3 and 3.0.")
    elif qtype == "Expanded Form":
        st.caption("Students must show the actual place-value sum. A numerically equal standard-form number will not count.")

    return {
        "question_type": qtype,
        "correct_answer": correct,
        "correct_answer_two": correct_two,
        "accepted_answers": _lines(alternates),
        "accepted_answers_two": _lines(alternates_two),
        "options": _lines(options),
        "label_options": _lines(labels),
        "correct_label": correct_label,
    }
