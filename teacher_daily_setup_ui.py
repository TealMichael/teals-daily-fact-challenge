from __future__ import annotations

"""Teacher-only per-class Daily 10 mode planning."""

from datetime import date

import streamlit as st

from daily_modes import DAILY_MODES, configured_daily_mode, daily_mode_setting_key
from fact_engine import current_daily_date
from supabase_fact_store import SupabaseFactStore


def render_teacher_daily_setup(store: SupabaseFactStore) -> None:
    st.markdown("### 🎯 Daily 10 Setup")
    st.caption(
        "Choose a Daily 10 for each class and date. Multiplication is the default, so doing nothing keeps the proven existing Daily exactly as-is."
    )
    target_date = st.date_input("Daily 10 date", value=current_daily_date(), key="teacher_daily10_setup_date")
    classes = store.list_classes()
    if not classes:
        st.info("Create a class first.")
        return

    st.info(
        "Alternate modes use the normal class Top 10, but they do not add evidence to Multiplication Fact Fluency. "
        "For now they are Daily 10 only — no Fix Misses, Focus Practice, or Fact Coach."
    )
    st.caption("Block 4 is supported in the app. The physical classroom clock remains intentionally mapped to Blocks 1–3.")

    values = {}
    with st.form(f"daily10_setup_form_{target_date.isoformat()}"):
        for class_record in classes:
            current = configured_daily_mode(store, class_record.class_id, target_date)
            values[class_record.class_id] = st.selectbox(
                class_record.class_name,
                list(DAILY_MODES),
                index=list(DAILY_MODES).index(current),
                key=f"daily10_mode_{target_date.isoformat()}_{class_record.class_id}",
            )
        save = st.form_submit_button("Save Daily 10 setup", type="primary", use_container_width=True)

    if save:
        try:
            for class_record in classes:
                key = daily_mode_setting_key(target_date, class_record.class_id)
                mode = values[class_record.class_id]
                if mode == "Multiplication":
                    store.delete_app_setting(key)
                else:
                    store.set_app_setting(key, mode)
            st.success(f"Daily 10 setup saved for {target_date.strftime('%A, %B %d').replace(' 0', ' ')}.")
            st.rerun()
        except Exception as exc:
            st.error("The Daily 10 setup could not be saved.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
