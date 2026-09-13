from __future__ import annotations

"""Teacher-only Quiz of the Week builder, results, and anonymous export."""

from collections import defaultdict
from datetime import date, timedelta
import csv
import io

import pandas as pd
import streamlit as st

from fact_engine import current_daily_date
from supabase_fact_store import SupabaseFactStore
from weekly_quiz import (
    QUIZ_CATEGORIES,
    QUIZ_QUESTION_COUNT,
    QUIZ_QUESTION_TYPES,
    prepare_quiz_question,
    skyward_score,
    student_export_key,
)


def _next_or_same_friday(value: date) -> date:
    return value + timedelta(days=(4 - value.weekday()) % 7)


def _lines(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _default_assignment_name(target: date) -> str:
    return f"Quiz of the Week - {target.strftime('%b %d').replace(' 0', ' ')}"


def _blank_question(slot: int) -> dict:
    return {
        "slot": slot,
        "prompt": "",
        "question_type": "Number",
        "correct_answer": "",
        "accepted_answers": [],
        "options": [],
        "label_options": [],
        "correct_label": "",
    }


def _question_editor(existing: dict, slot: int, prefix: str) -> dict:
    st.markdown(f"#### Question {slot}")
    prompt = st.text_area(
        "Question", value=str(existing.get("prompt") or ""),
        key=f"{prefix}_prompt_{slot}", height=88,
    )
    current_type = str(existing.get("question_type") or "Number")
    if current_type not in QUIZ_QUESTION_TYPES:
        current_type = "Number"
    qtype = st.selectbox(
        "Answer type", list(QUIZ_QUESTION_TYPES),
        index=list(QUIZ_QUESTION_TYPES).index(current_type),
        key=f"{prefix}_type_{slot}",
    )

    correct = st.text_input(
        "Correct answer", value=str(existing.get("correct_answer") or ""),
        key=f"{prefix}_correct_{slot}",
        help="For numeric questions, equivalent values are graded mathematically. Example: 3 and 3.0 match; 3/4 and 6/8 match.",
    )
    alternates = ""
    options = ""
    labels = ""
    correct_label = ""

    if qtype == "Multiple choice":
        options = st.text_area(
            "Choices — one per line", value="\n".join(str(item) for item in (existing.get("options") or [])),
            key=f"{prefix}_options_{slot}", height=90,
        )
        st.caption("Type the correct answer above exactly as it appears in the choices.")
    else:
        alternates = st.text_area(
            "Accepted alternate answers — optional, one per line",
            value="\n".join(str(item) for item in (existing.get("accepted_answers") or [])),
            key=f"{prefix}_alternates_{slot}", height=64,
        )
        if qtype == "Fraction":
            st.caption("Students can type fractions and mixed numbers, such as 3/4 or 2 1/3. Equivalent values are accepted.")
        if qtype == "Number + Label":
            labels = st.text_area(
                "Label / unit choices — one per line",
                value="\n".join(str(item) for item in (existing.get("label_options") or [])),
                key=f"{prefix}_labels_{slot}", height=82,
                placeholder="feet\nsquare feet\nyards\nsquare yards",
            )
            correct_label = st.text_input(
                "Correct label / unit", value=str(existing.get("correct_label") or ""),
                key=f"{prefix}_correct_label_{slot}",
            )
            st.caption("The question counts correct only when both the numerical answer and label are correct.")

    return {
        "prompt": prompt,
        "question_type": qtype,
        "correct_answer": correct,
        "accepted_answers": _lines(alternates),
        "options": _lines(options),
        "label_options": _lines(labels),
        "correct_label": correct_label,
    }


def _csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return out.getvalue().encode("utf-8-sig")


def _render_builder(store: SupabaseFactStore, classes) -> None:
    st.markdown("### Build Friday's Quiz")
    st.caption("Exactly 5 questions. Saving here does not change Daily 10, practice, Mystery, or Monday–Thursday Igniters.")

    target = st.date_input(
        "Friday quiz date", value=_next_or_same_friday(current_daily_date()),
        key="weekly_quiz_builder_date",
    )
    if target.weekday() != 4:
        st.warning("Quiz of the Week is a Friday feature. Choose a Friday date to save it.")

    by_name = {item.class_name: item for item in classes}
    source_name = st.selectbox("Build / edit from class", list(by_name), key=f"weekly_quiz_source_{target}")
    source = by_name[source_name]
    try:
        existing = store.get_weekly_quiz_set(source.class_id, target)
    except Exception as exc:
        st.error("The saved quiz could not be loaded.")
        if str(st.query_params.get("dbcheck", "0")) == "1": st.exception(exc)
        return

    prefix = f"weekly_quiz_builder_{target.isoformat()}_{source.class_id}"
    default_name = existing.assignment_name if existing else _default_assignment_name(target)
    assignment_name = st.text_input("Skyward assignment name", value=default_name, key=f"{prefix}_assignment")
    category_options = ["SUMM — Summative", "FORM — Formative"]
    existing_category = existing.category_code if existing else "SUMM"
    category_display = st.selectbox(
        "Skyward category", category_options,
        index=0 if existing_category == "SUMM" else 1,
        key=f"{prefix}_category",
    )
    category_code = category_display.split(" ", 1)[0]
    max_score = st.number_input(
        "Skyward max score", min_value=1.0, max_value=100.0,
        value=float(existing.max_score if existing else 5), step=1.0,
        key=f"{prefix}_max_score",
        help="Five questions are equally weighted. If Max Score is 10, a 4/5 becomes 8/10 in the anonymous export.",
    )

    existing_questions = list(existing.questions) if existing else [_blank_question(i) for i in range(1, 6)]
    edited = []
    for slot in range(1, QUIZ_QUESTION_COUNT + 1):
        with st.container(border=True):
            edited.append(_question_editor(dict(existing_questions[slot - 1]), slot, prefix))

    target_names = st.multiselect(
        "Save this same quiz to", list(by_name), default=[source_name],
        key=f"{prefix}_targets",
        help="Useful when two blocks take the same Quiz of the Week.",
    )
    st.caption("A class becomes locked as soon as a real student answers its quiz. Test Student responses do not lock it.")

    left, right = st.columns([2, 1])
    with left:
        save = st.button("Save Quiz of the Week", type="primary", use_container_width=True, key=f"{prefix}_save")
    with right:
        delete = st.button("Delete from this class", use_container_width=True, key=f"{prefix}_delete", disabled=existing is None)

    if save:
        if target.weekday() != 4:
            st.error("Choose a Friday before saving.")
            return
        if not target_names:
            st.error("Choose at least one class.")
            return
        try:
            prepared = [
                prepare_quiz_question(
                    slot=index,
                    prompt=item["prompt"],
                    question_type=item["question_type"],
                    correct_answer=item["correct_answer"],
                    options=item.get("options") or (),
                    accepted_answers=item.get("accepted_answers") or (),
                    label_options=item.get("label_options") or (),
                    correct_label=item.get("correct_label") or "",
                )
                for index, item in enumerate(edited, start=1)
            ]
            store.save_weekly_quiz_sets_bulk(
                [by_name[name].class_id for name in target_names], target,
                assignment_name=assignment_name,
                category_code=category_code,
                max_score=max_score,
                questions=prepared,
            )
            st.success(f"Quiz saved for {len(target_names)} class{'es' if len(target_names) != 1 else ''}.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if delete and existing is not None:
        try:
            store.delete_weekly_quiz_set(source.class_id, target)
            st.success("Quiz removed from this class.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if existing is not None:
        locked = store.weekly_quiz_locked(existing.quiz_id)
        with st.expander("Student preview · answers hidden", expanded=False):
            for index, question in enumerate(existing.questions, start=1):
                st.markdown(f"**{index}. {question.get('prompt', '')}**")
                st.caption(str(question.get("question_type") or "Number"))
                if str(question.get("question_type")) == "Multiple choice":
                    st.write(" · ".join(str(item) for item in (question.get("options") or [])))
                elif str(question.get("question_type")) == "Number + Label":
                    st.write("Label choices: " + " · ".join(str(item) for item in (question.get("label_options") or [])))
            st.caption("This preview never records an answer.")
        if locked:
            st.info("🔒 This class's quiz is locked because at least one real student has started it.")


def _result_rows(store: SupabaseFactStore, class_record, quiz):
    students = store.list_students(class_record.class_id, include_test=False)
    answers = store.list_weekly_quiz_answers(quiz.quiz_id)
    by_student = defaultdict(list)
    for row in answers:
        by_student[str(row.student_id)].append(row)
    rows = []
    for student in students:
        student_answers = by_student.get(str(student.student_id), [])
        slots = {int(item.question_slot) for item in student_answers}
        completed = len(slots) >= QUIZ_QUESTION_COUNT
        correct_count = sum(bool(item.correct) for item in student_answers if int(item.question_slot) in range(1, 6))
        rows.append({
            "student": student,
            "answers": student_answers,
            "completed": completed,
            "correct_count": correct_count,
            "score": skyward_score(correct_count, quiz.max_score) if completed else None,
        })
    return rows


def _render_results(store: SupabaseFactStore, classes) -> None:
    st.markdown("### Results & Anonymous Skyward Bridge")
    st.caption("The app export contains no first name, last name, Skyward number, or roster file. Your private local workbook performs the identity match.")
    target = st.date_input("Quiz date", value=_next_or_same_friday(current_daily_date()), key="weekly_quiz_results_date")
    by_name = {item.class_name: item for item in classes}
    class_name = st.selectbox("Class", list(by_name), key=f"weekly_quiz_results_class_{target}")
    class_record = by_name[class_name]
    try:
        quiz = store.get_weekly_quiz_set(class_record.class_id, target)
    except Exception as exc:
        st.error("Quiz results could not load.")
        if str(st.query_params.get("dbcheck", "0")) == "1": st.exception(exc)
        return
    if quiz is None:
        st.info("No Quiz of the Week is saved for this class and date.")
        return

    rows = _result_rows(store, class_record, quiz)
    completed = [row for row in rows if row["completed"]]
    avg = (sum(row["correct_count"] for row in completed) / len(completed)) if completed else None
    a, b, c = st.columns(3)
    a.metric("Finished", f"{len(completed)}/{len(rows)}")
    b.metric("Average", "—" if avg is None else f"{avg:.1f}/5")
    c.metric("Skyward max", f"{quiz.max_score:g}")
    st.caption(f"**{quiz.assignment_name}** · {quiz.category_code} · due {target.strftime('%m/%d/%Y')}")

    display_rows = []
    for row in rows:
        student = row["student"]
        display_rows.append({
            "Nickname": student.nickname,
            "Student Key": student_export_key(student.student_id),
            "Status": "Complete" if row["completed"] else f"{len(row['answers'])}/5 answered",
            "Raw Score": f"{row['correct_count']}/5" if row["completed"] else "—",
            "Skyward Score": row["score"] if row["completed"] else "",
        })
    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

    st.markdown("#### Question check")
    answer_rows = store.list_weekly_quiz_answers(quiz.quiz_id)
    for slot in range(1, QUIZ_QUESTION_COUNT + 1):
        slot_rows = [row for row in answer_rows if int(row.question_slot) == slot]
        correct = sum(bool(row.correct) for row in slot_rows)
        qtype = str(quiz.questions[slot - 1].get("question_type") or "Number")
        text = f"Q{slot} · {qtype} · {correct}/{len(slot_rows)} correct" if slot_rows else f"Q{slot} · {qtype} · no responses yet"
        if qtype == "Number + Label" and slot_rows:
            number_ok = sum(bool(row.number_correct) for row in slot_rows)
            label_ok = sum(bool(row.label_correct) for row in slot_rows)
            text += f" · number {number_ok}/{len(slot_rows)} · label {label_ok}/{len(slot_rows)}"
        st.caption(text)

    export_rows = []
    for row in completed:
        student = row["student"]
        export_rows.append({
            "Student Key": student_export_key(student.student_id),
            "Assignment Name": quiz.assignment_name,
            "Due Date": target.strftime("%m%d%Y"),
            "Category": quiz.category_code,
            "Max Score": int(quiz.max_score) if float(quiz.max_score).is_integer() else quiz.max_score,
            "Score": row["score"],
        })
    columns = ["Student Key", "Assignment Name", "Due Date", "Category", "Max Score", "Score"]
    if export_rows:
        st.download_button(
            "⬇ Download anonymous quiz scores",
            data=_csv_bytes(export_rows, columns),
            file_name=f"Quiz_of_the_Week_{target.isoformat()}_{class_record.class_name.replace(' ', '_')}_ANONYMOUS.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )
        st.caption("Only completed quizzes are exported. Unfinished/absent students are omitted rather than assigned a zero.")
    else:
        st.info("No completed student quizzes are ready to export yet.")


def _render_student_keys(store: SupabaseFactStore, classes) -> None:
    st.markdown("### Local Student Keys")
    st.caption("One-time setup for your private workbook. These keys are random-looking and permanent for the existing app account. Do not put real names or Skyward IDs into this app.")
    by_name = {item.class_name: item for item in classes}
    class_name = st.selectbox("Class", list(by_name), key="weekly_quiz_keys_class")
    class_record = by_name[class_name]
    students = store.list_students(class_record.class_id, include_test=False)
    rows = [{"Nickname": student.nickname, "Student Key": student_export_key(student.student_id)} for student in students]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if rows:
        st.download_button(
            "⬇ Download local key setup file",
            data=_csv_bytes(rows, ["Nickname", "Student Key"]),
            file_name=f"{class_record.class_name.replace(' ', '_')}_Student_Keys_LOCAL_SETUP.csv",
            mime="text/csv",
            use_container_width=True,
        )
    st.warning("Keep the file local. Add real names only in the private Excel bridge on your computer — never upload that completed workbook back into this app or to AI.")


def render_teacher_weekly_quiz(store: SupabaseFactStore) -> None:
    st.markdown("### 📝 Quiz of the Week")
    st.caption("Friday assessment → Daily 10 → normal Friday learning routine → final Weekly Mystery guess")
    classes = store.list_classes()
    if not classes:
        st.info("Create a class first.")
        return
    sections = ["✏️ Build", "📊 Results & Export", "🔑 Student Keys"]
    if st.session_state.get("weekly_quiz_teacher_section") not in sections:
        st.session_state["weekly_quiz_teacher_section"] = "✏️ Build"
    section = st.radio(
        "Quiz tools", sections, horizontal=True, label_visibility="collapsed",
        key="weekly_quiz_teacher_section",
    )
    if section == "✏️ Build":
        _render_builder(store, classes)
    elif section == "📊 Results & Export":
        _render_results(store, classes)
    else:
        _render_student_keys(store, classes)
