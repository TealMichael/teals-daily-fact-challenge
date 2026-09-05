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
from alternate_followup import missed_question_items
from alternate_teaching import teaching_plan_for_question
from alternate_focus import ALT_FOCUS_SESSION_LENGTH, build_alternate_focus_plan
from fact_store import utc_now
from supabase_fact_store import SupabaseFactStore

ALT_DAILY_COMPONENT = components.declare_component(
    "tdfc_alt_daily_v2195", path=str(Path(__file__).with_name("daily_alt_component"))
)
ALT_FIX_COMPONENT = components.declare_component(
    "tdfc_alt_fix_v2196", path=str(Path(__file__).with_name("alt_fix_component"))
)
ALT_FOCUS_COMPONENT = components.declare_component(
    "tdfc_alt_focus_v2196", path=str(Path(__file__).with_name("alt_focus_component"))
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
            # Mirror the proven multiplication completed-Daily guard: the official
            # completion path already applies/repairs learning evidence, so do not
            # re-upsert the same ten Daily evidence rows on every finished-page rerun.
            evidence_key = f"daily_evidence_verified::{attempt.attempt_id}"
            if not st.session_state.get(evidence_key, False):
                store.ensure_daily_learning_evidence(attempt.attempt_id)
                st.session_state[evidence_key] = True
            progress = store.get_alternate_learning_progress(
                attempt.student_id, attempt.challenge_id, str(attempt.daily_mode)
            )
            if progress is None:
                # Defensive repair for an unexpectedly missing progress row.
                progress = store.ensure_alternate_followup_state(attempt.attempt_id)

            missed = missed_question_items(
                questions, answers,
                default_domain=None if str(attempt.daily_mode) == "Mixed" else str(attempt.daily_mode),
            )
            had_daily_misses = bool(missed)
            if progress.completed_at is None and progress.fix_completed_at is None:
                if not missed:
                    progress = store.mark_alternate_fix_complete(
                        attempt.student_id, attempt.challenge_id, str(attempt.daily_mode)
                    )
                else:
                    st.success("✅ Daily 10 complete!")
                    st.markdown("### Next: Fix Your Misses")
                    st.caption(f"You have {len(missed)} question{'s' if len(missed) != 1 else ''} to fix.")
                    model_items = []
                    for item in missed:
                        question = questions[int(item["question_number"]) - 1]
                        plan = teaching_plan_for_question(
                            question, None if str(attempt.daily_mode) == "Mixed" else str(attempt.daily_mode)
                        )
                        model_items.append({
                            "question_number": int(item["question_number"]),
                            "prompt": str(item["prompt"]),
                            "original_answer": int(item["original_answer"]),
                            "correct_answer": int(item["correct_answer"]),
                            "domain": str(item["domain"]),
                            "model": plan.as_dict(),
                        })
                    result = ALT_FIX_COMPONENT(
                        items=model_items,
                        attempt_key=f"{attempt.attempt_id}:fix",
                        version="TDFC-ALT-FIX-v3",
                        default=None,
                        key=f"alt_fix_{attempt.attempt_id}",
                    )
                    if isinstance(result, dict) and result.get("status") == "complete":
                        corrections = list(result.get("corrections") or [])
                        store.record_alternate_fix_batch(attempt.attempt_id, corrections)
                        st.rerun()
                    st.caption("After your fixes, you'll finish 8 personalized Focus questions.")
                    return

            # v2.19: alternate modes now match multiplication's Step 3 rhythm.
            if progress.completed_at is None and progress.focus_completed_at is None:
                if not progress.focus_plan:
                    history = store.recent_alternate_learning_events(attempt.student_id, limit=500)
                    focus_plan = build_alternate_focus_plan(
                        str(attempt.daily_mode), questions, answers, history,
                        student_id=str(attempt.student_id), date_key=day.isoformat(),
                    )
                    progress = store.set_alternate_focus_plan(
                        attempt.student_id, attempt.challenge_id, str(attempt.daily_mode), focus_plan
                    )

                plan_items = list(progress.focus_plan or ())
                if len(plan_items) != ALT_FOCUS_SESSION_LENGTH:
                    st.error("Your Focus Practice isn't ready yet. Show your teacher and they can refresh it.")
                    return
                focus_rows = store.alternate_learning_activity_rows(
                    attempt.student_id, attempt.challenge_id, "focus"
                )
                remaining_items = []
                for index, question in enumerate(plan_items, start=1):
                    slot = [row for row in focus_rows if int(row.activity_index) == index]
                    first = next((row for row in slot if not row.is_retry), None)
                    corrected = first is not None and (first.correct or any(row.is_retry and row.correct for row in slot))
                    if corrected:
                        continue
                    teach = teaching_plan_for_question(
                        question, None if str(attempt.daily_mode) == "Mixed" else str(attempt.daily_mode)
                    )
                    remaining_items.append({
                        "activity_index": index,
                        "prompt": str(question.get("prompt") or ""),
                        "correct_answer": int(question.get("correct_answer")),
                        "domain": str(question.get("domain") or question.get("category") or attempt.daily_mode),
                        "focus_reason": str(question.get("focus_reason") or "Build fluency"),
                        "model": teach.as_dict(),
                        "start_phase": "coach" if first is not None and not first.correct else "question",
                        "attempt_offset": len(slot),
                    })
                if not remaining_items:
                    progress = store.mark_alternate_focus_complete(
                        attempt.student_id, attempt.challenge_id, str(attempt.daily_mode)
                    )
                    st.rerun()

                st.success("✅ Fix Your Misses complete!" if had_daily_misses else "✅ Daily 10 complete!")
                st.markdown("### Next: Focus Practice")
                st.caption("8 personalized questions. If one is tricky, you'll see the same kind of teaching model before you try again.")
                result = ALT_FOCUS_COMPONENT(
                    items=remaining_items,
                    session_key=f"{attempt.attempt_id}:focus",
                    version="TDFC-ALT-FOCUS-v2",
                    default=None,
                    key=f"alt_focus_{attempt.attempt_id}",
                )
                if isinstance(result, dict) and result.get("status") == "complete":
                    events = list(result.get("events") or [])
                    store.record_alternate_focus_batch(attempt.attempt_id, events)
                    st.rerun()
                st.caption("Your Mystery reward unlocks after Focus Practice.")
                return

            context = _student_top10(store, challenge)
            st.markdown(
                "<div class='finish-banner'><div class='big'>✅ YOU'RE DONE FOR TODAY!</div>"
                f"<div class='sub'>{html.escape(str(attempt.daily_mode))} Daily 10 ✓ &nbsp; · &nbsp; Fix Your Misses ✓ &nbsp; · &nbsp; Focus Practice ✓</div>"
                "<div style='margin-top:.45rem'>Your learning work is finished for today.</div></div>",
                unsafe_allow_html=True,
            )
            st.caption("Today's score counts toward your class Top 10.")
            st.markdown("## 🕵️ Today's Mystery Reward")
            render_mystery_reward(store, day, challenge, show_heading=False)
            _render_top10(context)
            st.markdown("### ✅ That's it — see you next Challenge day! 👋")
            _render_review(attempt)
        except Exception as exc:
            st.error("Your completed Daily is saved, but this next step could not fully load.")
            if st.button("Try again", type="primary", use_container_width=True, key="retry_alt_finished"):
                st.rerun()
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)
        return

    st.caption("Finish all 10, fix any misses, then complete 8 personalized Focus questions.")
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
