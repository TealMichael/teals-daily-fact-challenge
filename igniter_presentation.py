from __future__ import annotations

"""Teacher-only projection of published Igniters. No student writes or reveal state."""

import base64
from datetime import date, timedelta
from functools import lru_cache
import html
from pathlib import Path
import re
from uuid import uuid4

import streamlit as st

from fact_engine import current_daily_date
from indiana_question_bank import resolve_bank_image_path
from question_images import signed_question_image_url
from warmup import correct_answer_for_storage, display_student_response


def teacher_can_present() -> bool:
    return bool(st.session_state.get("teacher_authed")) and not bool(
        st.session_state.get("teacher_test_student_mode")
    ) and st.session_state.get("app_mode", "Teacher") == "Teacher"


def open_igniter_presentation(class_id: str, day: date | None = None) -> None:
    if not teacher_can_present():
        return
    st.session_state["igniter_presentation"] = {
        "class_id": str(class_id),
        # None means today's published questions, recalculated every open.
        "day": (day or current_daily_date()).isoformat(),
        "nonce": uuid4().hex,
    }


def math_text(value: str) -> str:
    """Escaped classroom text with readable numeric fractions and exponents.

    Supports the bank's plain-text notation plus common teacher-entered LaTeX
    fractions/operators. It never accepts raw HTML or executes Markdown links.
    """
    raw = str(value or "")
    for source, target in ((r"\times", "×"), (r"\div", "÷"), (r"\cdot", "·"),
                           (r"\leq", "≤"), (r"\geq", "≥"), (r"\neq", "≠"),
                           (r"\pi", "π"), (r"\pm", "±")):
        raw = raw.replace(source, target)
    # Keep algebraic fraction contents as text, not executable markup.
    tokens = []
    def fraction(match):
        top, bottom = match.group(1), match.group(2)
        tokens.append('<span class="fraction" role="math" aria-label="' +
                      html.escape(top + ' over ' + bottom, quote=True) + '">' +
                      '<span>' + html.escape(top) + '</span><span>' +
                      html.escape(bottom) + '</span></span>')
        return f"\x00{len(tokens)-1}\x00"
    raw = re.sub(r"\\(?:d?frac)\{([^{}\n]+)\}\{([^{}\n]+)\}", fraction, raw)
    raw = re.sub(r"(?<![\w/])([−-]?\d+)\s*/\s*(\d+)(?![\w/])", fraction, raw)
    # Dollar-delimited math is common in teacher entry; remove only paired delimiters.
    raw = re.sub(r"\$([^$\n]+)\$", r"\1", raw)
    result = html.escape(raw).replace("\n", "<br>")
    result = re.sub(r"\^\{([\w+−-]+)\}|\^([−-]?\d+)",
                    lambda m: '<sup>' + (m.group(1) or m.group(2)) + '</sup>', result)
    for index, fragment in enumerate(tokens):
        result = result.replace(f"\x00{index}\x00", fragment)
    return result


def question_html(question: dict, image_url: str = "") -> str:
    q = question
    content = '<div class="prompt">' + math_text(q.get("prompt", "")) + '</div>'
    kind = q.get("question_type")
    if kind == "Multiple choice":
        content += '<ol class="choices" type="A">' + ''.join(
            '<li>' + math_text(x) + '</li>' for x in q.get("options", [])) + '</ol>'
    elif kind == "Compare Values":
        content += '<div class="compare">' + math_text(q.get("compare_left", "")) + \
            '<span class="compare-blank">?</span>' + math_text(q.get("compare_right", "")) + '</div>'
        content += '<p class="hint">Choose &lt;, =, or &gt;.</p>'
    elif kind == "Order Tiles":
        content += '<p class="hint">' + html.escape(q.get("order_direction") or "Least to greatest") + '</p>'
        content += '<div class="tiles">' + ''.join('<span>' + math_text(x) + '</span>'
                    for x in q.get("order_items", [])) + '</div>'
    elif kind == "Number + Label":
        content += '<p class="hint">Include a unit: ' + ' · '.join(
            math_text(x) for x in q.get("label_options", [])) + '</p>'
    elif kind == "Multi-Part — 2 answers":
        content += '<p class="hint">Write both answers.</p>'
    if image_url:
        content += '<img class="diagram" src="' + html.escape(image_url, quote=True) + \
            '" alt="' + html.escape(q.get("image_alt") or q.get("bank_image_alt") or "Question diagram", quote=True) + '">'
    elif q.get("image_path") or q.get("bank_image_path"):
        content += '<p class="image-warning">Question image unavailable. Check the assignment before presenting.</p>'
    return content


def answer_text(question: dict) -> str:
    if question.get("question_type") == "Expanded Form":
        # The stored correct value is standard form; show the requested expanded sum.
        from decimal import Decimal
        try:
            value = Decimal(str(question.get("correct_answer", "")))
            if value.is_finite() and value >= 0:
                digits = format(value, "f")
                whole, _, decimal = digits.partition(".")
                terms = [str(int(d) * 10**i) for i, d in reversed(list(enumerate(reversed(whole)))) if d != '0']
                terms.extend(format(Decimal(d).scaleb(-i), "f")
                             for i, d in enumerate(decimal, 1) if d != '0')
                return " + ".join(terms) if terms else "0"
        except Exception:
            pass
    return display_student_response(correct_answer_for_storage(question), question.get("question_type", ""))


def question_image_url(store, question: dict) -> str:
    if question.get("image_path"):
        url = signed_question_image_url(store, question["image_path"])
        if url:
            return url
    path = resolve_bank_image_path(question.get("bank_image_path") or "")
    if path:
        return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return ""


@lru_cache(maxsize=1)
def _component():
    root = Path(__file__).with_name("igniter_presentation_assets")
    return st.components.v2.component(
        "tdfc_igniter_presentation_v2251",
        html=(root / "presentation.html").read_text(),
        css=(root / "presentation.css").read_text(),
        js=(root / "presentation.js").read_text(),
    )


def render_igniter_presentation(store) -> None:
    # Guard before all assignment/answer-key reads; student routes never invoke this.
    if not teacher_can_present():
        st.session_state.pop("igniter_presentation", None)
        st.warning("Sign in as a teacher to display an Igniter.")
        return
    context = st.session_state.get("igniter_presentation") or {}
    def dashboard_fallback():
        if st.button("← Teacher Dashboard", key="igniter_presentation_exit_fallback"):
            st.session_state.pop("igniter_presentation", None)
            st.rerun()
    try:
        day = date.fromisoformat(context.get("day") or current_daily_date().isoformat())
        class_id = context["class_id"]
        getter = getattr(store, "get_class", None)
        klass = getter(class_id) if callable(getter) else next(
            c for c in store.list_classes(include_inactive=True) if str(c.class_id) == str(class_id))
        # Always use published data, never the planner's draft/session editor.
        warmup = store.get_warmup_set(class_id, day)
    except Exception:
        st.error("The published Igniter could not load. Return to the dashboard and try again.")
        dashboard_fallback()
        return
    if warmup is None:
        st.info(f"No published Igniter for {day.strftime('%A, %B %d')}. Choose another date.")
        dashboard_fallback()
        chosen = st.date_input("Presentation date", day, key="empty_igniter_date")
        if st.button("Display selected date"):
            open_igniter_presentation(class_id, chosen)
            st.rerun()
        return
    st.markdown("""<style>
    [data-testid="stHeader"], [data-testid="stToolbar"], footer {display:none!important}
    .block-container {max-width:none!important;padding:0.4rem 1rem!important}
    </style>""", unsafe_allow_html=True)
    questions = [warmup.question_one, warmup.question_two]
    cards = [{"content": question_html(q, question_image_url(store, q)),
              "answer": math_text(answer_text(q))} for q in questions]
    identity = f"{context.get('nonce')}:{warmup.warmup_set_id}:{warmup.updated_at}"
    result = _component()(
        data={"identity": identity,
              "className": klass.class_name, "date": day.strftime("%A · %B %d, %Y"),
              "cards": cards}, key="teacher_igniter_slide",
        on_action_change=lambda: None,
    )
    event = getattr(result, "action", None)
    # Trigger values can survive an explicit Streamlit rerun. A navigation event
    # belongs only to the slide that emitted it, so it can never advance twice.
    action = event.get("action") if isinstance(event, dict) and event.get("identity") == identity else None
    if action == "exit":
        st.session_state.pop("igniter_presentation", None)
        st.rerun()
    elif action in {"previous", "next", "today"}:
        target = current_daily_date() if action == "today" else day + timedelta(days=-1 if action == "previous" else 1)
        open_igniter_presentation(class_id, target)
        st.rerun()
