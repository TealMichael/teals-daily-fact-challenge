from __future__ import annotations

"""Teacher-only Phase 2 instructional intelligence UI."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from adaptive_engine import complete_mastery_map
from fact_engine import Fact, current_daily_date
from supabase_fact_store import SupabaseFactStore
from teacher_insights import BAND_HELP, teacher_fact_band
from teacher_intelligence import (
    build_student_signals,
    class_fact_priorities,
    progress_signals,
    recommended_teaching_move,
    repeated_miss_facts,
    student_recommendation,
    suggested_small_groups,
    watch_signals,
    weekly_recap,
)
from ui_helpers import format_seconds, strategy_tip


def _class_picker(store: SupabaseFactStore, *, key: str):
    classes = store.list_classes()
    if not classes:
        st.info("Create a class first.")
        return None, []
    by_name = {item.class_name: item for item in classes}
    preferred = st.session_state.get("teacher_today_selected_class_name")
    if preferred in by_name and key not in st.session_state:
        st.session_state[key] = preferred
    selected_name = st.selectbox("Class", list(by_name), key=key)
    return by_name[selected_name], classes


def _load_class_evidence(store: SupabaseFactStore, selected, *, today: date, history_days: int = 28):
    students = store.list_students(selected.class_id)
    if not students:
        return students, {}, []
    raw = store.class_mastery_detail(selected.class_id, students=students)
    full = {
        student.student_id: complete_mastery_map(raw.get(student.student_id, []))
        for student in students
    }
    history = store.teacher_daily_history(
        selected.class_id, today - timedelta(days=history_days), today, students=students,
    )
    return students, full, history


def _priority_names(priority: dict, students, full_by_student) -> list[str]:
    if not priority:
        return []
    key = (int(priority["a"]), int(priority["b"]))
    by_id = {student.student_id: student.nickname for student in students}
    names = [
        by_id[sid] for sid, fact_map in full_by_student.items()
        if sid in by_id and teacher_fact_band(fact_map[key]) == BAND_HELP
    ]
    return sorted(names, key=str.casefold)


def render_teacher_next_steps(store: SupabaseFactStore) -> None:
    st.markdown("### 🧭 What Should I Teach Next?")
    st.caption("Uses recent multiplication results to suggest a short teaching plan. Student practice is not changed automatically.")
    selected, _ = _class_picker(store, key="teacher_intelligence_class")
    if selected is None:
        return
    today = current_daily_date()
    try:
        students, full_by_student, history = _load_class_evidence(store, selected, today=today)
    except Exception as exc:
        st.warning("Next Steps could not refresh just now. Learning Data and student work are still available.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return
    if not students:
        st.info("This class has no students yet.")
        return

    signals = build_student_signals(students, full_by_student, history, today=today)
    priorities = class_fact_priorities(full_by_student, history, limit=5)
    top = priorities[0] if priorities else None

    st.markdown("#### 🎯 Best Teaching Opportunity")
    if top is None:
        st.success("No class-wide multiplication gap is strong enough to interrupt the normal Daily + Focus routine right now.")
    else:
        names = _priority_names(top, students, full_by_student)
        c1, c2, c3 = st.columns(3)
        c1.metric("Fact", top["fact"])
        c2.metric("Need accuracy help", top["needs_help"])
        c3.metric("Repeated recent misses", top["repeated_students"])
        st.markdown(f"**Suggested next move:** {recommended_teaching_move(top, class_size=len(students))}")
        st.caption(f"Strategy idea: {strategy_tip(Fact(a=int(top['a']), b=int(top['b']), tier='core'))}")
        if names:
            st.markdown("**Students to watch for this fact:** " + ", ".join(names))

    st.markdown("#### Class Priorities")
    if priorities:
        st.dataframe(pd.DataFrame([
            {
                "Fact": row["fact"],
                "Needs accuracy help": row["needs_help"],
                "Repeated recent misses": row["repeated_students"],
                "Students missing recently": row["recent_miss_students"],
                "Accurate but slow": row["slow"],
            }
            for row in priorities
        ]), hide_index=True, use_container_width=True)
    else:
        st.caption("No repeated class-wide fact need is standing out yet.")

    groups = suggested_small_groups(signals, full_by_student, limit=5)
    st.markdown("#### 👥 Suggested Small Groups")
    if not groups:
        st.success("No extra small group stands out right now. Keep the normal Daily + Focus routine.")
    else:
        for group in groups:
            with st.expander(f"{group['name']} · {len(group['names'])} student{'s' if len(group['names']) != 1 else ''}", expanded=False):
                st.markdown("**Students:** " + ", ".join(group["names"]))
                st.caption(group["reason"])

    watch = watch_signals(signals)
    improving = progress_signals(signals)
    st.markdown("#### 🔎 Students Worth a Look")
    if not watch and not improving:
        st.caption("No students stand out for repeated misses, a fact to recheck, or a meaningful recent gain.")
    else:
        rows = []
        by_id = {signal.student_id: signal for signal in signals}
        surfaced = []
        for signal in watch + improving:
            if signal.student_id not in surfaced:
                surfaced.append(signal.student_id)
        for sid in surfaced[:12]:
            signal = by_id[sid]
            change = signal.accuracy_change
            rows.append({
                "Student": signal.nickname,
                "Repeated errors": ", ".join(signal.repeated_misses[:3]) or "—",
                "Facts to recheck": ", ".join(signal.fragile_facts[:3]) or "—",
                "Recent accuracy change": "—" if change is None else f"{change * 100:+.0f} pts",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        if improving:
            st.caption("Progress compares the five most recent Multiplication Dailies with the five before them.")
        st.caption("A fact appears here when it was previously strong but a recent miss makes it worth checking again.")


def render_teacher_weekly_recap(store: SupabaseFactStore) -> None:
    st.markdown("### 📅 Weekly Teacher Recap")
    st.caption("A quick look at the week. Other Daily 10 modes are listed separately from multiplication fluency.")
    selected, _ = _class_picker(store, key="teacher_recap_class")
    if selected is None:
        return
    today = current_daily_date()
    this_week = today - timedelta(days=today.weekday())
    period = st.radio("Week", ["Last week", "This week"], horizontal=True, key="teacher_recap_period")
    week_start = this_week - timedelta(days=7) if period == "Last week" else this_week
    try:
        students, full_by_student, history = _load_class_evidence(store, selected, today=today, history_days=35)
    except Exception as exc:
        st.warning("The weekly recap could not refresh just now. Try again in a moment.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return
    if not students:
        st.info("This class has no students yet.")
        return

    recap = weekly_recap(history, full_by_student, week_start=week_start, class_size=len(students))
    st.markdown(f"#### {week_start.strftime('%B %-d')}–{recap['week_end'].strftime('%B %-d, %Y')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Daily 10 completions", recap["daily_completions"])
    c2.metric("Students who completed", f"{recap['students_with_completion']}/{len(students)}")
    c3.metric("Multiplication accuracy", "—" if recap["multiplication_accuracy"] is None else f"{recap['multiplication_accuracy'] * 100:.0f}%")
    c4.metric("Median multiplication time", "—" if recap["median_multiplication_time"] is None else format_seconds(recap["median_multiplication_time"]))

    if recap["accuracy_trend"] is not None:
        delta = recap["accuracy_trend"] * 100
        st.caption(f"Multiplication accuracy vs. the previous school week: **{delta:+.0f} percentage points**.")
    if recap["modes"]:
        st.caption("Daily 10 completions by mode: " + " · ".join(f"{mode}: {count}" for mode, count in recap["modes"].items()))

    left, right = st.columns(2)
    with left:
        st.markdown("#### Most-Missed Multiplication Facts")
        if recap["common_misses"]:
            st.dataframe(pd.DataFrame([
                {"Fact": row["fact"], "Students": row["students"], "Misses": row["misses"]}
                for row in recap["common_misses"]
            ]), hide_index=True, use_container_width=True)
        else:
            st.caption("No multiplication misses were recorded in this week.")
    with right:
        st.markdown("#### Students Making Progress")
        if recap["progress"]:
            st.dataframe(pd.DataFrame([
                {"Student": row["nickname"], "Accuracy gain": f"+{row['gain'] * 100:.0f} pts", "This week": f"{row['accuracy'] * 100:.0f}%"}
                for row in recap["progress"]
            ]), hide_index=True, use_container_width=True)
        else:
            st.caption("No student improved by at least 10 percentage points with enough work in both weeks.")

    st.markdown("#### Fluency Momentum")
    st.metric("New facts looking strong", recap["newly_secured_signal_count"])
    st.caption("This is an estimate based on each student's current fact history.")


def render_student_learning_snapshot(store: SupabaseFactStore, class_record, students, student) -> None:
    """Add instructional context above the existing Student Support actions."""
    today = current_daily_date()
    try:
        raw = store.get_mastery(student.student_id)
        full_map = complete_mastery_map(raw)
        history = store.teacher_daily_history(
            class_record.class_id, today - timedelta(days=28), today, students=students,
        )
        signals = build_student_signals([student], {student.student_id: full_map}, history, today=today)
        signal = signals[0]
    except Exception as exc:
        st.caption("⚠️ Learning snapshot could not refresh; the support tools below are still available.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return

    st.markdown("#### 📚 Learning Snapshot")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Knows", f"{signal.summary.known}/45")
    c2.metric("Needs help", signal.summary.needs_help)
    c3.metric("Accurate but slow", signal.summary.slow)
    c4.metric("Facts with history", f"{signal.summary.evidence_facts}/45")
    st.markdown(f"**Recommended focus:** {student_recommendation(signal)}")

    if signal.repeated_misses:
        st.markdown("**Repeated recent errors:** " + ", ".join(signal.repeated_misses[:5]))
    if signal.fragile_facts:
        st.markdown("**Facts to recheck:** " + ", ".join(signal.fragile_facts[:5]))
    if signal.accuracy_change is not None:
        st.caption(f"Recent multiplication accuracy: {signal.accuracy_change * 100:+.0f} percentage points compared with the previous five Dailies.")

    student_history = [row for row in history if str(row.get("student_id")) == str(student.student_id)]
    recent = sorted(student_history, key=lambda row: str(row.get("challenge_date")), reverse=True)[:5]
    if recent:
        st.markdown("**Recent Daily 10 results**")
        st.dataframe(pd.DataFrame([
            {
                "Date": row["challenge_date"],
                "Mode": row["daily_mode"],
                "Score": f"{row['correct_count']}/10",
                "Time": "—" if row.get("timed_seconds") is None else format_seconds(row["timed_seconds"]),
            }
            for row in recent
        ]), hide_index=True, use_container_width=True)
