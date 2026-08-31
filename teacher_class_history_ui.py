from __future__ import annotations

"""Teacher-only date lookup for Daily 10, Warm-Up, and Weekly Mystery history."""

from collections import Counter
from datetime import date
from statistics import median

import pandas as pd
import streamlit as st

from daily_modes import configured_daily_mode
from fact_engine import current_daily_date
from supabase_fact_store import SupabaseFactStore
from ui_helpers import format_seconds
from weekly_mystery import mystery_for_key, school_day_number, week_start_for
from teacher_history import common_multiplication_misses, daily_rows_for_date, rank_daily, warmup_summary



def render_teacher_class_history(store: SupabaseFactStore) -> None:
    st.markdown("### 🗓️ Class History")
    st.caption("Look back at a class on any date.")

    classes = store.list_classes(include_inactive=True)
    if not classes:
        st.info("Create a class first.")
        return
    class_by_name = {item.class_name: item for item in classes}
    c1, c2 = st.columns([1.2, 1])
    with c1:
        class_name = st.selectbox("Class", list(class_by_name), key="teacher_history_class")
    with c2:
        target_date = st.date_input("Date", value=current_daily_date(), key="teacher_history_date")
    selected = class_by_name[class_name]
    students = store.list_students(selected.class_id, include_inactive=True)
    name_by_id = {str(student.student_id): student.nickname for student in students}

    st.markdown("#### Daily 10")
    try:
        history = store.teacher_daily_history(selected.class_id, target_date, target_date, students=students)
    except Exception as exc:
        st.warning("Daily 10 history could not be loaded right now.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        history = []
    daily_rows = daily_rows_for_date(history, target_date)
    configured_mode = configured_daily_mode(store, selected.class_id, target_date)
    if not daily_rows:
        st.caption(f"Daily 10 mode: **{configured_mode}** · No completed Daily 10s were found for this class/date.")
    else:
        modes = Counter(str(row.get("daily_mode") or "Multiplication") for row in daily_rows)
        average = sum(int(row.get("correct_count") or 0) for row in daily_rows) / len(daily_rows)
        times = [float(row["timed_seconds"]) for row in daily_rows if row.get("timed_seconds") is not None]
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Completed", len(daily_rows))
        d2.metric("Average score", f"{average:.1f}/10")
        d3.metric("Median time", "—" if not times else format_seconds(float(median(times))))
        d4.metric("Mode", next(iter(modes)) if len(modes) == 1 else "Mixed history")

        top = rank_daily(daily_rows)
        st.markdown("##### Top 10")
        st.dataframe(pd.DataFrame([
            {
                "Rank": row["rank"],
                "Student": row.get("nickname", "Student"),
                "Score": f"{int(row.get('correct_count') or 0)}/10",
                "Time": "—" if row.get("timed_seconds") is None else format_seconds(float(row["timed_seconds"])),
                "Mode": row.get("daily_mode") or "Multiplication",
            }
            for row in top
        ]), hide_index=True, use_container_width=True)

        misses = common_multiplication_misses(daily_rows)
        st.markdown("##### Common multiplication misses")
        if misses:
            st.dataframe(pd.DataFrame(misses), hide_index=True, use_container_width=True)
        elif any(str(row.get("daily_mode") or "Multiplication") == "Multiplication" for row in daily_rows):
            st.success("No multiplication misses were recorded in the completed attempts for this date.")
        else:
            st.caption("This date used a different Daily 10 mode, so multiplication fact details are not shown.")

    st.markdown("#### Warm-Up")
    try:
        warmup = store.get_warmup_set(selected.class_id, target_date)
        warmup_rows = store.list_warmup_answers(target_date, target_date, class_id=selected.class_id)
    except Exception as exc:
        warmup = None
        warmup_rows = []
        st.warning("Warm-Up history could not be loaded right now.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
    if warmup is None:
        st.caption("No Warm-Up was saved for this class/date.")
    else:
        summary = warmup_summary(students, warmup_rows)
        w1, w2, w3 = st.columns(3)
        w1.metric("Students responded", summary["completed"])
        for slot, column in ((1, w2), (2, w3)):
            slot_data = summary["slots"][slot]
            pct = None if not slot_data["responses"] else 100 * slot_data["correct"] / slot_data["responses"]
            column.metric(f"Q{slot} accuracy", "—" if pct is None else f"{pct:.0f}%")

        for slot, question in ((1, warmup.question_one), (2, warmup.question_two)):
            st.markdown(f"**Q{slot}: {question.get('prompt') or 'Question'}**")
            standard = " · ".join(part for part in [str(question.get("standard_code") or ""), str(question.get("standard_description") or "")] if part)
            if standard:
                st.caption(standard)
            incorrect_ids = summary["slots"][slot]["incorrect_ids"]
            if incorrect_ids:
                st.caption("Missed by: " + ", ".join(sorted((name_by_id.get(sid, "Student") for sid in incorrect_ids), key=str.casefold)))

        if target_date == current_daily_date() and any(str(row.student_answer or "").strip() for row in warmup_rows):
            with st.expander("Today’s raw Warm-Up responses", expanded=False):
                st.dataframe(pd.DataFrame([
                    {
                        "Student": name_by_id.get(str(row.student_id), "Student"),
                        "Question": f"Q{row.question_slot}",
                        "Response": row.student_answer or "—",
                        "Correct": "Yes" if row.correct else "No",
                    }
                    for row in warmup_rows
                ]), hide_index=True, use_container_width=True)
        elif target_date < current_daily_date():
            st.caption("For past dates, typed student answers are no longer kept; accuracy and standards remain available.")

    st.markdown("#### Weekly Mystery")
    week_start = week_start_for(target_date)
    try:
        mystery_record = store.get_weekly_mystery(week_start)
        mystery_stats = store.weekly_mystery_teacher_stats(week_start) if mystery_record is not None else None
    except Exception as exc:
        mystery_record = None
        mystery_stats = None
        st.warning("Mystery history could not be loaded right now.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
    if mystery_record is None:
        st.caption(f"No Weekly Mystery was found for the week of {week_start.strftime('%B %d, %Y').replace(' 0', ' ')}.")
    else:
        mystery = mystery_for_key(mystery_record.mystery_key)
        day_number = school_day_number(target_date)
        m1, m2, m3 = st.columns(3)
        m1.metric("Week", week_start.strftime("%b %d"))
        m2.metric("All-class clues", int((mystery_stats or {}).get("clues_unlocked", 0)))
        m3.metric("All-class solved", int((mystery_stats or {}).get("correct", 0)))
        if day_number:
            st.caption(f"You selected school day {day_number} of the Mystery week. The totals above show the full week's activity.")
        raffle = store.get_app_setting(f"weekly_mystery_raffle::{week_start.isoformat()}::{selected.class_id}")
        if isinstance(raffle, dict) and raffle.get("nickname"):
            st.caption(f"{selected.class_name} raffle winner: **{raffle['nickname']}**")
        with st.expander("🔒 Mystery answer & clues", expanded=False):
            st.markdown(f"**{mystery.category}: {mystery.answer}**")
            for index, clue in enumerate(mystery.clues[:5], start=1):
                st.write(f"**Clue {index}:** {clue}")
