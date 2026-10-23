from __future__ import annotations

"""v2.26 minimal teacher Today: lesson completion, reteach, and one Outlook link.

Other teacher tools retain their own pages. No Daily 10, Top 10, mastery, or
student writes occur here.
"""

import html
from datetime import date

import streamlit as st

from fact_engine import current_daily_date
from igniter_popout import render_igniter_window_button
from teacher_today_overview import load_today_lessons, recent_mastery_checkins, today_reteach
from teacher_warmup_ui import (
    _warmup_email_recipients,
    _warmup_grouping,
    _warmup_outlook_url,
    _warmup_report_text,
)


def _date_label(day: date) -> str:
    return day.strftime("%A, %B %d").replace(" 0", " ")


def _card_label(lesson) -> str:
    name = str(lesson.class_record.class_name)
    if lesson.error:
        return f"{name}\n\nUnavailable · Refresh"
    if lesson.assignment is None:
        return f"{name}\n\nNo activity assigned"
    noun = "Quiz submitted" if lesson.kind == "Quiz" else "Igniter complete"
    return f"{name}\n\n{lesson.complete}/{lesson.total} {noun}"


def _render_class_cards(lessons) -> object:
    st.markdown("""<style>
    div[class*="st-key-today_card_"] button {
        min-height: 112px;
        border-radius: 14px;
        border-width: 1.5px;
        white-space: pre-line;
        font-size: 1.04rem;
        line-height: 1.65;
        font-weight: 650;
    }
    div[class*="st-key-today_card_active"] button {
        border: 2px solid #087968;
        background: #e6f5ef;
        color: #163f36;
    }
    </style>""", unsafe_allow_html=True)

    known = {str(lesson.class_record.class_id) for lesson in lessons}
    selected_id = str(st.session_state.get("teacher_today_class_id") or "")
    if selected_id not in known:
        selected_id = str(lessons[0].class_record.class_id)
        st.session_state["teacher_today_class_id"] = selected_id

    # Four classroom blocks look balanced as two equal rows of two cards.
    # Always retain the empty columns in a partial final row so no card expands
    # to the full page width when another class is added later.
    per_row = 2 if len(lessons) == 4 else 3
    for start in range(0, len(lessons), per_row):
        row = lessons[start:start + per_row]
        cols = st.columns(per_row, gap="medium")
        for offset, lesson in enumerate(row):
            index = start + offset
            cid = str(lesson.class_record.class_id)
            with cols[offset]:
                state = "active" if cid == selected_id else "other"
                with st.container(key=f"today_card_{state}_{index}"):
                    if st.button(
                        _card_label(lesson), width="stretch",
                        key=f"today_pick_class_{index}",
                        help=f"Show {lesson.class_record.class_name} reteaching needs",
                    ):
                        st.session_state["teacher_today_class_id"] = cid
                        st.rerun()
    return next(lesson for lesson in lessons if str(lesson.class_record.class_id) == selected_id)


def _render_standard_groups(groups: list[dict]) -> None:
    for group in groups:
        code = html.escape(str(group["code"]))
        description = html.escape(str(group.get("description") or ""))
        names = ", ".join(group["names"])
        title = f"{code} — {description}" if description else code
        st.markdown(f"**{title}**")
        st.write(names)


def _render_warmup_outlook_link(store, lesson, day: date) -> None:
    if lesson.kind != "Igniter" or lesson.assignment is None or lesson.error:
        return
    klass = lesson.class_record
    primary, secondary = _warmup_email_recipients(store, klass.class_id)
    if not primary:
        st.caption("Set your Outlook recipients in Warm-Up to enable the email.")
        return
    # Reuse the exact existing report/subject/Outlook URL, without an alternate
    # copy of its formatting rules. Nothing is sent automatically.
    grouping = _warmup_grouping(lesson.students, lesson.rows)
    if not lesson.rows:
        st.caption("The Outlook report will be available after students submit their Igniter.")
        return
    report = _warmup_report_text(klass, day, lesson.assignment, grouping)
    subject = f"Warm-Up Results — {klass.class_name} — {day.strftime('%b %d')}"
    st.link_button(
        "📧 Prepare Warm-Up Email",
        _warmup_outlook_url(primary, secondary, subject, report),
        type="secondary",
        width="content",
    )
    st.caption("Opens the familiar draft in Outlook for your review. Nothing is sent automatically.")


def render_teacher_today_command_center(
    store, *, ensure_today_fn, refresh_control, finish_refresh,
    set_refresh_stamp, leaderboard_from_status, leaderboard_is_final,
    leaderboard_final_key, mystery_pending_draw, go_teacher_tool,
) -> None:
    # Legacy callback parameters remain for the other teacher modules and
    # compatibility tests. Today no longer needs leaderboard or Daily reads.
    day = current_daily_date()
    st.session_state.setdefault("teacher_today_day", day)
    # A new school date should not retain stale selected-slide state.
    st.session_state["teacher_today_day"] = day
    title, refresh = st.columns([5, 1.5], vertical_alignment="center")
    with title:
        st.markdown("## Today")
        st.caption(_date_label(day))
    with refresh:
        refresh_control(key="teacher_today_refresh")

    try:
        classes = store.list_classes()
        if not classes:
            st.info("Create a class in Manage to get started.")
            return
        lessons = load_today_lessons(store, day, classes)
    except Exception:
        st.warning("Classroom progress could not refresh just now. Choose Refresh data to try again.")
        st.session_state.pop("teacher_refresh_pending", None)
        return

    if st.session_state.get("teacher_refresh_pending"):
        finish_refresh()
    else:
        set_refresh_stamp()
    selected = _render_class_cards(lessons)

    st.markdown(f"### {html.escape(selected.class_record.class_name)}")
    if selected.error:
        st.warning("This class's Igniter or Quiz results are temporarily unavailable. Refresh to try again.")
        return

    if selected.kind == "Igniter":
        render_igniter_window_button(selected.class_record.class_id, day)
        try:
            _render_warmup_outlook_link(store, selected, day)
        except Exception:
            st.caption("The Warm-Up email is temporarily unavailable. Its original tool remains in Warm-Up.")
    if selected.assignment is None:
        st.info("No Igniter or Friday Quiz is published for this class today.")
    else:
        activity = "Friday Quiz" if selected.kind == "Quiz" else "Igniter"
        if selected.complete == 0:
            st.caption(f"No completed {activity} responses yet. Unfinished answers are never counted as incorrect.")
        else:
            st.caption(f"{selected.complete} of {selected.total} students finished the {activity}.")

    st.markdown("#### Teaching priorities")
    today_groups = today_reteach(selected)
    if today_groups:
        st.caption("Today's needs · Based on students who completed the Igniter or Quiz")
        _render_standard_groups(today_groups)
    else:
        try:
            recent = recent_mastery_checkins(store, selected, day)
        except Exception:
            recent = []
            st.caption("Recent mastery suggestions are temporarily unavailable.")
        if recent:
            st.caption("Worth checking in with · Repeated earlier misses from the Mastery Tracker")
            _render_standard_groups(recent)
        elif selected.assignment is not None and selected.complete:
            st.success("No reteaching priorities from completed work today.")
        else:
            st.caption("Today's needs will appear as students finish the Igniter or Quiz.")
