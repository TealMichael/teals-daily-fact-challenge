from __future__ import annotations

"""Teacher Igniter planning/results UI.

Extracted from app.py during the v2.11.2 foundation pass. Keeping this
workflow isolated reduces the chance that student Daily or unrelated teacher
pages drift when Igniter planning/email features change.
"""

from datetime import date, timedelta
import re
from urllib.parse import urlencode, quote

import pandas as pd
import streamlit as st

from fact_engine import current_daily_date
from fact_store import FactStoreError
from supabase_fact_store import SupabaseFactStore
from warmup import QUESTION_TYPES, display_student_response, prepare_question as prepare_warmup_question, question_for_slot
from teacher_planning import (
    copy_warmup_set as _copy_warmup_set,
    previous_school_day as _previous_school_day,
    save_warmup_template as _save_warmup_template,
    warmup_templates as _warmup_templates,
)
from indiana_math_standards import (
    BY_CODE as INDIANA_STANDARD_BY_CODE,
    CUSTOM_CODE as CUSTOM_STANDARD_CODE,
    display_label as indiana_standard_display_label,
    grade_from_standard_code, ordered_standard_codes, standard_by_code,
)

def _next_school_day(value: date) -> date:
    result = value + timedelta(days=1)
    while result.weekday() >= 5:
        result += timedelta(days=1)
    return result


def _render_warmup_student_preview(warmup) -> None:
    st.caption("Student preview. Correct answers stay hidden.")
    for slot, question in ((1, warmup.question_one), (2, warmup.question_two)):
        label = "Spiral Review" if slot == 1 else "Yesterday Check"
        st.markdown(f"**{slot}. {label}**")
        st.write(str(question.get("prompt") or ""))
        qtype = str(question.get("question_type") or "Short answer")
        st.caption(f"Answer type: {qtype}")
        if qtype == "Multiple choice":
            options = list(question.get("options") or [])
            if options:
                st.write(" · ".join(str(option) for option in options))
        elif qtype == "Multi-Part — 2 answers":
            st.caption("Students see two answer boxes.")



def _lines(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _app_setting(store: SupabaseFactStore, key: str, default=None):
    """Read a private app setting across both production and in-memory stores."""
    try:
        value = store.get_app_setting(key)
    except TypeError:
        value = store.get_app_setting(key, default)
    return default if value is None else value


def _recent_warmup_standards(store: SupabaseFactStore) -> list[str]:
    value = _app_setting(store, "warmup_recent_standards", [])
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for code in value:
        code = str(code or "").strip()
        if code in INDIANA_STANDARD_BY_CODE and code not in result:
            result.append(code)
    return result[:8]


def _remember_warmup_standards(store: SupabaseFactStore, codes) -> None:
    existing = _recent_warmup_standards(store)
    combined = []
    for code in list(codes or ()) + existing:
        code = str(code or "").strip()
        if code in INDIANA_STANDARD_BY_CODE and code not in combined:
            combined.append(code)
    store.set_app_setting("warmup_recent_standards", combined[:8])


def _remember_warmup_standards_safely(store: SupabaseFactStore, codes) -> bool:
    """Best-effort convenience write; core Igniter saves must not depend on it."""
    try:
        _remember_warmup_standards(store, codes)
        return True
    except Exception as exc:
        print(f"[TDFC teacher] recent_standards_save_failed type={type(exc).__name__}")
        return False


def _warmup_form_question(existing: dict, slot: int, key_prefix: str, recent_codes=()) -> dict:
    label = "Spiral Review" if slot == 1 else "Yesterday Check"
    st.markdown(f"#### {slot}. {label}")
    prompt = st.text_area(
        "Question", value=str(existing.get("prompt") or ""),
        key=f"{key_prefix}_prompt_{slot}", height=90,
    )
    current_type = str(existing.get("question_type") or "Short answer")
    qtype = st.selectbox(
        "Answer type", list(QUESTION_TYPES),
        index=list(QUESTION_TYPES).index(current_type) if current_type in QUESTION_TYPES else 0,
        key=f"{key_prefix}_type_{slot}",
    )
    correct_label = "Correct answer — Part 1" if qtype == "Multi-Part — 2 answers" else "Correct answer"
    correct = st.text_input(
        correct_label, value=str(existing.get("correct_answer") or ""),
        key=f"{key_prefix}_correct_{slot}",
    )
    correct_two = ""
    if qtype == "Multi-Part — 2 answers":
        correct_two = st.text_input(
            "Correct answer — Part 2", value=str(existing.get("correct_answer_two") or ""),
            key=f"{key_prefix}_correct_two_{slot}",
        )
    if qtype == "Expanded Form":
        st.caption("Students must show the actual place-value sum. A numerically equal standard-form number will not count.")
    options = ""
    if qtype == "Multiple choice":
        options = st.text_area(
            "Multiple-choice options — one per line",
            value="\n".join(str(value) for value in (existing.get("options") or [])),
            key=f"{key_prefix}_options_{slot}", height=90,
        )
    alternates = st.text_area(
        "Accepted alternate answers — optional, one per line",
        value="\n".join(str(value) for value in (existing.get("accepted_answers") or [])),
        key=f"{key_prefix}_alternates_{slot}", height=70,
    )
    alternates_two = ""
    if qtype == "Multi-Part — 2 answers":
        alternates_two = st.text_area(
            "Accepted Part 2 alternate answers — optional, one per line",
            value="\n".join(str(value) for value in (existing.get("accepted_answers_two") or [])),
            key=f"{key_prefix}_alternates_two_{slot}", height=70,
        )

    recent_codes = [code for code in recent_codes if code in INDIANA_STANDARD_BY_CODE]
    standard_options = ordered_standard_codes(recent_codes) + [CUSTOM_STANDARD_CODE]
    existing_code = str(existing.get("standard_code") or "").strip()
    if existing_code in INDIANA_STANDARD_BY_CODE:
        selected_default = existing_code
    elif existing_code:
        selected_default = CUSTOM_STANDARD_CODE
    elif recent_codes:
        selected_default = recent_codes[0]
    else:
        selected_default = "5.NS.1"
    selected_index = standard_options.index(selected_default) if selected_default in standard_options else 0
    standard_choice = st.selectbox(
        "Indiana Math standard · Grades 4–7",
        standard_options,
        index=selected_index,
        format_func=lambda code: indiana_standard_display_label(code, recent_codes),
        key=f"{key_prefix}_standard_choice_{slot}",
        help="Type a standard code or a skill keyword to search the list.",
    )
    if standard_choice == CUSTOM_STANDARD_CODE:
        standard = st.text_input(
            "Custom standard code", value=existing_code if existing_code not in INDIANA_STANDARD_BY_CODE else "",
            key=f"{key_prefix}_standard_custom_{slot}",
        )
        description = st.text_input(
            "Custom standard description", value=str(existing.get("standard_description") or "") if existing_code not in INDIANA_STANDARD_BY_CODE else "",
            key=f"{key_prefix}_description_custom_{slot}",
        )
    else:
        selected_standard = standard_by_code(standard_choice)
        standard = selected_standard.code
        description = selected_standard.description
        st.caption(f"**{selected_standard.domain}** · {selected_standard.description}")

    return {
        "prompt": prompt, "question_type": qtype, "correct_answer": correct,
        "correct_answer_two": correct_two,
        "options": _lines(options), "accepted_answers": _lines(alternates),
        "accepted_answers_two": _lines(alternates_two),
        "standard_code": standard, "standard_description": description,
    }


def _warmup_name_list(student_ids, name_by_id: dict[str, str]) -> list[str]:
    return sorted(
        [name_by_id[student_id] for student_id in student_ids if student_id in name_by_id],
        key=str.casefold,
    )


def _warmup_instruction_recommendation(miss_count: int) -> str:
    miss_count = int(miss_count or 0)
    if miss_count <= 0:
        return "No reteach group needed from the completed Warm-Ups."
    if miss_count <= 3:
        return "Quick individual check-in."
    if miss_count <= 8:
        return "Good small-group reteach target."
    return "Consider a quick whole-class clarification before small groups."


def _warmup_grouping(students, rows) -> dict:
    """Build actionable groups without treating unfinished work as incorrect."""
    student_ids = {str(student.student_id) for student in students}
    name_by_id = {str(student.student_id): str(student.nickname) for student in students}
    by_slot = {
        1: {str(row.student_id): row for row in rows if int(row.question_slot) == 1 and str(row.student_id) in student_ids},
        2: {str(row.student_id): row for row in rows if int(row.question_slot) == 2 and str(row.student_id) in student_ids},
    }
    completed_ids = set(by_slot[1]) & set(by_slot[2])
    unfinished_ids = student_ids - completed_ids
    q1_wrong_completed = {sid for sid in completed_ids if not bool(by_slot[1][sid].correct)}
    q2_wrong_completed = {sid for sid in completed_ids if not bool(by_slot[2][sid].correct)}
    missed_both_ids = q1_wrong_completed & q2_wrong_completed

    def accuracy(slot: int):
        slot_rows = list(by_slot[slot].values())
        if not slot_rows:
            return None
        return sum(bool(row.correct) for row in slot_rows) / len(slot_rows) * 100

    return {
        "student_count": len(student_ids),
        "completed_count": len(completed_ids),
        "answered_q1": len(by_slot[1]),
        "answered_q2": len(by_slot[2]),
        "accuracy_q1": accuracy(1),
        "accuracy_q2": accuracy(2),
        "correct_q1": sum(bool(row.correct) for row in by_slot[1].values()),
        "correct_q2": sum(bool(row.correct) for row in by_slot[2].values()),
        "missed_both": _warmup_name_list(missed_both_ids, name_by_id),
        "q1_support": _warmup_name_list(q1_wrong_completed, name_by_id),
        "q2_support": _warmup_name_list(q2_wrong_completed, name_by_id),
        "q1_only": _warmup_name_list(q1_wrong_completed - missed_both_ids, name_by_id),
        "q2_only": _warmup_name_list(q2_wrong_completed - missed_both_ids, name_by_id),
        "unfinished": _warmup_name_list(unfinished_ids, name_by_id),
        "completed_ids": completed_ids,
    }


def _warmup_class_snapshot(store: SupabaseFactStore, class_record, target_date: date, warmup):
    students = store.list_students(class_record.class_id)
    student_ids = {student.student_id for student in students}
    rows = [
        row for row in store.list_warmup_answers(target_date, target_date, class_id=class_record.class_id)
        if row.student_id in student_ids
    ]
    grouping = _warmup_grouping(students, rows)
    c1, c2, c3 = st.columns(3)
    c1.metric("Warm-Up finished", f"{grouping['completed_count']}/{grouping['student_count']}")
    c2.metric("Q1 accuracy", "—" if grouping["accuracy_q1"] is None else f"{grouping['accuracy_q1']:.0f}%")
    c3.metric("Q2 accuracy", "—" if grouping["accuracy_q2"] is None else f"{grouping['accuracy_q2']:.0f}%")

    for slot in (1, 2):
        question = question_for_slot(warmup, slot)
        accuracy = grouping[f"accuracy_q{slot}"]
        answered = grouping[f"answered_q{slot}"]
        st.markdown(f"**Q{slot} · {question.get('teacher_label', '')} · {question.get('standard_code', '')}**")
        if question.get("standard_description"):
            st.caption(str(question.get("standard_description")))
        st.caption(str(question.get("prompt") or ""))
        if accuracy is None:
            st.caption("No responses yet.")
        else:
            st.caption(f"{accuracy:.0f}% correct from {answered} response{'s' if answered != 1 else ''}.")
    return students, rows, grouping


def _warmup_email_setting_key(class_id: str) -> str:
    return f"warmup_email_secondary::{class_id}"


def _valid_email(value: str) -> bool:
    value = str(value or "").strip()
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


def _warmup_email_recipients(store: SupabaseFactStore, class_id: str) -> tuple[str, str]:
    primary = str(_app_setting(store, "warmup_email_primary", "") or "").strip()
    secondary = str(_app_setting(store, _warmup_email_setting_key(class_id), "") or "").strip()
    return primary, secondary


def _render_warmup_email_settings(store: SupabaseFactStore, class_record, key_prefix: str) -> None:
    primary, secondary = _warmup_email_recipients(store, class_record.class_id)
    with st.expander("📧 Email recipients", expanded=not bool(primary)):
        st.caption("Your address is used for every class. Add a push-in teacher only for the class that needs one.")
        with st.form(f"{key_prefix}_email_settings_form"):
            primary_input = st.text_input(
                "My school email · every class", value=primary,
                key=f"{key_prefix}_primary_email", placeholder="you@school.org",
            )
            secondary_input = st.text_input(
                f"Push-in teacher for {class_record.class_name} · optional", value=secondary,
                key=f"{key_prefix}_secondary_email", placeholder="Leave blank for classes without push-in support",
            )
            save_settings = st.form_submit_button("Save email recipients", use_container_width=True)
        if save_settings:
            primary_clean = primary_input.strip()
            secondary_clean = secondary_input.strip()
            if not _valid_email(primary_clean):
                st.error("Enter a valid school email for yourself.")
            elif secondary_clean and not _valid_email(secondary_clean):
                st.error("The push-in teacher email does not look valid.")
            else:
                store.set_app_setting("warmup_email_primary", primary_clean)
                if secondary_clean:
                    store.set_app_setting(_warmup_email_setting_key(class_record.class_id), secondary_clean)
                else:
                    store.delete_app_setting(_warmup_email_setting_key(class_record.class_id))
                st.success("Warm-Up email recipients saved.")
                st.rerun()


def _warmup_report_text(class_record, target_date: date, warmup, grouping: dict) -> str:
    q1 = question_for_slot(warmup, 1)
    q2 = question_for_slot(warmup, 2)

    def pull_line(names) -> str:
        return ", ".join(names) if names else "None"

    def clean_question_text(value) -> str:
        text = str(value or "").replace("**", "").replace("__", "").replace("`", "")
        return " ".join(text.split())

    lines = [
        f"Warm-Up Results — {class_record.class_name}",
        target_date.strftime("%A, %B %d, %Y"),
        f"Completed: {grouping['completed_count']}/{grouping['student_count']}",
        "",
        "QUESTION 1 — SPIRAL REVIEW",
        f"Standard: {q1.get('standard_code', '')}",
        f"Question: {clean_question_text(q1.get('prompt', ''))}",
        "Students to pull: " + pull_line(grouping["q1_support"]),
        "",
        "QUESTION 2 — YESTERDAY'S LESSON",
        f"Standard: {q2.get('standard_code', '')}",
        f"Question: {clean_question_text(q2.get('prompt', ''))}",
        "Students to pull: " + pull_line(grouping["q2_support"]),
        "",
        "PRIORITY GROUP — MISSED BOTH",
        pull_line(grouping["missed_both"]),
        "",
        "HAVE NOT FINISHED YET",
        pull_line(grouping["unfinished"]),
    ]
    if grouping["unfinished"]:
        lines.extend([
            "",
            "Please check in with these students. They are not counted as incorrect until they finish the Warm-Up.",
        ])
    return "\n".join(lines)


def _warmup_outlook_url(primary: str, secondary: str, subject: str, body: str) -> str:
    params = {"to": primary, "subject": subject, "body": body}
    if secondary:
        params["cc"] = secondary
    return "https://outlook.office.com/mail/deeplink/compose?" + urlencode(params, quote_via=quote)


def _render_warmup_groups_and_email(
    store: SupabaseFactStore, class_record, target_date: date, warmup, rows, students, *, key_prefix: str,
) -> None:
    grouping = _warmup_grouping(students, rows)
    q1 = question_for_slot(warmup, 1)
    q2 = question_for_slot(warmup, 2)

    st.markdown("##### 🎯 Small groups from current results")
    if grouping["missed_both"]:
        st.warning("**Priority · missed both:** " + ", ".join(grouping["missed_both"]))
    else:
        st.caption("Priority group: no student who has finished both questions missed both.")

    left, right = st.columns(2)
    with left:
        st.markdown(f"**🔁 Spiral · {q1.get('standard_code', '')}**")
        st.caption(_warmup_instruction_recommendation(len(grouping["q1_support"])))
        st.write(", ".join(grouping["q1_support"]) if grouping["q1_support"] else "No completed-student misses yet.")
    with right:
        st.markdown(f"**📚 Yesterday · {q2.get('standard_code', '')}**")
        st.caption(_warmup_instruction_recommendation(len(grouping["q2_support"])))
        st.write(", ".join(grouping["q2_support"]) if grouping["q2_support"] else "No completed-student misses yet.")

    if grouping["unfinished"]:
        st.info("**⚠️ Not finished yet:** " + ", ".join(grouping["unfinished"]) + "\n\nThese students didn't finish, so please check in with them!")
    else:
        st.success("Everyone has finished both Warm-Up questions.")
    st.caption("Unfinished work stays separate from incorrect work. Small groups use students who completed both questions.")

    _render_warmup_email_settings(store, class_record, key_prefix)
    primary, secondary = _warmup_email_recipients(store, class_record.class_id)
    prepare_key = f"{key_prefix}_email_ready"
    if st.button("📧 Prepare Warm-Up Email", use_container_width=True, type="primary", key=f"{key_prefix}_prepare_email"):
        st.session_state[prepare_key] = True
    if st.session_state.get(prepare_key):
        if not primary:
            st.warning("Save your school email above before preparing the Outlook draft.")
        elif not any(int(row.question_slot) in (1, 2) for row in rows):
            st.info("No student Warm-Up responses are available yet.")
        else:
            report = _warmup_report_text(class_record, target_date, warmup, grouping)
            subject = f"Warm-Up Results — {class_record.class_name} — {target_date.strftime('%b %d')}"
            recipients = primary + (f" · CC: {secondary}" if secondary else "")
            st.caption(f"Draft recipient: {recipients}")
            with st.expander("Preview email", expanded=True):
                st.code(report, language=None)
            st.link_button(
                "📨 Open this draft in Outlook",
                _warmup_outlook_url(primary, secondary, subject, report),
                use_container_width=True,
                type="primary",
            )
            st.caption("Nothing is sent automatically. Outlook opens the draft so you can review it and press Send.")


def _warmup_export_frame(store: SupabaseFactStore, start_date: date, end_date: date, class_id: str | None) -> pd.DataFrame:
    rows = store.list_warmup_answers(start_date, end_date, class_id=class_id, include_test=False)
    classes = store.list_classes(include_inactive=True)
    class_names = {item.class_id: item.class_name for item in classes}
    student_names: dict[str, str] = {}
    for class_record in classes:
        for student in store.list_students(class_record.class_id, include_inactive=True, include_test=False):
            student_names[student.student_id] = student.nickname
    data = []
    for row in rows:
        data.append({
            "Date": row.warmup_date,
            "Class": class_names.get(row.class_id, row.class_id),
            "Nickname": student_names.get(row.student_id, "Student"),
            "Question": "Spiral Review" if row.question_slot == 1 else "Yesterday Check",
            "Question Type": row.question_type,
            "Grade": grade_from_standard_code(row.standard_code) or "",
            "Indiana Standard": row.standard_code,
            "Standard Description": row.standard_description,
            "Prompt": row.prompt,
            "Student Answer": row.student_answer,
            "Correct Answer": row.correct_answer,
            "Correct": "Yes" if row.correct else "No",
            "Answered At": row.answered_at.isoformat(),
        })
    return pd.DataFrame(data, columns=[
        "Date", "Class", "Nickname", "Question", "Question Type", "Grade", "Indiana Standard",
        "Standard Description", "Prompt", "Student Answer", "Correct Answer", "Correct", "Answered At",
    ])


def render_teacher_warmup(store: SupabaseFactStore, *, refresh_control, finish_refresh) -> None:
    header_left, header_right = st.columns([4.2, 1.4])
    with header_left:
        st.markdown("### 🧠 Warm-Up")
        st.caption("Two untimed curriculum questions before the Daily 10.")
    with header_right:
        refresh_control(key="teacher_warmup_refresh")
    today = current_daily_date()
    retention_key = f"warmup_raw_response_retention::{today.isoformat()}"
    if not st.session_state.get(retention_key):
        try:
            store.clear_old_warmup_response_text(today)
            st.session_state[retention_key] = True
        except Exception as exc:
            print(f"[TDFC teacher] warmup_response_retention_failed type={type(exc).__name__}")
    classes = store.list_classes()
    if not classes:
        st.info("Create a class first.")
        return
    class_by_name = {item.class_name: item for item in classes}
    selected_name = st.selectbox("Class", list(class_by_name), key="teacher_warmup_class")
    selected = class_by_name[selected_name]

    default_date = current_daily_date()
    target_date = st.date_input("Warm-Up date", value=default_date, key="teacher_warmup_date")
    st.caption("To preview a Warm-Up, choose today's date, save it, then open 🧪 Test Student.")

    existing = store.get_warmup_set(selected.class_id, target_date)
    locked = bool(existing and store.warmup_set_locked(existing.warmup_set_id))
    if locked:
        st.info("🔒 This Warm-Up is locked because a student has already answered it, so everyone sees the same questions.")

    with st.expander("⚡ Planning shortcuts", expanded=False):
        previous_date = _previous_school_day(target_date)
        try:
            previous = store.get_warmup_set(selected.class_id, previous_date)
        except Exception:
            previous = None
        previous_label = previous_date.strftime("%A, %B %d").replace(" 0", " ")
        if previous is None:
            st.caption(f"No Warm-Up is saved for the previous school day ({previous_label}).")
        else:
            previous_action = "Replace with previous school day" if existing else "Use previous school day's Warm-Up"
            if st.button(previous_action, use_container_width=True, disabled=locked, key=f"warmup_previous_{selected.class_id}_{target_date}"):
                try:
                    _copy_warmup_set(store, source=previous, target_class_id=selected.class_id, target_date=target_date)
                    st.success(f"Copied {previous_label} into this date.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        if existing is not None:
            st.markdown("**Reuse this Warm-Up**")
            reuse_a, reuse_b = st.columns(2)
            next_week_date = target_date + timedelta(days=7)
            with reuse_a:
                if st.button("Reuse next week", use_container_width=True, key=f"warmup_reuse_week_{selected.class_id}_{target_date}"):
                    try:
                        _copy_warmup_set(store, source=existing, target_class_id=selected.class_id, target_date=next_week_date)
                        st.success(f"Copied to {next_week_date.strftime('%A, %B %d').replace(' 0', ' ')}.")
                    except Exception as exc:
                        st.error(str(exc))
            with reuse_b:
                other_classes = [item for item in classes if item.class_id != selected.class_id]
                if other_classes:
                    target_by_name = {item.class_name: item for item in other_classes}
                    target_name = st.selectbox("Copy to class", list(target_by_name), key=f"warmup_copy_class_{selected.class_id}_{target_date}")
                    if st.button("Copy to selected class", use_container_width=True, key=f"warmup_copy_class_button_{selected.class_id}_{target_date}"):
                        try:
                            _copy_warmup_set(store, source=existing, target_class_id=target_by_name[target_name].class_id, target_date=target_date)
                            st.success(f"Copied to {target_name} for the same date.")
                        except Exception as exc:
                            st.error(str(exc))

            st.markdown("**Templates**")
            template_name = st.text_input("Template name", placeholder="e.g. Decimal division check", key=f"warmup_template_name_{selected.class_id}_{target_date}")
            if st.button("Save this Warm-Up as a template", use_container_width=True, key=f"warmup_template_save_{selected.class_id}_{target_date}"):
                try:
                    _save_warmup_template(store, template_name, existing.question_one, existing.question_two)
                    st.success("Warm-Up template saved.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            with st.expander("👀 Preview student view", expanded=False):
                _render_warmup_student_preview(existing)

        templates = _warmup_templates(store)
        if templates:
            template_by_name = {item["name"]: item for item in templates}
            template_choice = st.selectbox("Load a saved template", list(template_by_name), key=f"warmup_template_load_{selected.class_id}_{target_date}")
            if st.button("Use template on this date", use_container_width=True, disabled=locked, key=f"warmup_template_load_button_{selected.class_id}_{target_date}"):
                try:
                    item = template_by_name[template_choice]
                    class _TemplateSource:
                        question_one = item["question_one"]
                        question_two = item["question_two"]
                    _copy_warmup_set(store, source=_TemplateSource(), target_class_id=selected.class_id, target_date=target_date)
                    st.success(f"Loaded template: {template_choice}.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    q1_existing = dict(existing.question_one) if existing else {}
    q2_existing = dict(existing.question_two) if existing else {}
    key_prefix = f"warmup_plan_{selected.class_id}_{target_date.isoformat()}"
    recent_standards = _recent_warmup_standards(store)
    st.caption("Indiana Math standards from Grades 4–7 are built in. Type a code or skill word in the standard box to search; recently used standards float to the top.")
    with st.form(f"{key_prefix}_form"):
        q1_values = _warmup_form_question(q1_existing, 1, key_prefix, recent_standards)
        q2_values = _warmup_form_question(q2_existing, 2, key_prefix, recent_standards)
        copy_all = st.checkbox("Also copy this Warm-Up to every class", value=False, key=f"{key_prefix}_copy")
        save = st.form_submit_button("Save Warm-Up", type="primary", use_container_width=True, disabled=locked)
    if save:
        try:
            q1 = prepare_warmup_question(slot=1, **q1_values)
            q2 = prepare_warmup_question(slot=2, **q2_values)
            targets = classes if copy_all else [selected]
            locked_targets = []
            for class_record in targets:
                current = store.get_warmup_set(class_record.class_id, target_date)
                if current is not None and store.warmup_set_locked(current.warmup_set_id):
                    locked_targets.append(class_record.class_name)
            if locked_targets:
                raise FactStoreError("Cannot copy over a Warm-Up that students already started: " + ", ".join(locked_targets))
            for class_record in targets:
                store.save_warmup_set(class_record.class_id, target_date, q1, q2)

            # Remembering recent standards is only a teacher convenience. A failure
            # here must never make a successfully saved Igniter look like it failed.
            _remember_warmup_standards_safely(store, [q1.get("standard_code"), q2.get("standard_code")])

            st.success("Warm-Up saved" + (" for all classes." if copy_all else f" for {selected.class_name}."))
            st.rerun()
        except (ValueError, FactStoreError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error("The Warm-Up could not be saved.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)

    if existing and not locked:
        if st.button("Remove this Warm-Up", use_container_width=True, key=f"remove_{key_prefix}"):
            try:
                store.delete_warmup_set(selected.class_id, target_date)
                st.success("Warm-Up removed for this class/date.")
                st.rerun()
            except FactStoreError as exc:
                st.error(str(exc))

    if existing:
        st.markdown("#### Class results")
        result_students, result_rows, _ = _warmup_class_snapshot(store, selected, target_date, existing)
        if target_date == current_daily_date():
            with st.expander("📝 Today's Student Answers", expanded=False):
                st.caption("Today's typed answers are available here. On past dates, accuracy and standards are kept, but typed responses are not.")
                name_by_id = {str(student.student_id): str(student.nickname) for student in result_students}
                by_student = {}
                for row in result_rows:
                    entry = by_student.setdefault(str(row.student_id), {"Nickname": name_by_id.get(str(row.student_id), "Student"), "Q1": "—", "Q2": "—"})
                    entry[f"Q{int(row.question_slot)}"] = display_student_response(row.student_answer, row.question_type)
                if by_student:
                    frame = pd.DataFrame(sorted(by_student.values(), key=lambda item: item["Nickname"].casefold()))
                    st.dataframe(frame, hide_index=True, use_container_width=True)
                else:
                    st.caption("No student answers yet today.")
        # A Warm-Up refresh is only marked complete after the current set and
        # its latest real-student answers have both been read successfully.
        finish_refresh()
        _render_warmup_groups_and_email(
            store, selected, target_date, existing, result_rows, result_students,
            key_prefix=f"teacher_warmup_results_{selected.class_id}_{target_date.isoformat()}",
        )
        test_student = store.get_test_student(selected.class_id)
        if test_student is not None:
            test_rows = store.get_warmup_answers(test_student.student_id, existing.warmup_set_id)
            if test_rows:
                with st.expander("🧪 Test Student Answers", expanded=False):
                    st.caption("These responses are for checking the student view and stay out of class results, groups, email, and downloads.")
                    st.dataframe(pd.DataFrame([
                        {
                            "Question": "Spiral Review" if row.question_slot == 1 else "Yesterday Check",
                            "Answer": display_student_response(row.student_answer, row.question_type),
                            "Correct": "Yes" if row.correct else "No",
                        } for row in test_rows
                    ]), hide_index=True, use_container_width=True)
                    primary_email, _ = _warmup_email_recipients(store, selected.class_id)
                    sandbox_ready_key = f"sandbox_warmup_email_{selected.class_id}_{target_date.isoformat()}"
                    if st.button("🧪 Prepare Test Student Outlook email", key=f"{sandbox_ready_key}_button", use_container_width=True):
                        st.session_state[sandbox_ready_key] = True
                    if st.session_state.get(sandbox_ready_key):
                        if not primary_email:
                            st.warning("Save your school email in the Warm-Up email recipients section first.")
                        else:
                            sandbox_grouping = _warmup_grouping([test_student], test_rows)
                            sandbox_report = "[TEST STUDENT — preview only]\n\n" + _warmup_report_text(
                                selected, target_date, existing, sandbox_grouping
                            )
                            sandbox_subject = f"[TEST STUDENT] Warm-Up Results — {selected.class_name} — {target_date.strftime('%b %d')}"
                            st.code(sandbox_report, language=None)
                            st.link_button(
                                "📨 Open Test Student draft in Outlook",
                                _warmup_outlook_url(primary_email, "", sandbox_subject, sandbox_report),
                                use_container_width=True,
                            )
                            st.caption("Test Student drafts go only to you; the push-in teacher is not included.")
    else:
        finish_refresh()
        st.info("No Warm-Up is assigned for this class/date. Students will go straight to the Daily 10.")

    st.markdown("#### 📥 Weekly Warm-Up Data")
    st.caption("Download weekly Warm-Up results by student and standard. Test Student is not included.")
    if st.toggle("Prepare weekly CSV", key="teacher_warmup_export_ready"):
        today = current_daily_date()
        monday = today - timedelta(days=today.weekday())
        week_start = st.date_input("Week starting", value=monday, key="teacher_warmup_export_week")
        week_start = week_start - timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=4)
        scope_names = ["All classes"] + list(class_by_name)
        scope = st.selectbox("Export", scope_names, key="teacher_warmup_export_scope")
        export_class_id = None if scope == "All classes" else class_by_name[scope].class_id
        frame = _warmup_export_frame(store, week_start, week_end, export_class_id)
        if frame.empty:
            st.info(f"No Warm-Up responses found for {week_start.strftime('%b %d')}–{week_end.strftime('%b %d')}.")
        else:
            summary = frame.assign(CorrectFlag=frame["Correct"].eq("Yes")).groupby("Indiana Standard", as_index=False).agg(
                Responses=("CorrectFlag", "size"), Correct=("CorrectFlag", "sum")
            )
            summary["Accuracy"] = (summary["Correct"] / summary["Responses"] * 100).round(0).astype(int).astype(str) + "%"
            st.dataframe(summary[["Indiana Standard", "Responses", "Correct", "Accuracy"]], hide_index=True, use_container_width=True)
            csv_bytes = frame.to_csv(index=False).encode("utf-8")
            filename = f"warmup_data_{week_start.isoformat()}_to_{week_end.isoformat()}.csv"
            st.download_button("⬇️ Download weekly Warm-Up CSV", data=csv_bytes, file_name=filename, mime="text/csv", use_container_width=True)
