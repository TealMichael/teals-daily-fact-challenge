from __future__ import annotations

"""Teacher-only class recovery tools for v2.20.

These tools deliberately stay out of the student flow. They restore already-earned
Mystery clue receipts or reopen several same-day attempts in one teacher action.
"""

import streamlit as st

from fact_engine import current_daily_date
from weekly_mystery import week_start_for


def render_class_recovery_tools(store, class_record, students, *, ensure_today_fn) -> None:
    active_students = [
        item for item in students
        if item.active and not getattr(item, "is_test", False)
    ]
    if not st.toggle(
        "🚑 Show class recovery tools",
        value=False,
        key=f"teacher_class_recovery_tools_{class_record.class_id}",
        help="Use these only when several students need the same recovery action.",
    ):
        return

    st.markdown("#### 🚑 Class Recovery")
    st.caption(
        "Repair missing Mystery clues without making students redo completed work, "
        "or reopen today's Daily for several students at once."
    )
    try:
        recovery_day, _, recovery_challenge = ensure_today_fn(store)
        recovery_status = store.daily_status(
            class_record.class_id, recovery_challenge.challenge_id, students=active_students
        )
    except Exception as exc:
        recovery_day = current_daily_date()
        recovery_challenge = None
        recovery_status = []
        st.warning("Today's recovery status could not load right now.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)

    st.markdown("##### 🕵️ Repair missing Mystery clues")
    st.caption(
        "This only restores a clue when the saved Daily + required follow-up prove the student earned it. "
        "Incomplete students are never granted a clue."
    )
    if st.button(
        "Repair earned clues for this class",
        use_container_width=True,
        key=f"repair_mystery_clues_{class_record.class_id}_{recovery_day}",
    ):
        try:
            week_start = week_start_for(recovery_day)
            through_day = 5 if recovery_day.weekday() >= 4 else max(1, recovery_day.weekday() + 1)
            result = store.repair_missing_mystery_clues_for_class(
                class_record.class_id,
                week_start,
                through_day_number=through_day,
                students=active_students,
            )
            st.session_state[f"mystery_repair_result_{class_record.class_id}"] = result
        except Exception as exc:
            st.error("Missing clues could not be repaired.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)

    repair_result = st.session_state.get(f"mystery_repair_result_{class_record.class_id}")
    if isinstance(repair_result, dict):
        repaired = list(repair_result.get("repaired") or [])
        if repaired:
            labels = []
            for item in repaired:
                days = ", ".join(f"#{int(day)}" for day in (item.get("days") or []))
                labels.append(f"{item.get('nickname', 'Student')} ({days})")
            st.success(
                f"Repaired earned clue receipts for {len(repaired)} student"
                f"{'s' if len(repaired) != 1 else ''}: " + " · ".join(labels)
            )
        else:
            st.success("No earned Mystery clues were missing for this class.")

    st.markdown("##### 🧰 Bulk reopen today's Daily")
    if recovery_challenge is None:
        st.caption("Today's Daily could not be checked.")
    else:
        started_ids = {
            str(row.get("student_id") or "")
            for row in recovery_status
            if row.get("attempt_id")
        }
        started_students = [item for item in active_students if item.student_id in started_ids]
        if not started_students:
            st.caption("No students in this class have a Daily attempt to reopen today.")
        else:
            by_label = {item.nickname: item for item in started_students}
            selected_reopen = st.multiselect(
                "Students to reopen",
                list(by_label),
                key=f"bulk_reopen_students_{class_record.class_id}_{recovery_day}",
                placeholder="Choose one or more students",
            )
            confirm_bulk_reopen = st.checkbox(
                "I understand these students will lose today's saved Daily and follow-up work.",
                key=f"bulk_reopen_confirm_{class_record.class_id}_{recovery_day}",
            )
            if st.button(
                f"Reopen Daily for {len(selected_reopen)} selected student"
                f"{'s' if len(selected_reopen) != 1 else ''}",
                use_container_width=True,
                type="primary",
                disabled=(not selected_reopen or not confirm_bulk_reopen),
                key=f"bulk_reopen_daily_{class_record.class_id}_{recovery_day}",
            ):
                try:
                    count = store.reset_daily_attempts(
                        [by_label[label].student_id for label in selected_reopen],
                        recovery_challenge.challenge_id,
                    )
                    st.session_state["teacher_roster_flash"] = (
                        "success",
                        f"Reopened today's Daily for {count} student"
                        f"{'s' if count != 1 else ''}.",
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Bulk reopen did not finish: {exc}")

    st.markdown("---")
