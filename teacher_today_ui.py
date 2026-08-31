from __future__ import annotations

"""Teacher-only Today Command Center UI introduced in v2.14."""

from datetime import timedelta
import html

import pandas as pd
import streamlit as st

from daily_modes import configured_daily_mode
from fact_engine import daily_mix_summary
from supabase_fact_store import SupabaseFactStore
from teacher_clock_ui import queue_clock_top10_for_class
from teacher_command_center import (
    build_today_action_items,
    summarize_daily_status,
    summarize_learning_routine,
)
from teacher_warmup_ui import _render_warmup_groups_and_email
from ui_helpers import format_seconds
from weekly_mystery import week_start_for


def render_teacher_today_command_center(
    store: SupabaseFactStore, *, ensure_today_fn, refresh_control, finish_refresh,
    set_refresh_stamp, leaderboard_from_status, leaderboard_is_final,
    leaderboard_final_key, mystery_pending_draw, go_teacher_tool,
) -> None:
    header_left, header_right = st.columns([4.2, 1.4])
    with header_left:
        st.markdown("### 📊 Today Command Center")
        st.caption("See the school day at a glance, then open the class that needs you. Student screens are unchanged.")
    with header_right:
        refresh_control(key="teacher_today_refresh")

    try:
        classes = store.list_classes()
    except Exception as exc:
        st.error("Classes could not load just now. Tap Refresh data to retry with a fresh Supabase connection.")
        st.session_state.pop("teacher_refresh_pending", False)
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return
    if not classes:
        st.info("Create your first class in Classes & Rosters.")
        return

    day, facts, challenge = ensure_today_fn(store)
    day_label = day.strftime("%A, %B %d").replace(" 0", " ")
    st.caption(f"📅 {day_label}")

    # Load a lightweight Daily 10 snapshot for each class once.  The selected
    # class reuses this roster/status data below instead of repeating reads.
    overview_rows = []
    class_snapshot = {}
    overview_errors = []
    for class_record in classes:
        try:
            roster = store.list_students(class_record.class_id)
            status_rows = store.daily_status(class_record.class_id, challenge.challenge_id, students=roster)
            summary = summarize_daily_status(status_rows)
            mode = configured_daily_mode(store, class_record.class_id, day)
            class_snapshot[class_record.class_id] = {
                "students": roster,
                "status": status_rows,
                "summary": summary,
                "mode": mode,
            }
            overview_rows.append({
                "Class": class_record.class_name,
                "Daily 10": mode,
                "Finished": f"{summary['complete']}/{summary['present']}",
                "In progress": summary["in_progress"],
                "Not started": summary["not_started"],
            })
        except Exception as exc:
            overview_errors.append((class_record.class_name, exc))
            class_snapshot[class_record.class_id] = {
                "students": [], "status": [], "summary": None,
                "mode": configured_daily_mode(store, class_record.class_id, day), "error": exc,
            }
            overview_rows.append({
                "Class": class_record.class_name,
                "Daily 10": class_snapshot[class_record.class_id]["mode"],
                "Finished": "—", "In progress": "—", "Not started": "—",
            })

    st.markdown("#### All Classes Snapshot")
    st.dataframe(pd.DataFrame(overview_rows), hide_index=True, use_container_width=True)
    if overview_errors:
        st.caption("⚠️ One or more class snapshots could not refresh. The class detail below will stay available where data loaded successfully.")

    class_by_name = {item.class_name: item for item in classes}
    selected_name = st.selectbox("Open class", list(class_by_name), key="teacher_today_class")
    selected = class_by_name[selected_name]
    st.caption("Done means Daily 10 + Fix Your Misses + Focus Practice are complete. The Mystery guess is optional.")
    selected_snapshot = class_snapshot.get(selected.class_id, {})
    students = list(selected_snapshot.get("students") or [])
    status = list(selected_snapshot.get("status") or [])
    absent_ids: set[str] = set()
    daily_status_error = selected_snapshot.get("error")
    daily_mode = str(selected_snapshot.get("mode") or configured_daily_mode(store, selected.class_id, day))

    progress_error = None
    learning_stats_error = None
    if daily_status_error is None:
        try:
            progress_map = store.class_learning_progress(selected.class_id, challenge.challenge_id, students=students)
        except Exception as exc:
            progress_map = {}
            progress_error = exc
        try:
            learning_stats = store.class_learning_stats(selected.class_id, day, students=students)
        except Exception as exc:
            learning_stats = {}
            learning_stats_error = exc
    else:
        progress_map = {}
        learning_stats = {}

    warmup_error = None
    try:
        warmup_today = store.get_warmup_set(selected.class_id, day)
        warmup_rows = store.list_warmup_answers(day, day, class_id=selected.class_id) if warmup_today is not None else []
    except Exception as exc:
        warmup_today = None
        warmup_rows = []
        warmup_error = exc

    if daily_status_error is None:
        if st.session_state.get("teacher_refresh_pending"):
            finish_refresh()
        else:
            set_refresh_stamp()
    else:
        st.session_state.pop("teacher_refresh_pending", False)

    stamp = st.session_state.get("teacher_last_refresh_at")
    if stamp:
        st.caption(f"🟢 Teacher data checked {stamp} · Refresh data forces a new Supabase connection.")

    # v2.14.1 intentionally keeps Today roster-based. Teachers do not need to
    # maintain a separate attendance list just to understand the class snapshot.

    if daily_status_error is None:
        daily_summary = summarize_daily_status(status)
        present_status = list(status)
        completed_rows = [row for row in present_status if row.get("status") == "Complete"]
        total = daily_summary["present"]
        not_started = daily_summary["not_started"]
        daily_complete = daily_summary["complete"]
        if progress_error is None:
            routine_summary = summarize_learning_routine(status, progress_map)
            full_complete = routine_summary["done"]
            working = routine_summary["daily"] + routine_summary["fix"] + routine_summary["focus"]
        else:
            routine_summary = {"done": 0, "daily": 0, "fix": 0, "focus": 0, "not_started": not_started}
            full_complete = working = None
    else:
        daily_summary = {"enrolled": len(students), "absent": 0, "present": len(students), "complete": 0, "in_progress": 0, "not_started": 0}
        routine_summary = {"done": 0, "daily": 0, "fix": 0, "focus": 0, "not_started": 0}
        present_status = status
        completed_rows = []
        total = len(students)
        full_complete = working = None
        not_started = daily_complete = 0

    average_accuracy = (
        sum(int(row["correct_count"]) for row in completed_rows) / len(completed_rows)
        if completed_rows else 0
    )
    median_time = (
        float(pd.Series([row["timed_seconds"] for row in completed_rows]).median())
        if completed_rows else 0
    )

    warmup_done = set()
    q1_accuracy = q2_accuracy = None
    if warmup_today is not None:
        real_ids = {student.student_id for student in students}
        warmup_rows = [row for row in warmup_rows if row.student_id in real_ids]
        q1_rows = [row for row in warmup_rows if row.question_slot == 1]
        q2_rows = [row for row in warmup_rows if row.question_slot == 2]
        warmup_done = {row.student_id for row in q1_rows} & {row.student_id for row in q2_rows}
        q1_accuracy = (sum(row.correct for row in q1_rows) / len(q1_rows) * 100) if q1_rows else None
        q2_accuracy = (sum(row.correct for row in q2_rows) / len(q2_rows) * 100) if q2_rows else None

    pending_prior_raffle = False
    try:
        current_week = week_start_for(day)
        pending_prior_raffle = mystery_pending_draw(store, current_week - timedelta(days=7))
    except Exception:
        pending_prior_raffle = False

    not_started_names = [
        str(row.get("nickname") or "").strip()
        for row in status
        if str(row.get("status") or "") == "Not started" and str(row.get("nickname") or "").strip()
    ]
    follow_up_names = []
    if progress_error is None:
        for row in status:
            if str(row.get("status") or "") != "Complete":
                continue
            progress = progress_map.get(str(row.get("student_id") or ""))
            if progress is None or not getattr(progress, "completed_at", None):
                nickname = str(row.get("nickname") or "").strip()
                if nickname:
                    follow_up_names.append(nickname)
    warmup_missing_names = [
        student.nickname for student in students if student.student_id not in warmup_done
    ] if warmup_today is not None else []

    st.markdown(f"#### {selected.class_name} · Quick follow-ups")
    actions = build_today_action_items(
        daily_summary=daily_summary,
        routine_summary=routine_summary,
        warmup_assigned=warmup_today is not None,
        warmup_finished=len(warmup_done),
        pending_prior_raffle=pending_prior_raffle,
        not_started_names=not_started_names,
        follow_up_names=follow_up_names,
        warmup_missing_names=warmup_missing_names,
    ) if daily_status_error is None else []
    if actions:
        action_html = "".join(
            f"<div style='padding:.42rem 0'><strong>{html.escape(item['icon'])} {html.escape(item['title'])}</strong>"
            f"<div style='color:#6b7280;font-size:.92rem'>{html.escape(item['detail'])}</div></div>"
            for item in actions[:4]
        )
        st.markdown(f"<div class='soft-card'>{action_html}</div>", unsafe_allow_html=True)

    qa1, qa2, qa3, qa4 = st.columns(4)
    with qa1:
        st.button(
            "🧠 Warm-Up", use_container_width=True, key="today_go_warmup",
            on_click=go_teacher_tool, args=("Warm-Up", selected.class_name),
        )
    with qa2:
        st.button("🛠️ Student Support", use_container_width=True, key="today_go_support", on_click=go_teacher_tool, args=("Student Support",))
    with qa3:
        st.button("🎟️ Mystery", use_container_width=True, key="today_go_mystery", on_click=go_teacher_tool, args=("Weekly Mystery",))
    with qa4:
        st.button("🎯 Daily 10 Setup", use_container_width=True, key="today_go_daily_setup", on_click=go_teacher_tool, args=("Daily 10 Setup",))

    c1, c2, c3, c4 = st.columns(4)
    if daily_status_error is None:
        c1.metric("🟢 Done", "—" if full_complete is None else f"{full_complete}/{total}")
        c2.metric("🟡 Working", "—" if working is None else working)
        c3.metric("⚪ Not started", not_started)
        c4.metric("Daily 10 finished", f"{daily_complete}/{total}")
        st.caption(f"Students: {total} · Daily 10 mode: **{daily_mode}**")
    else:
        c1.metric("🟢 Done", "—")
        c2.metric("🟡 Working", "—")
        c3.metric("⚪ Not started", "—")
        c4.metric("Daily 10 finished", "—")
        st.warning("Daily 10 status could not load just now. Warm-Up and other teacher tools remain available; tap Refresh data to retry the class snapshot.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(daily_status_error)

    if progress_error is not None:
        st.warning("Full-routine progress could not load just now. Daily 10 completion is still accurate; Done/Working will return after Refresh data.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(progress_error)
    if learning_stats_error is not None:
        st.caption("⚠️ Streak/Days Completed details could not refresh; the rest of Today is still available.")

    if warmup_error is not None:
        st.warning("Warm-Up data could not load just now. The rest of Today is still available; try Refresh data once.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(warmup_error)

    if warmup_today is not None:
        st.markdown("#### 🧠 Quick Warm-Up")
        w1, w2, w3 = st.columns(3)
        w1.metric("Finished", f"{len(warmup_done)}/{total}")
        w2.metric("Spiral accuracy", "—" if q1_accuracy is None else f"{q1_accuracy:.0f}%")
        w3.metric("Yesterday accuracy", "—" if q2_accuracy is None else f"{q2_accuracy:.0f}%")
        st.caption("Unfinished present students are not counted as incorrect. Open the groups below whenever you are ready to act on the current data.")
        if st.toggle("🎯 Show Warm-Up groups & email", key=f"teacher_today_warmup_groups_{selected.class_id}"):
            _render_warmup_groups_and_email(
                store, selected, day, warmup_today, warmup_rows, students,
                key_prefix=f"teacher_today_warmup_{selected.class_id}_{day.isoformat()}",
            )

    st.markdown("#### 🏆 Class Top 10")
    if daily_status_error is not None:
        st.caption("Daily standings are temporarily unavailable. Warm-Up results above are unaffected; tap Refresh data to retry.")
    else:
        board = leaderboard_from_status(present_status, limit=10)
        final = leaderboard_is_final(store, day, selected.class_id, completed=daily_complete, total=total)
        if final:
            st.success("**Final Top 10** · final standings for today")
        else:
            st.info(f"**Live Top 10** · {daily_complete} of {total} students finished · standings may change")
        board_frame = pd.DataFrame([{"Rank": row["rank"], "Nickname": row["nickname"]} for row in board]) if board else pd.DataFrame(columns=["Rank", "Nickname"])
        if board:
            st.dataframe(board_frame, hide_index=True, use_container_width=True)
        else:
            st.caption("No completed Daily attempts yet today.")

        top10_a, top10_b = st.columns(2)
        with top10_a:
            if st.button("🏆 Display Top 10", use_container_width=True, key=f"display_top10_{selected.class_id}"):
                st.session_state["teacher_projector_mode"] = True
                st.session_state["teacher_projector_class_id"] = selected.class_id
                st.session_state["teacher_projector_class_name"] = selected.class_name
                st.rerun()
        with top10_b:
            if final and not (total > 0 and daily_complete >= total):
                if st.button("Return standings to Live", use_container_width=True, key=f"unfinal_top10_{selected.class_id}"):
                    store.set_app_setting(leaderboard_final_key(day, selected.class_id), False)
                    st.rerun()
            elif not final:
                if st.button("Mark standings Final", use_container_width=True, key=f"final_top10_{selected.class_id}"):
                    store.set_app_setting(leaderboard_final_key(day, selected.class_id), True)
                    st.rerun()
            else:
                st.caption("Everyone has finished the Daily 10, so standings are automatically Final.")

    if st.button("📟 Send Top 10 to Clock Now", use_container_width=True, key=f"send_clock_top10_{selected.class_id}"):
        try:
            block = queue_clock_top10_for_class(store, selected.class_id)
            st.success(f"Block {block} Top 10 queued for the classroom clock. An online clock should pick it up within about 15 seconds.")
        except Exception as exc:
            st.warning(f"Clock send is not ready yet: {exc}")

    teacher_students = {student.student_id: student for student in students}
    summary_rows = []
    performance_rows = []
    for row in status:
        sid = row["student_id"]
        progress = progress_map.get(sid)
        if progress and progress.completed_at:
            routine = "🟢 Done"
        elif row["status"] == "Not started":
            routine = "⚪ Not started"
        elif row["status"] != "Complete":
            routine = "🟡 Daily 10"
        elif progress and progress.fix_completed_at:
            routine = "🟡 Focus Practice"
        else:
            routine = "🟡 Fix Your Misses"
        stats = learning_stats.get(sid, {"current_streak": 0, "stars": 0})
        student_record = teacher_students.get(sid)
        pin = student_record.pin_code if student_record and student_record.pin_code else "Reset once"
        summary_rows.append({
            "Nickname": row["nickname"],
            "PIN": pin,
            "Status": routine,
            "Streak": f"🔥 {stats.get('current_streak', 0)}" if stats.get("current_streak", 0) else "—",
            "Days Completed": int(stats.get("stars", 0)),
        })
        performance_rows.append({
            "Nickname": row["nickname"],
            "PIN": pin,
            "Daily accuracy": "" if row["correct_count"] is None else f"{int(row['correct_count'])}/10",
            "Timed sprint": "" if row["timed_seconds"] is None else format_seconds(float(row["timed_seconds"])),
        })
    if summary_rows:
        st.markdown("#### Where everyone is")
        st.dataframe(pd.DataFrame(summary_rows), hide_index=True, use_container_width=True)

    with st.expander("Teacher-only accuracy & timing", expanded=False):
        st.caption("Students never see these scores or times. Accuracy ranks first; time only breaks ties.")
        if completed_rows:
            st.caption(f"Class average: {average_accuracy:.1f}/10 · median timed sprint: {format_seconds(median_time)}")
        st.dataframe(pd.DataFrame(performance_rows), hide_index=True, use_container_width=True)

    with st.expander("Preview today's balanced 10", expanded=False):
        if daily_mode != "Multiplication":
            st.caption(f"{daily_mode} is assigned to this class today. The multiplication preview below remains the protected default generator and is not the alternate-mode question list.")
        mix = daily_mix_summary(facts)
        st.caption(
            f"Core mix: {mix['easy']} easier retrieval · {mix['medium']} medium · {mix['hard']} harder"
            + (f" · {mix['extension']} 11/12 extension" if mix["extension"] else " · no 11/12 fact today")
        )
        for index, fact in enumerate(facts, start=1):
            st.write(f"{index}. **{fact.label} = {fact.product}** · {fact.tier}")
