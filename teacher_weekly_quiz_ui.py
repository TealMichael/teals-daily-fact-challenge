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
from teacher_question_editor import render_answer_editor
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
    answer_values = render_answer_editor(
        existing, slot=slot, prefix=prefix,
        question_types=QUIZ_QUESTION_TYPES, default_type="Number",
    )
    return {"prompt": prompt, **answer_values}


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
    # Keep Test Student completely out of real-class item analysis.  A teacher
    # may preview Friday's quiz before students arrive; those sandbox answers
    # must never change the real class percentages shown here.
    all_answer_rows = store.list_weekly_quiz_answers(quiz.quiz_id)
    real_student_ids = {str(row["student"].student_id) for row in rows}
    answer_rows = [row for row in all_answer_rows if str(row.student_id) in real_student_ids]
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

    # Test Student gets a separate verification area.  It is intentionally
    # excluded from Finished/Average, the real Question check above, Student
    # Keys, and the production anonymous Skyward export below.
    test_student = store.get_test_student(class_record.class_id)
    test_rows = [] if test_student is None else [
        row for row in all_answer_rows if str(row.student_id) == str(test_student.student_id)
    ]
    if test_rows:
        test_slots = {int(item.question_slot) for item in test_rows}
        test_completed = len(test_slots) >= QUIZ_QUESTION_COUNT
        test_correct = sum(
            bool(item.correct) for item in test_rows
            if int(item.question_slot) in range(1, QUIZ_QUESTION_COUNT + 1)
        )
        st.markdown("#### 🧪 Test Student verification")
        st.caption("Sandbox only — never included in class averages, real item analysis, Student Keys, or the production Skyward export.")
        t1, t2, t3 = st.columns(3)
        t1.metric("Status", "Complete" if test_completed else f"{len(test_slots)}/5 answered")
        t2.metric("Raw Score", f"{test_correct}/5" if test_completed else "—")
        t3.metric("Skyward Score", skyward_score(test_correct, quiz.max_score) if test_completed else "—")
        if test_completed:
            test_export_rows = [{
                "Student Key": student_export_key(test_student.student_id),
                "Assignment Name": quiz.assignment_name,
                "Due Date": target.strftime("%m%d%Y"),
                "Category": quiz.category_code,
                "Max Score": int(quiz.max_score) if float(quiz.max_score).is_integer() else quiz.max_score,
                "Score": skyward_score(test_correct, quiz.max_score),
            }]
            test_columns = ["Student Key", "Assignment Name", "Due Date", "Category", "Max Score", "Score"]
            st.download_button(
                "⬇ Download TEST anonymous quiz score",
                data=_csv_bytes(test_export_rows, test_columns),
                file_name=f"Quiz_of_the_Week_{target.isoformat()}_{class_record.class_name.replace(' ', '_')}_TEST_ONLY.csv",
                mime="text/csv",
                use_container_width=True,
            )

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
