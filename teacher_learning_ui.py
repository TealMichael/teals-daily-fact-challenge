from __future__ import annotations

"""Teacher Learning Data UI.

Extracted from app.py during the v2.11.2 foundation pass. This module owns
the Fact Fluency and Igniter Standards Tracker views so changes in teacher
analytics do not share a 3,000+ line file with the student Daily workflow.
"""

from datetime import date
import re

import pandas as pd
import streamlit as st

from adaptive_engine import (
    STATUS_BUILDING, STATUS_FLUENT, STATUS_FOCUS, STATUS_UNKNOWN,
    complete_mastery_map,
)
from fact_engine import Fact, current_daily_date
from supabase_fact_store import SupabaseFactStore
from teacher_insights import (
    BAND_HELP, BAND_KNOWN, BAND_LEARNING, BAND_SLOW,
    common_fact_needs, pull_reason, rank_students_to_pull,
    standard_student_history, summarize_student_fluency, teacher_fact_band,
)
from ui_helpers import format_seconds, strategy_tip

def _override_label(value: int | None) -> str:
    return "Automatic" if value is None else f"{value}s"


def _override_value(label: str) -> int | None:
    return None if label == "Automatic" else int(label.rstrip("s"))


def _status_icon(status: str) -> str:
    return {
        STATUS_FLUENT: "🟢",
        STATUS_BUILDING: "🟡",
        STATUS_FOCUS: "🔴",
        STATUS_UNKNOWN: "⚪",
    }.get(status, "⚪")


def _family_need_text(rows) -> str:
    counts = {value: 0 for value in range(2, 11)}
    for row in rows:
        if row.status != STATUS_FOCUS:
            continue
        counts[row.a] += 1
        if row.b != row.a:
            counts[row.b] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ranked = [(family, count) for family, count in ranked if count > 0]
    if not ranked:
        return "No clear fact-family need yet"
    return " / ".join(f"{family}s" for family, _ in ranked[:2])


def _teaching_recommendation(*, students: int, observed: int, focus: int, building: int) -> str:
    if observed < max(4, int(students * 0.25)):
        return "Keep gathering evidence before making a class-wide decision."
    focus_ratio = focus / observed if observed else 0
    developing_ratio = (focus + building) / observed if observed else 0
    if focus_ratio >= 0.35 or developing_ratio >= 0.70:
        return "Good candidate for a quick whole-class strategy reminder."
    if focus >= 2 or developing_ratio >= 0.35:
        return "Good small-group target while adaptive practice continues."
    return "Keep this in adaptive practice; whole-class instruction is probably not needed right now."


def _teacher_band_icon(band: str) -> str:
    return {
        BAND_KNOWN: "🟢",
        BAND_SLOW: "🟡",
        BAND_HELP: "🔴",
        BAND_LEARNING: "⚪",
    }.get(str(band), "⚪")


def _school_year_start(day: date) -> date:
    return date(day.year if day.month >= 7 else day.year - 1, 7, 1)


def _render_teacher_fact_fluency(store: SupabaseFactStore, selected, students) -> None:
    raw_by_student = store.class_mastery_detail(selected.class_id, students=students)
    full_by_student = {
        student.student_id: complete_mastery_map(raw_by_student.get(student.student_id, []))
        for student in students
    }
    fact_keys = [(a, b) for a in range(2, 11) for b in range(a, 11)]
    fact_labels = {f"{a} × {b}": (a, b) for a, b in fact_keys}

    summaries = [
        summarize_student_fluency(
            student.student_id,
            student.nickname,
            full_by_student[student.student_id].values(),
        )
        for student in students
    ]
    summary_by_id = {summary.student_id: summary for summary in summaries}
    pull_students = rank_students_to_pull(summaries)
    stable_times = [summary.typical_correct_seconds for summary in summaries if summary.typical_correct_seconds is not None]
    class_typical_time = float(pd.Series(stable_times).median()) if stable_times else None
    average_known = sum(summary.known for summary in summaries) / len(summaries)
    average_evidence = sum(summary.evidence_facts for summary in summaries) / len(summaries)

    st.markdown("#### ⚡ Fact Fluency")
    st.caption("Accuracy comes first. Speed only matters after a student is retrieving a fact accurately and repeatedly.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Students to pull", len(pull_students))
    c2.metric("Avg facts known", f"{average_known:.0f}/45")
    c3.metric("Typical correct recall", "—" if class_typical_time is None else format_seconds(class_typical_time))
    c4.metric("Avg facts with evidence", f"{average_evidence:.0f}/45")

    st.markdown("#### 🎯 Students to Pull")
    if not pull_students:
        st.success("No clear accuracy or fluency pull group right now. Keep the normal Daily + Focus routine going.")
    else:
        pull_frame = pd.DataFrame([
            {
                "Student": summary.nickname,
                "Why pull": pull_reason(summary),
                "Start with": " · ".join(summary.start_facts) if summary.start_facts else "—",
            }
            for summary in pull_students
        ])
        st.dataframe(pull_frame, hide_index=True, use_container_width=True)
        st.caption("Repeated misses put a student at the top. Accurate-but-slow facts are a secondary fluency signal, not an accuracy penalty.")

    common_needs = common_fact_needs(full_by_student, limit=5)
    st.markdown("#### Most Common Fact Needs")
    if not common_needs:
        st.success("No repeated accuracy or speed pattern is standing out across the class yet.")
    else:
        st.dataframe(pd.DataFrame([
            {
                "Fact": row["fact"],
                "🔴 Need help": row["needs_help"],
                "🟡 Accurate but slow": row["slow"],
            }
            for row in common_needs
        ]), hide_index=True, use_container_width=True)

    st.markdown("#### All Students")
    ordered_summaries = sorted(
        summaries,
        key=lambda summary: (
            summary not in pull_students,
            -summary.needs_help,
            -summary.slow,
            summary.nickname.casefold(),
        ),
    )
    st.dataframe(pd.DataFrame([
        {
            "Student": summary.nickname,
            "🟢 Knows": summary.known,
            "🟡 Slow": summary.slow,
            "🔴 Needs help": summary.needs_help,
            "Evidence": f"{summary.evidence_facts}/45",
            "Typical correct recall": "—" if summary.typical_correct_seconds is None else format_seconds(summary.typical_correct_seconds),
        }
        for summary in ordered_summaries
    ]), hide_index=True, use_container_width=True)

    with st.expander("How is Fact Fluency being read?", expanded=False):
        st.markdown("**🟢 Knows It** — repeated accurate retrieval with a stable correct streak and roughly 5 seconds or less on correct responses.")
        st.markdown("**🟡 Accurate, Still Slow** — several accurate retrievals show the fact is known, but recall is consistently taking noticeably longer (about 7+ seconds).")
        st.markdown("**🔴 Needs Help** — at least two independent misses show a real accuracy pattern. One isolated miss never creates a red flag.")
        st.markdown("**⚪ Still Learning** — the app does not have enough stable evidence yet, or the fact is still developing. This is not automatically an intervention flag.")
        st.caption("Fact Coach corrections do not erase the original miss and do not count as independent fluency evidence.")

    with st.expander("🔎 Fact & student detail", expanded=False):
        detail_view = st.radio(
            "Detail",
            ["Look Up a Fact", "Look Up a Student"],
            horizontal=True,
            key="teacher_learning_detail_view",
        )
        if detail_view == "Look Up a Fact":
            selected_fact_label = st.selectbox("Fact", list(fact_labels), key="teacher_fact_detail")
            fa, fb = fact_labels[selected_fact_label]
            snapshots = [(student, full_by_student[student.student_id][(fa, fb)]) for student in students]
            bands = {band: [(student, snap) for student, snap in snapshots if teacher_fact_band(snap) == band]
                     for band in (BAND_KNOWN, BAND_SLOW, BAND_HELP, BAND_LEARNING)}
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("🟢 Knows", len(bands[BAND_KNOWN]))
            d2.metric("🟡 Slow", len(bands[BAND_SLOW]))
            d3.metric("🔴 Needs help", len(bands[BAND_HELP]))
            d4.metric("⚪ Learning", len(bands[BAND_LEARNING]))

            observed = [(student, snap) for student, snap in snapshots if snap.evidence_count > 0]
            total_evidence = sum(snap.evidence_count for _, snap in observed)
            total_correct = sum(snap.correct_count for _, snap in observed)
            accuracy = (100 * total_correct / total_evidence) if total_evidence else None
            st.markdown(f"**Teaching move for {fa} × {fb}:** {strategy_tip(Fact(a=fa, b=fb, tier='core'))}")
            if accuracy is not None:
                st.caption(f"Independent accuracy across recorded attempts: {accuracy:.0f}%")
            help_names = [student.nickname for student, _ in bands[BAND_HELP]]
            slow_names = [student.nickname for student, _ in bands[BAND_SLOW]]
            if help_names:
                st.markdown("**Pull for accuracy:** " + ", ".join(sorted(help_names, key=str.casefold)))
            if slow_names:
                st.markdown("**Accurate but slow:** " + ", ".join(sorted(slow_names, key=str.casefold)))
            if not help_names and not slow_names:
                st.success("No current accuracy or speed concern for this fact.")

            with st.expander("Optional: assign a Focus fact family", expanded=False):
                st.caption("This is a teacher override. Automatic personalization returns when the override is set back to Automatic.")
                family_choice = st.selectbox(
                    "Fact family", [f"{value}s" for value in range(2, 11)], index=fa - 2, key="fact_quick_family"
                )
                student_by_name = {student.nickname: student for student in students}
                default_names = sorted(help_names, key=str.casefold)
                chosen_names = st.multiselect(
                    "Students", list(student_by_name), default=default_names, key="fact_quick_students"
                )
                if st.button("Assign selected students", use_container_width=True, disabled=not chosen_names, key="fact_quick_assign"):
                    family = int(family_choice.rstrip("s"))
                    for name in chosen_names:
                        store.set_student_focus_override(student_by_name[name].student_id, family)
                    st.success(f"Assigned {family}s Focus to {len(chosen_names)} student(s).")
                    st.rerun()
        else:
            student_by_label = {student.nickname: student for student in students}
            student_label = st.selectbox("Student", list(student_by_label), key="mastery_student_select")
            student = student_by_label[student_label]
            summary = summary_by_id[student.student_id]
            individual_map = full_by_student[student.student_id]
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("🟢 Knows", summary.known)
            s2.metric("🟡 Slow", summary.slow)
            s3.metric("🔴 Needs help", summary.needs_help)
            s4.metric("Evidence", f"{summary.evidence_facts}/45")

            help_rows = [row for row in individual_map.values() if teacher_fact_band(row) == BAND_HELP]
            slow_rows = [row for row in individual_map.values() if teacher_fact_band(row) == BAND_SLOW]
            if help_rows:
                help_rows = sorted(help_rows, key=lambda row: (row.ema_accuracy if row.ema_accuracy is not None else 1.0, -row.evidence_count, row.a, row.b))
                st.markdown("**Accuracy needs:** " + " · ".join(f"{row.a}×{row.b}" for row in help_rows[:8]))
            if slow_rows:
                slow_rows = sorted(slow_rows, key=lambda row: (-(row.ema_seconds or 0.0), row.a, row.b))
                st.markdown("**Accurate but slow:** " + " · ".join(f"{row.a}×{row.b}" for row in slow_rows[:8]))
            if not help_rows and not slow_rows:
                st.success("No current accuracy or speed concern for this student.")

            student_fact_label = st.selectbox("Inspect one fact", list(fact_labels), key="student_fact_why")
            sa, sb = fact_labels[student_fact_label]
            snap = individual_map[(sa, sb)]
            band = teacher_fact_band(snap)
            st.markdown(f"**{student_fact_label} — {_teacher_band_icon(band)} {band.replace('_', ' ').title()}**")
            if snap.evidence_count == 0:
                st.caption("No independent evidence yet.")
            else:
                st.write(f"Independent attempts: **{snap.evidence_count}** · correct: **{snap.correct_count}** · current correct streak: **{snap.correct_streak}**")
                if snap.ema_accuracy is not None:
                    st.write(f"Recent weighted accuracy: **{snap.ema_accuracy * 100:.0f}%**")
                if snap.ema_seconds is not None:
                    st.write(f"Recent weighted correct-retrieval time: **{format_seconds(snap.ema_seconds)}**")

            with st.expander("View all 45 facts", expanded=False):
                individual_table = []
                for key in fact_keys:
                    row = individual_map[key]
                    band = teacher_fact_band(row)
                    individual_table.append({
                        "Fact": f"{row.a} × {row.b}",
                        "Teacher read": f"{_teacher_band_icon(band)} {band.replace('_', ' ').title()}",
                        "Evidence": row.evidence_count,
                        "Correct": "—" if not row.evidence_count else f"{row.correct_count}/{row.evidence_count}",
                        "Recent correct time": "—" if row.ema_seconds is None else format_seconds(row.ema_seconds),
                    })
                st.dataframe(pd.DataFrame(individual_table), hide_index=True, use_container_width=True)
            st.caption("Account fixes, PINs, Daily resets, and personal Focus overrides live in Student Support.")

    with st.expander("⚙️ Advanced fact map & class-wide Focus controls", expanded=False):
        st.caption("The full engine view is still available when you need it, but it stays out of the normal teaching dashboard.")
        filter_options = ["All facts", "Needs-help facts only"] + [f"{value}s" for value in range(2, 11)]
        heat_filter = st.selectbox("Fact map filter", filter_options, key="teacher_heatmap_filter")
        help_keys = [key for key in fact_keys if any(teacher_fact_band(full_by_student[s.student_id][key]) == BAND_HELP for s in students)]
        family_filters = {f"{value}s": value for value in range(2, 11)}
        if heat_filter == "Needs-help facts only":
            shown_keys = help_keys
        elif heat_filter in family_filters:
            family = family_filters[heat_filter]
            shown_keys = [key for key in fact_keys if family in key]
        else:
            shown_keys = fact_keys
        matrix_rows = []
        for student in students:
            row = {"Student": student.nickname}
            for key in shown_keys:
                row[f"{key[0]}×{key[1]}"] = _teacher_band_icon(teacher_fact_band(full_by_student[student.student_id][key]))
            matrix_rows.append(row)
        if shown_keys:
            st.dataframe(pd.DataFrame(matrix_rows), hide_index=True, use_container_width=True, height=min(650, 78 + len(students) * 35))
        else:
            st.success("No facts are currently marked as a repeated accuracy need in this class.")

        with st.expander("Class-wide Focus overrides", expanded=False):
            st.caption("Leave these on Automatic unless you intentionally want to steer Focus Practice for everyone or this class.")
            override_options = ["Automatic"] + [f"{value}s" for value in range(2, 11)]
            current_global = store.get_global_focus_override()
            global_choice = st.selectbox("Everyone", override_options, index=override_options.index(_override_label(current_global)), key="global_focus_override_ui")
            if st.button("Save everyone focus", use_container_width=True, key="save_global_focus_mastery"):
                store.set_global_focus_override(_override_value(global_choice))
                st.success("Everyone Focus setting saved.")
                st.rerun()
            current_class = store.get_class_focus_override(selected.class_id)
            class_choice = st.selectbox(selected.class_name, override_options, index=override_options.index(_override_label(current_class)), key=f"class_focus_override_{selected.class_id}")
            if st.button("Save class focus", use_container_width=True, key="save_class_focus_mastery"):
                store.set_class_focus_override(selected.class_id, _override_value(class_choice))
                st.success("Class Focus setting saved.")
                st.rerun()

        with st.expander("How the app teaches & uses data", expanded=False):
            st.markdown("**Daily 10:** independent first-try retrieval evidence.")
            st.markdown("**Fix Your Misses:** corrective teaching; the coached retry does not erase the original miss.")
            st.markdown("**Focus Practice:** eight personalized retrievals using weak/developing facts, some unknowns, spacing, and maintenance facts.")
            st.markdown("**No placement test:** every fact begins without enough evidence and grows only through normal independent retrieval.")
            st.markdown("**Accuracy before speed:** response time matters only after accurate retrieval is established.")


def _render_teacher_standards_tracker(store: SupabaseFactStore, selected, students) -> None:
    st.markdown("#### 📚 Igniter Standards Tracker")
    st.caption("Choose a standard to see the evidence your Igniter questions have collected over time. This is evidence history, not an automatic mastery claim.")

    today = current_daily_date()
    start_date = _school_year_start(today)
    try:
        rows = store.list_warmup_answers(start_date, today, class_id=selected.class_id)
    except Exception as exc:
        st.error("Igniter history could not be loaded. Try Refresh data and open this view again.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return

    student_ids = {student.student_id for student in students}
    rows = [row for row in rows if row.student_id in student_ids and str(row.standard_code or "").strip()]
    if not rows:
        st.info("No standards-tagged Igniter responses have been recorded for this class yet.")
        return

    latest_by_code = {}
    for row in rows:
        code = str(row.standard_code or "").strip()
        current = latest_by_code.get(code)
        if current is None or (str(row.warmup_date), row.answered_at) > (str(current.warmup_date), current.answered_at):
            latest_by_code[code] = row
    codes = sorted(latest_by_code, key=lambda code: (str(latest_by_code[code].warmup_date), latest_by_code[code].answered_at), reverse=True)

    def standard_label(code: str) -> str:
        row = latest_by_code[code]
        description = re.sub(r"\s+", " ", str(row.standard_description or "")).strip()
        return f"{code} — {description}" if description else code

    selected_code = st.selectbox(
        "Indiana standard",
        codes,
        format_func=standard_label,
        key=f"teacher_standard_tracker_{selected.class_id}",
        help="Type a standard code or skill word to search the standards you have actually checked with an Igniter.",
    )
    matching = [row for row in rows if str(row.standard_code or "").strip() == selected_code]
    latest = latest_by_code[selected_code]
    if latest.standard_description:
        st.caption(str(latest.standard_description))

    history = standard_student_history(students, rows, selected_code)
    checked = [item for item in history if item["checks"] > 0]
    total_checks = len(matching)
    total_correct = sum(bool(row.correct) for row in matching)
    accuracy = (total_correct / total_checks * 100) if total_checks else None
    last_date = max(str(row.warmup_date) for row in matching) if matching else None

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Students checked", f"{len(checked)}/{len(students)}")
    t2.metric("Igniter checks", total_checks)
    t3.metric("Correct", "—" if accuracy is None else f"{accuracy:.0f}%")
    t4.metric("Last checked", "—" if not last_date else date.fromisoformat(last_date).strftime("%b %d"))

    st.markdown("#### Student History")
    st.caption("History is shown oldest → newest. Students with the lowest current evidence appear first; students with no evidence are listed last.")
    history_frame = pd.DataFrame([
        {
            "Student": item["nickname"],
            "Checks": item["checks"],
            "Correct": "—" if item["checks"] == 0 else f"{item['correct']}/{item['checks']} ({item['accuracy'] * 100:.0f}%)",
            "History": item["history"],
        }
        for item in history
    ])
    st.dataframe(history_frame, hide_index=True, use_container_width=True)

    st.markdown("#### One Student's Evidence")
    student_options = [item["nickname"] for item in history]
    detail_name = st.selectbox("Student", student_options, key=f"teacher_standard_student_{selected.class_id}_{selected_code}")
    detail = next(item for item in history if item["nickname"] == detail_name)
    if not detail["rows"]:
        st.info(f"No Igniter evidence for {selected_code} has been recorded for this student yet.")
    else:
        detail_frame = pd.DataFrame([
            {
                "Date": date.fromisoformat(str(row.warmup_date)).strftime("%b %d, %Y"),
                "Igniter": f"Question {int(row.question_slot)}",
                "Question": re.sub(r"\s+", " ", str(row.prompt or "")).strip(),
                "Result": "✅ Correct" if row.correct else "❌ Needs review",
            }
            for row in reversed(detail["rows"])
        ])
        st.dataframe(detail_frame, hide_index=True, use_container_width=True)
    st.caption(f"History shown from {start_date.strftime('%b %d, %Y')} through {today.strftime('%b %d, %Y')}.")


def render_teacher_mastery_focus(store: SupabaseFactStore) -> None:
    st.markdown("### 📈 Learning Data")
    st.caption("A simple view of multiplication fact fluency plus the standards evidence collected by your Igniters.")
    classes = store.list_classes()
    if not classes:
        st.info("Create a class first.")
        return

    class_by_name = {item.class_name: item for item in classes}
    class_name = st.selectbox("Class", list(class_by_name), key="teacher_mastery_class")
    selected = class_by_name[class_name]
    students = store.list_students(selected.class_id)
    if not students:
        st.info("No students are in this class yet.")
        return

    view = st.radio(
        "Learning data view",
        ["⚡ Fact Fluency", "📚 Standards Tracker"],
        horizontal=True,
        label_visibility="collapsed",
        key="teacher_learning_data_view",
    )
    if view == "⚡ Fact Fluency":
        _render_teacher_fact_fluency(store, selected, students)
    else:
        _render_teacher_standards_tracker(store, selected, students)
