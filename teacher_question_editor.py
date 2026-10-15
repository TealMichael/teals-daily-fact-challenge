from __future__ import annotations

"""Shared teacher-side answer editor for Igniter and Quiz of the Week.

The surrounding builders own prompt/standards/assignment metadata. This module
owns the answer-type selector and all answer-specific fields so common question
types cannot drift between the two teacher workflows.
"""

from collections.abc import Sequence

import streamlit as st

from curriculum_question_types import (
    COMPARE_QUESTION_TYPE,
    ORDER_DIRECTIONS,
    ORDER_QUESTION_TYPE,
    comparison_symbol,
    order_display,
    pack_order_response,
    sorted_order_items,
)
from indiana_question_bank import resolve_bank_image_path


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
    # Defensive compatibility: the shared editor owns the new interactive
    # question types. If an older caller supplies the pre-v2.24 type list,
    # inject Compare Values and Order Tiles so the teacher can still select
    # them while the rest of the v2.24 files are being deployed.
    types = list(dict.fromkeys(question_types))
    insert_at = types.index("Number + Label") + 1 if "Number + Label" in types else len(types)
    for interactive_type in (COMPARE_QUESTION_TYPE, ORDER_QUESTION_TYPE):
        if interactive_type not in types:
            types.insert(insert_at, interactive_type)
            insert_at += 1
    current_type = str(existing.get("question_type") or default_type)
    if current_type not in types:
        current_type = default_type if default_type in types else types[0]
    qtype = st.selectbox(
        "Answer type", types,
        index=types.index(current_type),
        key=f"{prefix}_type_{slot}",
    )

    compare_left = ""
    compare_right = ""
    order_items: list[str] = []
    order_direction = ""
    correct = ""

    if qtype == COMPARE_QUESTION_TYPE:
        left_col, right_col = st.columns(2)
        with left_col:
            compare_left = st.text_input(
                "Left value",
                value=str(existing.get("compare_left") or ""),
                key=f"{prefix}_compare_left_{slot}",
                placeholder="0.507",
            )
        with right_col:
            compare_right = st.text_input(
                "Right value",
                value=str(existing.get("compare_right") or ""),
                key=f"{prefix}_compare_right_{slot}",
                placeholder="0.57",
            )
        symbol = comparison_symbol(compare_left, compare_right)
        correct = symbol or ""
        if compare_left and compare_right:
            if symbol:
                st.success(f"Correct comparison: {compare_left} {symbol} {compare_right}")
            else:
                st.warning("Both comparison values must be valid numbers, decimals, fractions, or mixed numbers.")
        st.caption("Students tap <, =, or >. The correct symbol is calculated automatically using exact math.")

    elif qtype == ORDER_QUESTION_TYPE:
        raw_items = st.text_area(
            "Number tiles — one per line",
            value="\n".join(str(item) for item in (existing.get("order_items") or [])),
            key=f"{prefix}_order_items_{slot}",
            height=120,
            placeholder="0.45\n0.405\n0.54\n0.5",
            help="Use 3–6 whole numbers, decimals, fractions, or mixed numbers. Students will drag these tiles into order.",
        )
        order_items = _lines(raw_items)
        existing_direction = str(existing.get("order_direction") or ORDER_DIRECTIONS[0])
        if existing_direction not in ORDER_DIRECTIONS:
            existing_direction = ORDER_DIRECTIONS[0]
        order_direction = st.selectbox(
            "Order direction",
            ORDER_DIRECTIONS,
            index=ORDER_DIRECTIONS.index(existing_direction),
            key=f"{prefix}_order_direction_{slot}",
        )
        try:
            canonical = sorted_order_items(order_items, order_direction)
            correct = pack_order_response(canonical)
            st.success(f"Correct order: {order_display(canonical, order_direction)}")
        except ValueError as exc:
            correct = ""
            if order_items:
                st.warning(str(exc))
        st.caption("Students get touch-friendly draggable tiles. Equivalent values may appear next to each other in either order.")

    else:
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
    if qtype not in {"Multiple choice", COMPARE_QUESTION_TYPE, ORDER_QUESTION_TYPE}:
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

    session_state = getattr(st, "session_state", {})
    bank_image_path = str(
        session_state.get(f"{prefix}_bank_image_path_{slot}", existing.get("bank_image_path") or "")
        or ""
    )
    bank_image_alt = str(
        session_state.get(f"{prefix}_bank_image_alt_{slot}", existing.get("bank_image_alt") or "Built-in question diagram")
        or "Built-in question diagram"
    )
    bank_question_id = str(
        session_state.get(f"{prefix}_bank_question_id_{slot}", existing.get("bank_question_id") or "")
        or ""
    )
    resolved_bank_image = resolve_bank_image_path(bank_image_path)
    if resolved_bank_image:
        st.caption("Built-in Question Bank diagram · permanent app asset")
        st.image(resolved_bank_image, width=420)
        st.caption("A temporary image upload will display instead of this built-in diagram for the scheduled question.")
        remove_bank_image = st.checkbox(
            "Remove built-in bank diagram", value=False, key=f"{prefix}_remove_bank_image_{slot}"
        )
        if remove_bank_image:
            bank_image_path = ""
            bank_image_alt = "Built-in question diagram"
            bank_question_id = ""

    st.caption("Optional question image · PNG/JPG/WEBP · auto-deletes after scheduled date + 7 days")
    existing_image_path = str(existing.get("image_path") or "")
    if existing_image_path:
        st.caption("An image is currently attached. Upload a replacement or check Remove image.")
    uploader = getattr(st, "file_uploader", None)
    image_upload = uploader(
        "Upload PNG, JPG, or WEBP",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"{prefix}_image_{slot}",
        help="Images are resized automatically and deleted after the question date + 7 days.",
    ) if callable(uploader) else None
    checkbox = getattr(st, "checkbox", None)
    if image_upload is not None and hasattr(st, "image"):
        st.image(image_upload, width=420)
    remove_image = checkbox(
        "Remove image", value=False, key=f"{prefix}_remove_image_{slot}",
        disabled=not bool(existing_image_path),
    ) if callable(checkbox) else False
    image_alt = st.text_input(
        "Image description · optional",
        value=str(existing.get("image_alt") or "Question diagram"),
        key=f"{prefix}_image_alt_{slot}",
        help="Short description for accessibility, e.g. Rectangular prism labeled 8, 4, and 3 units.",
    )
    st.caption("Image files are temporary: automatically deleted 7 days after the scheduled question date.")

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
        "compare_left": compare_left,
        "compare_right": compare_right,
        "order_items": order_items,
        "order_direction": order_direction,
        "image_path": existing_image_path,
        "image_alt": image_alt,
        "bank_image_path": bank_image_path,
        "bank_image_alt": bank_image_alt,
        "bank_question_id": bank_question_id,
        "_image_upload": image_upload,
        "_remove_image": remove_image,
    }
