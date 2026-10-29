from __future__ import annotations

"""Teacher Today: class snapshots, Igniter pull groups and prior standards.

Other teacher tools retain their own pages. No Daily 10, Top 10, mastery, or
student writes occur here.
"""

import html
import time
from datetime import date

import streamlit as st

from fact_engine import current_daily_date
from igniter_popout import render_igniter_window_button
from indiana_question_bank import SUPPORTED_BANK_TYPES, questions_for_standard, resolve_bank_image_path
from standards_recovery import question_standard_metadata
from standards_tagging import reconcile_tag
from teacher_today_overview import load_today_lessons, recent_mastery_checkins, today_reteach
from teacher_warmup_ui import (
    _warmup_email_recipients,
    _warmup_grouping,
    _warmup_instruction_recommendation,
    _warmup_outlook_url,
    _warmup_report_text,
)
from warmup import question_for_slot


_CHECK_CACHE_SECONDS = 20


def _date_label(day: date) -> str:
    return day.strftime("%A, %B %d").replace(" 0", " ")


def _card_label(lesson, grouping: dict | None = None) -> str:
    name = str(lesson.class_record.class_name)
    if lesson.error:
        return f"{name}\n\nUnavailable"
    if lesson.assignment is None:
        return f"{name}\n\nNo activity assigned"
    noun = "quiz submitted" if lesson.kind == "Quiz" else "Igniter complete"
    return f"{name}\n\n{lesson.complete}/{lesson.total} {noun}"


def _select_today_class(class_id: str) -> None:
    # Callbacks run before the render, so choosing a card needs one live refresh.
    st.session_state["teacher_today_class_id"] = class_id


def _today_standard_targets(lesson, grouping: dict | None) -> dict[str, set[str]]:
    """Exact student/standard pairs requiring follow-up from completed work.

    A student missing both questions on the same standard needs only one
    assignment, since the database permits one independent check per standard
    per day. Anonymous student IDs avoid duplicate-nickname collisions.
    """
    if lesson.error or lesson.assignment is None:
        return {}
    if lesson.kind == "Quiz":
        return {str(group["code"]): set(map(str, group["student_ids"]))
                for group in today_reteach(lesson) if group.get("code")}
    if lesson.kind != "Igniter" or not grouping:
        return {}

    targets: dict[str, set[str]] = {}
    for slot in (1, 2):
        question = question_for_slot(lesson.assignment, slot)
        decision = reconcile_tag(
            question.get("standard_code", ""), question.get("standard_description", ""),
            question.get("prompt", ""),
        )
        if not decision.code:
            continue
        missed_ids = {
            str(row.student_id) for row in lesson.rows
            if str(row.student_id) in lesson.completed_ids
            and int(row.question_slot) == slot and not bool(row.correct)
        }
        if missed_ids:
            targets.setdefault(decision.code, set()).update(missed_ids)
    return targets


def _today_followup_coverage(lesson, targets: dict[str, set[str]], rows) -> dict:
    """A group is addressed only when every missed student/code has a check.

    'Assigned' means the check exists, whether answered or pending. One button
    click does not clear a group if the teacher selected only a subset.
    """
    required = {(str(sid), code) for code, students in targets.items() for sid in students}
    class_id = str(lesson.class_record.class_id)
    assigned = {
        (str(row.student_id), str(row.standard_code)) for row in (rows or ())
        if str(row.class_id) == class_id
    }
    covered = required & assigned
    return {"required": len(required), "assigned": len(covered),
            "remaining": required - assigned, "clear": not (required - assigned)}


def _today_has_unmatched_misses(lesson) -> bool:
    """Do not hide a wrong answer merely because its standard tag is unusable."""
    if lesson.assignment is None or lesson.error:
        return False
    for answer in lesson.rows:
        if str(answer.student_id) not in lesson.completed_ids or bool(answer.correct):
            continue
        slot = int(answer.question_slot)
        if lesson.kind == "Quiz":
            questions = tuple(getattr(lesson.assignment, "questions", ()) or ())
            if not 1 <= slot <= len(questions):
                return True
            code, description = question_standard_metadata(questions[slot - 1])
            prompt = str(getattr(answer, "prompt", "") or questions[slot - 1].get("prompt") or "")
        else:
            if slot not in (1, 2):
                return True
            question = question_for_slot(lesson.assignment, slot)
            code = str(question.get("standard_code") or "")
            description = str(question.get("standard_description") or "")
            prompt = str(question.get("prompt") or "")
        if not reconcile_tag(code, description, prompt).code:
            return True
    return False


def _history_is_next_priority(lesson, targets: dict[str, set[str]], coverage: dict | None,
                              *, unmatched_misses: bool = False) -> bool:
    """Option B: prior standards become primary after today's checks are sent."""
    if lesson.error:
        return False
    if lesson.assignment is None:
        return True  # No classroom activity scheduled for this block today.
    if not lesson.complete:
        return False  # No completed work: today's needs are still unknown.
    if unmatched_misses:
        return False  # A bad standard tag must not be interpreted as 'addressed'.
    return not targets or bool(coverage and coverage["clear"])


def _checks_cache_key(lesson, day: date) -> str:
    return f"teacher_today_v229_checks_{lesson.class_record.class_id}_{day.isoformat()}"


def _today_quick_checks(store, lesson, day: date, *, fresh: bool = False) -> list:
    """One short-lived class-scoped read, shared by priorities and results.

    A successful teacher assignment invalidates this entry immediately. The
    explicit Refresh and View Results actions force a new read as well.
    """
    key = _checks_cache_key(lesson, day)
    saved = st.session_state.get(key)
    now = time.monotonic()
    if (not fresh and saved and now - saved["at"] < _CHECK_CACHE_SECONDS):
        return saved["rows"]
    rows = store.list_standard_quick_checks(
        day, day, class_id=lesson.class_record.class_id, include_test=True,
    )
    roster = {str(student.student_id) for student in lesson.students}
    valid = [row for row in rows
             if str(row.student_id) in roster
             and str(row.class_id) == str(lesson.class_record.class_id)]
    st.session_state[key] = {"at": now, "rows": valid}
    return valid


def _render_class_cards(lessons, groupings: dict | None = None) -> object:
    st.markdown("""<style>
    .block-container:has(div[class*="st-key-today_card_"]) {max-width: 1200px;}
    div[class*="st-key-today_card_"] button {
        min-height: 76px;
        border-radius: 12px;
        border-width: 1.5px;
        padding: 11px 13px;
        text-align: left;
    }
    div[class*="st-key-today_card_"] button > div {width: 100%;}
    div[class*="st-key-today_card_"] button [data-has-shortcut] {width: 100%;}
    div[class*="st-key-today_card_"] button [data-testid="stMarkdownContainer"] {
        display: flex; flex-direction: column;
        gap: 3px; width: 100%; align-items: flex-start;
    }
    div[class*="st-key-today_card_"] button p {margin: 0; line-height: 1.32;}
    div[class*="st-key-today_card_"] button p:first-child {font-weight: 650;}
    div[class*="st-key-today_card_"] button p:nth-child(2) {font-size: .87rem; color: #536773;}
    div[class*="st-key-today_card_active"] button {
        border: 2px solid #087968;
        background: #e6f5ef;
        color: #163f36;
    }
    .today-results {display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
        padding: 2px 0 12px; border-bottom: 1px solid #d6dce0; margin-bottom: 4px;}
    .today-result {padding: 0 16px; border-left: 1px solid #d6dce0; min-width: 0;}
    .today-result:first-child {padding-left: 0; border-left: 0;}
    .today-result-label, .today-result-detail {color: #647080; font-size: .88rem;}
    .today-result-value {font-size: 1.65rem; font-weight: 700; line-height: 1.2;
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
        .today-result {padding: 0 10px;}
        .today-result-value {font-size: 1.4rem;}
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

    # Four compact cards across on desktop. Streamlit automatically stacks the
    # columns on small screens; partial final rows retain their column width.
    per_row = 4
    for start in range(0, len(lessons), per_row):
        row = lessons[start:start + per_row]
        cols = st.columns(per_row, gap="small")
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
            st.session_state.pop(_checks_cache_key(lesson, day), None)
            # The database intentionally ignores duplicate assignments so a
            # second click never replaces a student's pending or completed
            # question. Count here means selected recipients, not new rows.
            st.success(f"Quick Check requested for {count} selected student{'s' if count != 1 else ''}. "
                       "Existing checks stay unchanged. Students can reopen the app at their seats.")
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
               f"{len(grouping['unfinished'])} remaining")]
    for slot in (1, 2):
        accuracy = grouping[f"accuracy_q{slot}"]
        value = "—" if accuracy is None else f"{accuracy:.0f}%"
        missed = grouping[f"answered_q{slot}"] - grouping[f"correct_q{slot}"]
        detail = (f"{grouping[f'correct_q{slot}']} correct · {missed} missed"
                  if accuracy is not None else "0 responses")
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
    active_slots = [slot for slot in (1, 2) if grouping[f"q{slot}_support"]]
    columns = st.columns(len(active_slots), gap="small") if active_slots else []
    for index, slot in enumerate(active_slots):
        label = "Spiral Review" if slot == 1 else "Yesterday's Lesson"
        with columns[index]:
            names = grouping[f"q{slot}_support"]
            question = question_for_slot(lesson.assignment, slot)
            code = str(question.get("standard_code") or "").strip()
            description = str(question.get("standard_description") or "").strip()
            title_attr = f' title="{html.escape(description, quote=True)}"' if description else ""
            subtitle = html.escape(f"{label} · {code}" if code else label)
            count = f"{len(names)} student{'s' if len(names) != 1 else ''}"
            st.markdown(
                f'<div class="today-question-panel" role="group" aria-label="Missed Q{slot}">'
                f'<div class="today-question-heading">Q{slot} needs support · {count}</div>'
                f'<div class="today-question-standard"{title_attr}>{subtitle}</div>'
                f'{_names_html(names)}</div>', unsafe_allow_html=True,
            )
            decision = reconcile_tag(code, description, str(question.get("prompt") or ""))
            target_ids = [str(row.student_id) for row in lesson.rows
                          if int(row.question_slot) == slot
                          and str(row.student_id) in lesson.completed_ids
                          and not bool(row.correct)]
            _worked_with_button(store, lesson, code=decision.code,
                                student_ids=target_ids, day=day,
                                exclude_bank_ids=(str(question.get("bank_question_id") or ""),),
                                key=f"worked_igniter_{lesson.class_record.class_id}_{slot}")

    notes = []
    if both:
        notes.append("Students who missed both are included in each question group.")
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
    if grouping["unfinished"]:
        with st.expander(f"Not finished · {len(grouping['unfinished'])}", expanded=False):
            _render_names(grouping["unfinished"])
            st.caption("Incomplete work is not counted as incorrect.")


def _render_historical_checkins(store, lesson, day: date, *, ready: bool) -> None:
    """Prior standards become the default only after today's groups are clear.

    The older evidence is still one optional click away before then, and is
    never fetched while hidden. The teacher can also tuck it away again, even
    once it becomes the next recommended priority.
    """
    key = f"teacher_today_history_open_{lesson.class_record.class_id}_{day.isoformat()}"
    ready_seen_key = f"teacher_today_history_ready_seen_{lesson.class_record.class_id}_{day.isoformat()}"
    with st.container(key="today_history"):
        # Open once automatically when today's student-standard checks are
        # fully assigned; afterward, respect the teacher's manual preference.
        if ready and not st.session_state.get(ready_seen_key):
            st.session_state[key] = True
            st.session_state[ready_seen_key] = True

        visible = bool(st.session_state.get(key, False))
        label = ("Hide previous missed standards" if visible
                 else "Review previous missed standards (optional)")
        if st.button(label, key=f"toggle_{key}", type="secondary"):
            visible = not visible
            st.session_state[key] = visible
        if not visible:
            return
        st.markdown("##### Previous missed standards")
        st.caption("Based on repeated misses before today. Use these for additional follow-up.")
        _render_historical_rows(store, lesson, day)


def _render_historical_rows(store, lesson, day: date) -> None:
    try:
        recent = recent_mastery_checkins(store, lesson, day)
    except Exception:
        st.caption("Historical check-ins are temporarily unavailable. Refresh to try again.")
        return
    if recent:
        for group in recent:
            code = str(group["code"])
            description = str(group.get("description") or "")
            count = len(group.get("student_ids") or ())
            title = f"{code} · {description}" if description else code
            with st.expander(f"{title} · {count} students", expanded=False):
                _render_names(list(group["names"]))
                _worked_with_button(store, lesson, code=code,
                                    student_ids=list(group.get("student_ids") or []), day=day,
                                    key=f"worked_history_{lesson.class_record.class_id}_{code}")
    else:
        st.caption("No historical standards currently meet the check-in criteria.")


def _quick_check_results_summary(rows, students) -> tuple[dict, list[dict], list[dict]]:
    """Small, teacher-only follow-up summary without additional store reads.

    Excludes former or unrelated class roster entries and never shows an
    unfinished response as incorrect. No identifying information leaves the
    teacher's current session.
    """
    roster = {str(student.student_id): str(student.nickname) for student in students}
    valid = [row for row in rows if str(row.student_id) in roster]
    totals = {"assigned": len(valid), "completed": 0, "correct": 0, "review": 0, "pending": 0}
    by_code: dict[str, dict] = {}
    details = []
    for row in valid:
        code = str(row.standard_code)
        group = by_code.setdefault(code, {"assigned": 0, "completed": 0, "correct": 0, "review": 0, "pending": 0})
        group["assigned"] += 1
        if row.completed_at is None:
            status = "Not answered"
            totals["pending"] += 1
            group["pending"] += 1
        else:
            totals["completed"] += 1
            group["completed"] += 1
            if row.correct:
                totals["correct"] += 1
                group["correct"] += 1
                status = "Correct"
            else:
                totals["review"] += 1
                group["review"] += 1
                status = "Needs review"
        details.append({
            "Student": roster[str(row.student_id)], "Standard": code,
            "Result": status, "Question": str(row.prompt or ""),
        })
    details.sort(key=lambda item: (item["Standard"], item["Student"].casefold()))
    groups = [{"standard": code, **item} for code, item in sorted(by_code.items())]
    return totals, groups, details


def _render_quick_check_results(store, lesson, day: date, *, preloaded=None) -> None:
    """Compact status from a shared read; detail remains teacher-controlled."""
    key = f"show_quick_check_results_{lesson.class_record.class_id}_{day.isoformat()}"
    if preloaded is None:
        if st.button("View small-group check results", key=f"open_{key}", type="secondary"):
            st.session_state[key] = True
        if not st.session_state.get(key):
            return
    try:
        rows = (preloaded if preloaded is not None else
                _today_quick_checks(store, lesson, day, fresh=True))
    except Exception:
        st.caption("Quick Check results are not available yet. Verify the v2.28 database setup.")
        return
    totals, groups, details = _quick_check_results_summary(rows, lesson.students)
    if not totals["assigned"]:
        if preloaded is None:
            st.caption("No small-group Quick Checks were assigned to this class today.")
        return
    st.markdown(f"**Small-group checks** · {totals['completed']}/{totals['assigned']} answered · "
                f"{totals['correct']} correct · {totals['review']} needs review · "
                f"{totals['pending']} pending")
    with st.expander("Check results by standard and student", expanded=False):
        for item in groups:
            st.write(f"**{item['standard']}** · {item['completed']}/{item['assigned']} answered · "
                     f"{item['correct']} correct · {item['review']} needs review")
        st.dataframe(details, hide_index=True, width="stretch")
        st.caption("Mastery labels use each student's four most recent independent checks, "
                   "not a single Quick Check result. See Learning for their current labels.")


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
    title, refresh = st.columns([6, 1], vertical_alignment="center")
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

    force_checks_refresh = bool(st.session_state.get("teacher_refresh_pending"))
    if force_checks_refresh:
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
        _render_historical_checkins(store, selected, day, ready=False)
        return

    if selected.assignment is None:
        st.info("No Igniter or Friday Quiz is published for this class today.")

    if grouping is not None:
        if grouping["completed_count"]:
            _render_igniter_priorities(store, selected, grouping, day)
        else:
            st.markdown("#### Who to pull today")
            st.caption("Groups appear after students finish both questions. "
                       "Unfinished work is not counted as incorrect."
                       if selected.total else "No active students in this class.")
            if grouping["unfinished"]:
                st.markdown(f"**Not finished · {len(grouping['unfinished'])}**")
                _render_names(grouping["unfinished"])
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

    if selected.kind == "Quiz" and selected.complete:
        st.caption(f"{selected.complete} of {selected.total} students finished the Friday Quiz.")

    # 'Today's groups addressed' means every student who missed a *tagged*
    # standard has a Quick Check assigned for that same code and school date.
    # Pending responses still count as assigned, but partial subsets do not.
    targets = _today_standard_targets(selected, grouping)
    unmatched_misses = _today_has_unmatched_misses(selected)
    today_checks = None
    coverage = None
    if targets:
        try:
            today_checks = _today_quick_checks(
                store, selected, day, fresh=force_checks_refresh,
            )
            coverage = _today_followup_coverage(selected, targets, today_checks)
        except Exception:
            st.caption("Could not verify which follow-ups have been assigned. "
                       "Previous standards remain available on request.")
    if coverage and coverage["assigned"]:
        if coverage["clear"]:
            st.caption(f"Today's follow-ups · all {coverage['required']} "
                       "student-standard checks assigned.")
        else:
            st.caption(f"Today's follow-ups · {coverage['assigned']}/{coverage['required']} "
                       "student-standard checks assigned; finish the remaining groups first.")
    if unmatched_misses:
        st.warning("Some incorrect answers could not be matched to a valid Indiana standard. "
                   "Check the published question's standard before treating today's groups as addressed.")

    _render_quick_check_results(store, selected, day, preloaded=today_checks)
    ready_for_history = _history_is_next_priority(
        selected, targets, coverage, unmatched_misses=unmatched_misses,
    )
    _render_historical_checkins(store, selected, day, ready=ready_for_history)
