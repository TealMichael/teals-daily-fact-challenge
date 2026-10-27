from __future__ import annotations

"""Small, private student growth indicators; no leaderboard or extra practice."""

from datetime import date
import html

import streamlit as st

from standards_growth import growth_snapshot, evidence_for_standard
from standards_tagging import reconcile_tag


def _cache_key(student_id: str, class_id: str, day: date) -> str:
    return f"growth_evidence::{student_id}::{class_id}::{day.isoformat()}"


def student_evidence(store, student_id: str, class_id: str, day: date) -> list[dict] | None:
    """At most one network read per session/day; submitted rows extend the cache."""
    key = _cache_key(student_id, class_id, day)
    if key in st.session_state:
        return st.session_state[key]
    since = date(day.year if day.month >= 7 else day.year - 1, 7, 1)
    try:
        raw = store.student_standard_evidence(student_id, class_id, since)
        rows = []
        for item in raw:
            row = dict(item)
            decision = reconcile_tag(row.get("standard_code", ""), row.get("standard_description", ""),
                                     row.get("prompt", ""))
            if not decision.code:
                continue
            row["standard_code"] = decision.code
            row["standard_description"] = decision.description
            rows.append(row)
        st.session_state[key] = rows
    except Exception:
        # Migration or network trouble must never block Igniter/Daily 10.
        st.session_state[key] = None
    return st.session_state[key]


def note_new_standard_answer(
    student_id: str, class_id: str, day: date, *, code: str,
    description: str, prompt: str, correct: bool, source: str, slot: int | None = None,
) -> None:
    key = _cache_key(student_id, class_id, day)
    existing = st.session_state.get(key)
    if existing is None:
        return
    decision = reconcile_tag(code, description, prompt)
    if not decision.code:
        return
    from datetime import datetime, timezone
    existing.append({
        "student_id": student_id, "class_id": class_id,
        "activity_date": day.isoformat(), "answered_at": datetime.now(timezone.utc).isoformat(),
        "standard_code": decision.code, "standard_description": decision.description,
        "prompt": prompt, "correct": bool(correct), "source": source,
        "source_slot": slot,
    })


def standard_snapshot(store, student_id: str, class_id: str, day: date, code: str):
    records = student_evidence(store, student_id, class_id, day)
    if records is None:
        return None
    return growth_snapshot(evidence_for_standard(records, student_id, code))


def render_standard_progress(
    store, student_id: str, class_id: str, day: date, *, code: str,
    description: str = "", previous_progress: float | None = None,
    show_growth: bool = False, suppress_decline: bool = False,
) -> None:
    if not code:
        return
    snapshot = standard_snapshot(store, student_id, class_id, day, code)
    if snapshot is None:
        return
    visual = snapshot.progress
    if suppress_decline and previous_progress is not None:
        visual = max(visual, previous_progress)
    # Keep a private, single-day high-water display so an incorrect Igniter
    # response never visibly shrinks the bar on the next question. The mastery
    # model itself still uses the true last-four evidence without any floor.
    visual_key = f"growth_display::{student_id}::{class_id}::{day.isoformat()}::{code}"
    visual = max(visual, float(st.session_state.get(visual_key, visual)))
    st.session_state[visual_key] = visual
    start = min(visual, previous_progress if previous_progress is not None else visual)
    is_growing = show_growth and previous_progress is not None and visual > previous_progress
    st.markdown("""
<style>
@keyframes tdfc-standard-fill {from {width:var(--start)} to {width:var(--end)}}
.tdfc-progress {padding:12px 14px;border:1px solid #dce6df;border-radius:12px;
 background:rgba(100,150,110,.055);margin:10px 0 12px}
.tdfc-progress-title {display:flex;gap:12px;justify-content:space-between;
 font-size:.85rem;font-weight:700;margin-bottom:8px}
.tdfc-progress-track {height:10px;background:#e2e8e4;border-radius:999px;overflow:hidden}
.tdfc-progress-fill {height:10px;background:#239b65;border-radius:999px}
.tdfc-progress-note {font-size:.78rem;margin-top:5px;color:#53645d}
</style>
""", unsafe_allow_html=True)
    from standards_growth import NOT_CHECKED, LEARNING, GROWING, CONFIDENT
    label_rank = {NOT_CHECKED: 0, LEARNING: 1, GROWING: 2, CONFIDENT: 3}
    label_key = f"growth_display_label::{student_id}::{class_id}::{day.isoformat()}::{code}"
    shown_label = st.session_state.get(label_key, snapshot.label)
    if label_rank.get(snapshot.label, 0) > label_rank.get(shown_label, 0):
        shown_label = snapshot.label
    st.session_state[label_key] = shown_label
    label = html.escape(shown_label)
    display = html.escape(description or code)
    message = "Nice work — your understanding is growing!" if is_growing else "Each independent check helps show your learning."
    animation = ("animation:tdfc-standard-fill .75s ease-out both;" if is_growing else "")
    st.markdown(
        f'<div class="tdfc-progress" role="group" aria-label="{display} progress: {label}">'
        f'<div class="tdfc-progress-title"><span>{html.escape(code)} · Your progress</span><span>{label}</span></div>'
        f'<div class="tdfc-progress-track"><div class="tdfc-progress-fill" '
        f'style="--start:{start:.1f}%;--end:{visual:.1f}%;width:{visual:.1f}%;{animation}"></div></div>'
        f'<div class="tdfc-progress-note">{message}</div></div>', unsafe_allow_html=True,
    )


def render_fact_fluency_progress(store, student_id: str, *, day: date,
                                 before_challenge: bool) -> None:
    """Only the existing 45-core multiplication map, never alternate modes."""
    from adaptive_engine import STATUS_FLUENT
    view_key = f"fact_fluency_value::{student_id}::{day.isoformat()}"
    # Streamlit reruns for each of the ten answers; do not read Supabase ten
    # extra times to paint the same opening progress indicator.
    done_key = f"fact_fluency_after::{student_id}::{day.isoformat()}"
    if before_challenge and view_key in st.session_state:
        fluent = st.session_state[view_key]
    elif not before_challenge and done_key in st.session_state:
        fluent = st.session_state[done_key]
    else:
        try:
            fluent = int(store.mastery_summary(student_id).get(STATUS_FLUENT, 0))
        except Exception:
            return  # Supplemental visuals never block learning.
        st.session_state[view_key] = fluent
        if not before_challenge:
            st.session_state[done_key] = fluent
    key = f"fact_fluent_before::{student_id}::{day.isoformat()}"
    if before_challenge and key not in st.session_state:
        st.session_state[key] = fluent
    before = st.session_state.get(key)
    st.markdown("**🌱 Your Fact Fluency**")
    st.progress(fluent / 45)
    st.caption(f"{fluent} of 45 core multiplication facts fluent")
    if not before_challenge and isinstance(before, int) and fluent > before:
        gained = fluent - before
        st.success(f"You've gained {gained} fluent fact{'s' if gained != 1 else ''}!")
    elif before_challenge:
        st.caption("Let's see what you can do today!")
