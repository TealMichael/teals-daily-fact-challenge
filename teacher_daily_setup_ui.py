from __future__ import annotations

"""Teacher-only weekly Daily 10 planning."""

from datetime import date, timedelta

import streamlit as st

from daily_modes import DAILY_MODES, configured_daily_mode, daily_mode_setting_key, questions_for_mode
from teacher_planning import copy_daily_week, monday_for, next_school_day, school_days_for_week, set_daily_mode
from fact_engine import current_daily_date
from supabase_fact_store import SupabaseFactStore



def render_teacher_daily_setup(store: SupabaseFactStore, *, show_heading: bool = True) -> None:
    if show_heading:
        st.markdown("### 🎯 Daily 10 Setup")
    st.caption("Plan a full school week at once. Multiplication is still the default, so blank/default planning never changes the proven Daily 10.")

    classes = store.list_classes()
    if not classes:
        st.info("Create a class first.")
        return

    picked = st.date_input("Week", value=current_daily_date(), key="teacher_daily10_week")
    week_start = monday_for(picked)
    days = school_days_for_week(week_start)
    st.caption(f"Week of **{week_start.strftime('%B %d, %Y').replace(' 0', ' ')}** · Alternate modes stay out of Multiplication Fact Fluency.")

    values: dict[tuple[str, date], str] = {}
    with st.form(f"daily10_week_form_{week_start.isoformat()}"):
        header = st.columns([1.25, 1, 1, 1, 1, 1])
        header[0].markdown("**Class**")
        for idx, day in enumerate(days, start=1):
            header[idx].markdown(f"**{day.strftime('%a')}**")
        for class_record in classes:
            row = st.columns([1.25, 1, 1, 1, 1, 1])
            row[0].markdown(f"**{class_record.class_name}**")
            for idx, day in enumerate(days, start=1):
                current = configured_daily_mode(store, class_record.class_id, day)
                values[(class_record.class_id, day)] = row[idx].selectbox(
                    f"{class_record.class_name} {day.isoformat()}",
                    list(DAILY_MODES),
                    index=list(DAILY_MODES).index(current),
                    key=f"daily10_week_mode_{class_record.class_id}_{day.isoformat()}",
                    label_visibility="collapsed",
                )
        save = st.form_submit_button("Save weekly Daily 10 plan", type="primary", use_container_width=True)
    if save:
        try:
            for class_record in classes:
                for day in days:
                    set_daily_mode(store, class_record.class_id, day, values[(class_record.class_id, day)])
            st.success("Weekly Daily 10 plan saved.")
            st.rerun()
        except Exception as exc:
            st.error("The weekly Daily 10 plan could not be saved.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)

    with st.expander("⚡ Week tools", expanded=False):
        st.caption("These tools change teacher setup only; they never edit completed student attempts.")
        a, b = st.columns(2)
        with a:
            if st.button("Copy previous week", use_container_width=True, key=f"copy_previous_daily10_{week_start}"):
                try:
                    copy_daily_week(store, classes, week_start - timedelta(days=7), week_start)
                    st.success("Previous week copied into this week.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with b:
            if st.button("Reset week to Multiplication", use_container_width=True, key=f"reset_daily10_week_{week_start}"):
                try:
                    for class_record in classes:
                        for day in days:
                            store.delete_app_setting(daily_mode_setting_key(day, class_record.class_id))
                    st.success("This week is back to Multiplication for every class.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        class_by_name = {item.class_name: item for item in classes}
        source_name = st.selectbox("Copy one class's whole week", list(class_by_name), key=f"daily10_source_class_{week_start}")
        if st.button("Apply this class's week to all classes", use_container_width=True, key=f"daily10_apply_all_{week_start}"):
            try:
                source = class_by_name[source_name]
                source_modes = [configured_daily_mode(store, source.class_id, day) for day in days]
                for class_record in classes:
                    for day, mode in zip(days, source_modes):
                        set_daily_mode(store, class_record.class_id, day, mode)
                st.success(f"{source.class_name}'s week was copied to all active classes.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.markdown("#### Preview tomorrow")
    preview_day = next_school_day(current_daily_date())
    preview_by_name = {item.class_name: item for item in classes}
    preview_name = st.selectbox("Preview class", list(preview_by_name), key="daily10_preview_class")
    preview_class = preview_by_name[preview_name]
    preview_mode = configured_daily_mode(store, preview_class.class_id, preview_day)
    st.caption(f"{preview_day.strftime('%A, %B %d').replace(' 0', ' ')} · **{preview_mode}**")
    with st.expander("See the 10 questions", expanded=False):
        try:
            for index, item in enumerate(questions_for_mode(preview_day, preview_mode), start=1):
                st.write(f"**{index}.** {item['prompt']}")
        except Exception as exc:
            st.warning("Tomorrow's preview could not be generated.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
