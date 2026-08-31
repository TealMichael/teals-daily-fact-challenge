from __future__ import annotations

"""Student UI for non-multiplication Daily 10 modes.

Kept outside app.py so alternate question types cannot drift the protected
multiplication Daily browser/component path.
"""

import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from daily_modes import ALT_DAILY_VERSION
from fact_store import utc_now
from supabase_fact_store import SupabaseFactStore

ALT_DAILY_COMPONENT = components.declare_component(
    "tdfc_alt_daily", path=str(Path(__file__).with_name("daily_alt_component"))
)


def _student_top10(store: SupabaseFactStore, challenge) -> dict:
    class_id = str(st.session_state.student_class_id)
    student_id = str(st.session_state.student_id)
    roster = store.list_students(class_id)
    try:
        completed = store.completed_attempts_for_class(class_id, challenge.challenge_id, students=roster)
    except TypeError:
        completed = store.completed_attempts_for_class(class_id, challenge.challenge_id)
    rows = [
        {"student_id": str(row["student_id"]), "nickname": str(row["nickname"]), "rank": index}
        for index, row in enumerate(completed[:10], start=1)
    ]
    return {"rows": rows, "finished": len(completed), "roster_count": len(roster), "student_id": student_id}


def _render_top10(context: dict) -> None:
    rows = list(context.get("rows") or [])
    own_id = str(context.get("student_id") or "")
    own = next((row for row in rows if row["student_id"] == own_id), None)
    st.markdown("## 🏆 Current Top 10")
    if own:
        st.success(f"🏆 You're #{own['rank']} in your class Top 10 right now!")
    else:
        st.info("You finished today's challenge! Only Top 10 places are shown, so lower exact ranks stay private.")
    st.caption(f"{int(context.get('finished') or 0)} of {int(context.get('roster_count') or 0)} finished · standings may change as classmates finish")
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}
    if not rows:
        st.info("No one has finished yet. The first completed challenge will start the board!")
        return
    html_rows = []
    for row in rows:
        rank = int(row["rank"])
        marker = medal.get(rank, str(rank))
        suffix = " · you" if row["student_id"] == own_id else ""
        html_rows.append(
            f'<div class="leader-row"><div class="leader-rank">{marker}</div>'
            f'<div class="leader-name">{html.escape(row["nickname"])}{suffix}</div></div>'
        )
    st.markdown('<div class="soft-card">' + "".join(html_rows) + "</div>", unsafe_allow_html=True)


def _render_review(attempt) -> None:
    with st.expander("📝 Review My Daily 10", expanded=False):
        for index, (question, value) in enumerate(zip(attempt.custom_questions, attempt.custom_answers), start=1):
            correct_answer = int(question.get("correct_answer"))
            correct = int(value) == correct_answer
            symbol = "✅" if correct else "❌"
            correction = "" if correct else f" · correct answer {correct_answer}"
            prompt = html.escape(str(question.get("prompt") or ""))
            st.markdown(
                f'<div class="soft-card"><strong>{symbol} {index}. {prompt}</strong><br>'
                f'You answered <strong>{int(value)}</strong>{correction}</div>', unsafe_allow_html=True,
            )


def render_alternate_daily(store: SupabaseFactStore, day, challenge, attempt, *, render_mystery_reward) -> None:
    questions = list(attempt.custom_questions or ())
    if len(questions) != 10:
        st.error("Today's Daily 10 did not load correctly. Show your teacher this screen.")
        return

    if attempt.completed_at is not None:
        answers = list(attempt.custom_answers or ())
        if len(answers) != 10:
            st.error("Today's results did not finish loading. Show your teacher this screen.")
            return
        try:
            context = _student_top10(store, challenge)
            st.markdown(
                "<div class='finish-banner'><div class='big'>✅ YOU'RE DONE FOR TODAY!</div>"
                f"<div class='sub'>{html.escape(str(attempt.daily_mode))} Daily 10 ✓</div>"
                "<div style='margin-top:.45rem'>This class is using a Daily-10-only mode today.</div></div>",
                unsafe_allow_html=True,
            )
            st.caption("Today's score counts toward your class Top 10.")
            st.markdown("## 🕵️ Today's Mystery Reward")
            render_mystery_reward(store, day, challenge, show_heading=False)
            _render_top10(context)
            st.markdown("### ✅ That's it — see you next Challenge day! 👋")
            _render_review(attempt)
        except Exception as exc:
            st.error("Your completed Daily is saved, but the finished screen could not fully load.")
            if st.button("Try again", type="primary", use_container_width=True, key="retry_alt_finished"):
                st.rerun()
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
        return

    st.caption("That's all for today — this mode does not include Fix Your Misses or Focus Practice.")
    st.markdown(
        "<div class='private-note'><strong>Question 1 is untimed.</strong> After you submit it, the hidden timer starts. Accuracy comes first.</div>",
        unsafe_allow_html=True,
    )
    result = ALT_DAILY_COMPONENT(
        questions=[{"prompt": str(item.get("prompt") or "")} for item in questions],
        attempt_key=f"{st.session_state.student_id}:{challenge.challenge_id}:{attempt.attempt_id}",
        daily_version=f"{ALT_DAILY_VERSION}:{attempt.daily_mode}", default=None, key=f"alt_daily_{attempt.attempt_id}",
    )
    if isinstance(result, dict) and result.get("status") == "complete":
        try:
            raw_answers = result.get("answers")
            timed_seconds = float(result.get("timed_seconds"))
            if not isinstance(raw_answers, list) or len(raw_answers) != 10:
                raise ValueError("Alternate Daily component returned an incomplete answer set.")
            values = [int(value) for value in raw_answers]
            if any(value < -999 or value > 999 for value in values):
                raise ValueError("Alternate Daily component returned an invalid answer.")
            store.complete_custom_attempt(attempt.attempt_id, values, timed_seconds, completed_at=utc_now())
            st.rerun()
        except Exception as exc:
            st.error("Your finished Daily could not be saved. Leave this page open and try once more; your answers are still here.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
