from __future__ import annotations

"""Teacher Today: class snapshots, Igniter pull groups and prior standards.

Other teacher tools retain their own pages. No Daily 10, Top 10, mastery, or
student writes occur here.
"""

import html
from datetime import date

import streamlit as st

from fact_engine import current_daily_date
from igniter_popout import render_igniter_window_button
from indiana_question_bank import SUPPORTED_BANK_TYPES, questions_for_standard, resolve_bank_image_path
from teacher_today_overview import load_today_lessons, recent_mastery_checkins, today_reteach
from teacher_warmup_ui import (
    _warmup_email_recipients,
    _warmup_grouping,
    _warmup_instruction_recommendation,
    _warmup_outlook_url,
    _warmup_report_text,
)
from warmup import question_for_slot


def _date_label(day: date) -> str:
    return day.strftime("%A, %B %d").replace(" 0", " ")


def _card_label(lesson, grouping: dict | None = None) -> str:
    name = str(lesson.class_record.class_name)
    if lesson.error:
        return f"{name}\n\nUnavailable · Refresh"
    if lesson.assignment is None:
        return f"{name}\n\nNo activity assigned"
    noun = "Quiz submitted" if lesson.kind == "Quiz" else "Igniter complete"
    label = f"{name}\n\n{lesson.complete}/{lesson.total} {noun}"
    if grouping is not None:
        if grouping["completed_count"]:
            label += (
                f"\n\nMissed Q1 **{len(grouping['q1_support'])}** · "
                f"Missed Q2 **{len(grouping['q2_support'])}** · "
                f"Missed both **{len(grouping['missed_both'])}**"
            )
        else:
            label += "\n\nAwaiting completed Igniters" if lesson.total else "\n\nNo active students"
    return label


def _select_today_class(class_id: str) -> None:
    # Callbacks run before the render, so choosing a card needs one live refresh.
    st.session_state["teacher_today_class_id"] = class_id


def _render_class_cards(lessons, groupings: dict | None = None) -> object:
    st.markdown("""<style>
    .block-container:has(div[class*="st-key-today_card_"]) {max-width: 1100px;}
    div[class*="st-key-today_card_"] button {
        min-height: 104px;
        border-radius: 14px;
        border-width: 1.5px;
        padding: 15px 18px;
        text-align: left;
    }
    div[class*="st-key-today_card_"] button > div {width: 100%;}
    div[class*="st-key-today_card_"] button [data-has-shortcut] {width: 100%;}
    div[class*="st-key-today_card_"] button [data-testid="stMarkdownContainer"] {
        display: grid; grid-template-columns: 1fr auto;
        gap: 10px 12px; width: 100%;
    }
    div[class*="st-key-today_card_"] button p {margin: 0; line-height: 1.45;}
    div[class*="st-key-today_card_"] button p:first-child {font-weight: 650;}
    div[class*="st-key-today_card_"] button p:nth-child(2) {font-size: .94rem; text-align: right;}
    div[class*="st-key-today_card_"] button p:nth-child(3) {
        grid-column: 1 / -1; border-top: 1px solid #d4dfdb;
        padding-top: 9px; font-size: .86rem; color: #536773;
    }
    div[class*="st-key-today_card_"] button p:nth-child(3) strong:last-of-type {
        color: #765400;
    }
    div[class*="st-key-today_card_active"] button {
        border: 2px solid #087968;
        background: #e6f5ef;
        color: #163f36;
    }
    .today-results {display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
        padding: 4px 0 20px; border-bottom: 1px solid #d6dce0; margin-bottom: 4px;}
    .today-result {padding: 0 22px; border-left: 1px solid #d6dce0; min-width: 0;}
    .today-result:first-child {padding-left: 0; border-left: 0;}
    .today-result-label, .today-result-detail {color: #647080; font-size: .88rem;}
    .today-result-value {font-size: 2.2rem; font-weight: 700; line-height: 1.25;
        font-variant-numeric: tabular-nums; color: #111827;}
    .today-result-detail {font-size: .83rem; margin-top: 3px;}
    .today-name-list {display: flex; flex-wrap: wrap; gap: 7px; align-items: flex-start;}
    .today-name {display: inline-block; padding: 4px 9px; border-radius: 6px;
        background: #f4f7f6; color: #111827; font-size: .94rem;
        line-height: 1.4; overflow-wrap: anywhere;}
    /* Each panel is a single HTML block. Its own box, not a fixed-height
       Streamlit container, must grow with wrapped names at every width. */
    .today-priority-panel, .today-question-panel {
        box-sizing: border-box; width: 100%; display: flex; flex-direction: column;
        height: auto; overflow: visible;
    }
    .today-priority-panel {background: #fff8e5; border: 1px solid #ead8a2;
        border-radius: 12px; padding: 18px 20px 20px; gap: 12px;}
    .today-priority-panel .today-name {background: #fff;}
    .today-priority-heading {display: flex; flex-wrap: wrap; align-items: baseline;
        gap: 4px 12px; font-size: 1.11rem; font-weight: 700; line-height: 1.4;
        color: #111827;}
    .today-priority-count {font-size: .97rem; font-weight: 500; color: #765400;}
    .today-question-panel {border: 1px solid #d6dce0; border-radius: 12px;
        padding: 14px 18px 16px; margin-top: 12px; gap: 8px;}
    .today-question-heading {font-size: 1.07rem; font-weight: 700;
        color: #111827; line-height: 1.4;}
    .today-question-standard {color: #647080; font-size: .9rem; line-height: 1.45;}
    .today-question-empty {color: #647080; font-size: .88rem;}
    .st-key-today_unfinished {border-top: 1px solid #d6dce0; padding-top: 12px;}
    .st-key-today_history {border-top: 1px solid #d6dce0; padding-top: 18px; margin-top: 12px;}
    .today-history-row {background: #f4f7f6; border-radius: 7px; padding: 12px 15px;
        display: flex; justify-content: space-between; gap: 8px 24px; flex-wrap: wrap;}
    .today-history-names {color: #647080; overflow-wrap: anywhere;}
    .st-key-today_actions [data-testid="stLinkButton"] a {min-height: 46px;}
    @media (max-width: 650px) {
        div[class*="st-key-today_card_"] button [data-testid="stMarkdownContainer"] {grid-template-columns: 1fr;}
        div[class*="st-key-today_card_"] button p:nth-child(2) {text-align: left;}
        .today-result {padding: 0 10px;}
        .today-result-value {font-size: 1.8rem;}
        .today-result-label, .today-result-detail {font-size: .8rem;}
        .today-priority-panel {padding: 15px 16px 17px;}
        .today-question-panel {padding: 13px 16px 15px;}
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
                    st.button(
                        _card_label(lesson, (groupings or {}).get(cid)), width="stretch",
                        key=f"today_pick_class_{index}",
                        help=f"Show {lesson.class_record.class_name} reteaching needs",
                        on_click=_select_today_class, args=(cid,),
                    )
    return next(lesson for lesson in lessons if str(lesson.class_record.class_id) == selected_id)


def _worked_with_button(store, lesson, *, code: str, student_ids: list[str], day: date,
                        key: str, exclude_bank_ids=()) -> None:
    """One-click default, with optional student and bank-question choices.

    The existing missed-question group is the only eligible roster: a stale
    widget value can never assign a check to an unrelated student.
    """
    if not code or not student_ids or not hasattr(store, "assign_standard_quick_checks"):
        return
    roster = {str(student.student_id): str(student.nickname)
              for student in lesson.students}
    eligible = sorted(
        {str(sid) for sid in student_ids if str(sid) in roster},
        key=lambda sid: (roster[sid].casefold(), sid),
    )
    if not eligible:
        return

    # Separate choices per class, group, and day. Start with all students to
    # preserve the original single-click path, but honor a teacher's subset.
    picker_key = f"{key}::students::{day.isoformat()}"
    if picker_key not in st.session_state:
        st.session_state[picker_key] = list(eligible)
    else:
        allowed = set(eligible)
        st.session_state[picker_key] = [sid for sid in st.session_state[picker_key]
                                         if sid in allowed]

    # Choose from this standard's built-in bank. An edited or unrelated
    # question cannot sneak in through stale Streamlit widget state.
    excluded = {str(item) for item in exclude_bank_ids if str(item)}
    bank_rows = [row for row in questions_for_standard(code)
                 if row.get("question_type") in SUPPORTED_BANK_TYPES
                 and str(row.get("id") or "") not in excluded]
    bank_rows.sort(key=lambda row: str(row.get("id") or ""))
    bank_by_id = {str(row["id"]): row for row in bank_rows}
    question_key = f"{key}::bank_question::{day.isoformat()}::{code}"
    if question_key not in st.session_state or st.session_state[question_key] not in ("", *bank_by_id):
        st.session_state[question_key] = ""

    button_col, picker_col = st.columns([1.85, 1], gap="small")
    with picker_col:
        with st.popover("Customize check", width="stretch",
                        help="Select students and optionally choose their exact question."):
            st.caption("Select the students you actually worked with.")
            st.multiselect("Students to check", options=eligible,
                           format_func=lambda sid: roster[sid], key=picker_key,
                           placeholder="Choose students")
            st.selectbox(
                "Question to send", ["", *bank_by_id], key=question_key,
                format_func=lambda bank_id: (
                    "Automatic · fresh question for each student" if not bank_id else
                    f"Q{bank_by_id[bank_id].get('question_number', '')} · "
                    f"{str(bank_by_id[bank_id].get('prompt') or '')[:100]}"
                ),
                help="Choose a bank question to give every selected student the same check. "
                     "Automatic retains the usual fresh question per student.",
            )
            preview_id = str(st.session_state[question_key] or "")
            if preview_id in bank_by_id:
                row = bank_by_id[preview_id]
                st.markdown("**Question preview**")
                st.write(str(row.get("prompt") or ""))
                if row.get("question_type") == "Multiple choice":
                    st.caption("Choices: " + " · ".join(str(item) for item in row.get("options") or ()))
                elif row.get("question_type") == "Compare Values":
                    st.caption(f"Compare: {row.get('compare_left', '')} ? {row.get('compare_right', '')}")
                elif row.get("question_type") == "Order Tiles":
                    st.caption("Tiles: " + " · ".join(str(item) for item in row.get("order_items") or ()))
                image_path = resolve_bank_image_path(row.get("bank_image_path") or "")
                if image_path:
                    st.image(image_path, width=320)
                correct = str(row.get("correct_answer") or "").strip()
                if correct:
                    label = str(row.get("correct_label") or "").strip()
                    st.caption(f"Teacher answer: {correct}{' ' + label if label else ''}")

    selected = [sid for sid in st.session_state[picker_key] if sid in set(eligible)]
    chosen_bank_id = str(st.session_state[question_key] or "")
    all_selected = len(selected) == len(eligible)
    send_label = (f"✓ Worked With · Send to all {len(eligible)}" if all_selected
                  else f"✓ Worked With · Send to {len(selected)}")
    with button_col:
        send = st.button(send_label, key=key, type="secondary",
                         disabled=not selected,
                         help="Assign one independent check only to the selected students.",
                         width="stretch")
    if send:
        try:
            count = store.assign_standard_quick_checks(
                class_id=lesson.class_record.class_id,
                student_ids=selected, standard_code=code, assigned_date=day,
                exclude_bank_ids=tuple(exclude_bank_ids),
                bank_question_id=chosen_bank_id,
            )
            st.success(f"Quick Check available for {count} student{'s' if count != 1 else ''}. "
                       "They can reopen the app when they return to their seats.")
        except ValueError as exc:
            st.warning(str(exc))
        except Exception:
            st.error("Quick Checks are not ready. Verify the v2.28 database setup before assigning.")
    if chosen_bank_id in bank_by_id:
        prompt = str(bank_by_id[chosen_bank_id].get("prompt") or "").strip()
        st.caption(f"Chosen question: {prompt[:88]}{'…' if len(prompt) > 88 else ''}")


def _render_standard_groups(groups: list[dict], *, store=None, lesson=None, day=None) -> None:
    for group in groups:
        code = html.escape(str(group["code"]))
        description = html.escape(str(group.get("description") or ""))
        names = ", ".join(group["names"])
        title = f"{code} — {description}" if description else code
        st.markdown(f"**{title}**")
        st.write(names)
        if store is not None and lesson is not None and day is not None:
            _worked_with_button(store, lesson, code=str(group["code"]),
                                student_ids=list(group.get("student_ids") or []), day=day,
                                key=f"worked_quiz_{lesson.class_record.class_id}_{group['code']}")


def _render_warmup_outlook_link(store, lesson, day: date, *, grouping: dict | None = None,
                                compact: bool = False) -> None:
    if lesson.kind != "Igniter" or lesson.assignment is None or lesson.error:
        return
    klass = lesson.class_record
    primary, secondary = _warmup_email_recipients(store, klass.class_id)
    if not primary:
        st.caption("Set your Outlook recipients in Warm-Up to enable the email.")
        return
    # Reuse the exact existing report/subject/Outlook URL, without an alternate
    # copy of its formatting rules. Nothing is sent automatically.
    if grouping is None:
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
        **({"help": "Opens the familiar draft in Outlook for your review. Nothing is sent automatically."}
           if compact else {}),
    )
    if not compact:
        st.caption("Opens the familiar draft in Outlook for your review. Nothing is sent automatically.")


def _names_html(names: list[str]) -> str:
    """Nicknames are text, never interpreted as Markdown or HTML."""
    tags = "".join(f'<span class="today-name">{html.escape(str(name))}</span>' for name in names)
    return f'<div class="today-name-list">{tags}</div>'


def _render_names(names: list[str]) -> None:
    st.markdown(_names_html(names), unsafe_allow_html=True)


def _render_igniter_snapshot(grouping: dict) -> None:
    values = [("Igniter complete", f"{grouping['completed_count']}/{grouping['student_count']}",
               f"{len(grouping['unfinished'])} not finished")]
    for slot in (1, 2):
        accuracy = grouping[f"accuracy_q{slot}"]
        value = "—" if accuracy is None else f"{accuracy:.0f}%"
        missed = grouping[f"answered_q{slot}"] - grouping[f"correct_q{slot}"]
        detail = (f"{grouping[f'correct_q{slot}']} correct · {missed} missed"
                  if accuracy is not None else "No responses yet")
        values.append((f"Q{slot} accuracy", value, detail))
    cells = "".join(
        '<div class="today-result">'
        f'<div class="today-result-label">{label}</div>'
        f'<div class="today-result-value">{value}</div>'
        f'<div class="today-result-detail">{detail}</div></div>'
        for label, value, detail in values
    )
    st.markdown(f'<div class="today-results" role="group" aria-label="Class results">{cells}</div>',
                unsafe_allow_html=True)
    if any(grouping[f"answered_q{slot}"] > grouping["completed_count"] for slot in (1, 2)):
        st.caption("Accuracy includes submitted answers. Pull groups require both questions to be finished.")


def _render_igniter_priorities(store, lesson, grouping: dict, day: date) -> None:
    """Present the existing completed-student groups, without changing evidence."""
    st.markdown("#### Who to pull today")
    both = grouping["missed_both"]
    if both:
        count = f"{len(both)} student{'s' if len(both) != 1 else ''}"
        st.markdown(
            '<div class="today-priority-panel" role="group" aria-label="First priority: missed both questions">'
            '<div class="today-priority-heading"><span>First priority · Missed both questions</span>'
            f'<span class="today-priority-count">{count}</span></div>'
            f'{_names_html(both)}</div>', unsafe_allow_html=True,
        )
    else:
        st.caption("First priority · Missed both questions: none among completed Igniters.")

    columns = st.columns(2, gap="medium")
    for slot, label in ((1, "Spiral Review"), (2, "Yesterday's Lesson")):
        with columns[slot - 1]:
            names = grouping[f"q{slot}_only"]
            question = question_for_slot(lesson.assignment, slot)
            code = str(question.get("standard_code") or "").strip()
            description = str(question.get("standard_description") or "").strip()
            title_attr = f' title="{html.escape(description, quote=True)}"' if description else ""
            subtitle = html.escape(f"{label} · {code}" if code else label)
            count = f"{len(names)} student{'s' if len(names) != 1 else ''}"
            names_or_empty = (_names_html(names) if names else
                              f'<div class="today-question-empty">No students missed only Question {slot}.</div>')
            st.markdown(
                f'<div class="today-question-panel" role="group" aria-label="Missed Q{slot} only">'
                f'<div class="today-question-heading">Missed Q{slot} only · {count}</div>'
                f'<div class="today-question-standard"{title_attr}>{subtitle}</div>'
                f'{names_or_empty}</div>', unsafe_allow_html=True,
            )
            from standards_tagging import reconcile_tag
            decision = reconcile_tag(code, description, str(question.get("prompt") or ""))
            support_names = set(grouping[f"q{slot}_support"])
            target_ids = [str(student.student_id) for student in lesson.students
                          if student.nickname in support_names]
            _worked_with_button(store, lesson, code=decision.code,
                                student_ids=target_ids, day=day,
                                exclude_bank_ids=(str(question.get("bank_question_id") or ""),),
                                key=f"worked_igniter_{lesson.class_record.class_id}_{slot}")

    notes = []
    if both:
        notes.append("Missed-both students count in both question totals but appear once above.")
    recommendations = [(f"Q{slot}", _warmup_instruction_recommendation(len(grouping[f"q{slot}_support"])))
                       for slot in (1, 2) if grouping[f"q{slot}_support"]]
    if recommendations:
        if len({text for _, text in recommendations}) == 1:
            notes.append(recommendations[0][1])
        else:
            notes.append(" · ".join(f"{label}: {text}" for label, text in recommendations))
    if notes:
        st.caption(" · ".join(notes))
    if grouping["completed_count"] and not (both or grouping["q1_only"] or grouping["q2_only"]):
        st.success("No students to pull from completed Igniters today.")
    with st.container(key="today_unfinished"):
        st.markdown(f"**Not finished · {len(grouping['unfinished'])}**")
        if grouping["unfinished"]:
            _render_names(grouping["unfinished"])
        st.caption("Incomplete work is separate from incorrect answers.")


def _render_historical_checkins(store, lesson, day: date) -> None:
    """Always show the selected class's bounded, prior-day evidence separately."""
    with st.container(key="today_history"):
        st.markdown("##### Previous missed standards")
        st.caption("Follow up after today's Igniter or Quiz groups · Repeated misses on prior dates; excludes today's results.")
        _render_historical_rows(store, lesson, day)


def _render_historical_rows(store, lesson, day: date) -> None:
    try:
        recent = recent_mastery_checkins(store, lesson, day)
    except Exception:
        st.caption("Historical check-ins are temporarily unavailable. Refresh to try again.")
        return
    if recent:
        for group in recent:
            code = html.escape(str(group["code"]))
            description = html.escape(str(group.get("description") or ""))
            title = f"<strong>{code}</strong> · {description}" if description else f"<strong>{code}</strong>"
            names = " · ".join(html.escape(str(name)) for name in group["names"])
            st.markdown(f'<div class="today-history-row"><span>{title}</span>'
                        f'<span class="today-history-names">{names}</span></div>', unsafe_allow_html=True)
            _worked_with_button(store, lesson, code=str(group["code"]),
                                student_ids=list(group.get("student_ids") or []), day=day,
                                key=f"worked_history_{lesson.class_record.class_id}_{group['code']}")
    else:
        st.caption("No historical standards currently meet the check-in criteria.")


def _render_quick_check_results(store, lesson, day: date) -> None:
    """Results are opt-in to avoid another Supabase read on every Today visit."""
    key = f"show_quick_check_results_{lesson.class_record.class_id}_{day.isoformat()}"
    if not st.button("View small-group check results", key=f"open_{key}", type="secondary"):
        if not st.session_state.get(key):
            return
    st.session_state[key] = True
    try:
        rows = store.list_standard_quick_checks(day, day,
                    class_id=lesson.class_record.class_id, include_test=True)
    except Exception:
        st.caption("Quick Check results are not available yet. Verify the v2.28 database setup.")
        return
    valid_ids = {str(student.student_id) for student in lesson.students}
    rows = [row for row in rows if str(row.student_id) in valid_ids]
    if not rows:
        st.caption("No small-group Quick Checks were assigned to this class today.")
        return
    done = [row for row in rows if row.completed_at is not None]
    correct = sum(bool(row.correct) for row in done)
    st.caption(f"{len(done)}/{len(rows)} checks completed · {correct} correct · "
               f"{len(done) - correct} needing another look")
    by_code = {}
    for row in rows:
        cell = by_code.setdefault(str(row.standard_code), {"assigned": 0, "done": 0, "correct": 0})
        cell["assigned"] += 1
        if row.completed_at is not None:
            cell["done"] += 1
            cell["correct"] += int(bool(row.correct))
    for code, item in sorted(by_code.items()):
        st.write(f"**{code}** · {item['done']}/{item['assigned']} complete · "
                 f"{item['correct']} correct")


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
    # Compute once per loaded Igniter, from the same live rows already fetched.
    # Cards, selected results, pull groups and the exact Outlook report share it.
    groupings = {
        str(lesson.class_record.class_id): _warmup_grouping(lesson.students, lesson.rows)
        for lesson in lessons
        if lesson.kind == "Igniter" and lesson.assignment is not None and not lesson.error
    }
    selected = _render_class_cards(lessons, groupings)

    grouping = groupings.get(str(selected.class_record.class_id))
    if grouping is not None:
        heading, actions = st.columns([1, 1.4], vertical_alignment="center")
        with heading:
            st.markdown(f"### {html.escape(selected.class_record.class_name)} · Today's Igniter")
        with actions, st.container(key="today_actions"):
            display, email = st.columns([1, 1.3], gap="small")
            with display:
                render_igniter_window_button(selected.class_record.class_id, day)
            with email:
                try:
                    _render_warmup_outlook_link(store, selected, day, grouping=grouping, compact=True)
                except Exception:
                    st.caption("The Warm-Up email is temporarily unavailable. Its original tool remains in Warm-Up.")
        _render_igniter_snapshot(grouping)
    else:
        st.markdown(f"### {html.escape(selected.class_record.class_name)}")
    if selected.error:
        st.warning("This class's Igniter or Quiz results are temporarily unavailable. Refresh to try again.")
        _render_historical_checkins(store, selected, day)
        return

    if selected.assignment is None:
        st.info("No Igniter or Friday Quiz is published for this class today.")

    if grouping is not None:
        if grouping["completed_count"]:
            _render_igniter_priorities(store, selected, grouping, day)
        else:
            st.markdown("#### Who to pull today")
            st.info("Awaiting completed Igniters. Pull groups will appear as students finish both questions."
                    if selected.total else "No active students in this class.")
            with st.container(key="today_unfinished"):
                st.markdown(f"**Not finished · {len(grouping['unfinished'])}**")
                if grouping["unfinished"]:
                    _render_names(grouping["unfinished"])
                st.caption("Incomplete work is separate from incorrect answers.")
    else:
        title = "Today's Friday Quiz: Students to Pull" if selected.kind == "Quiz" else "Today's teaching priorities"
        st.markdown(f"#### {title}")
        today_groups = today_reteach(selected)
        if today_groups:
            st.caption("Today's needs · Based on students who completed the Quiz")
            _render_standard_groups(today_groups, store=store, lesson=selected, day=day)
        elif selected.assignment is not None and selected.complete:
            st.success("No reteaching priorities from completed work today.")
        else:
            st.caption("Today's needs will appear as students finish the Igniter or Quiz.")

    if selected.assignment is not None:
        activity = "Friday Quiz" if selected.kind == "Quiz" else "Igniter"
        if selected.complete == 0:
            st.caption(f"No completed {activity} responses yet. Unfinished answers are never counted as incorrect.")
        elif selected.kind == "Quiz":
            st.caption(f"{selected.complete} of {selected.total} students finished the {activity}.")
    _render_historical_checkins(store, selected, day)
    _render_quick_check_results(store, selected, day)
