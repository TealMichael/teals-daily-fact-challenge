from __future__ import annotations

"""Recover a finished browser-local Daily when its first Supabase save fails.

The browser components already keep their completed payload in localStorage.
This module adds a Streamlit-session copy before the first database mutation.
A retry also requests a fresh Supabase client on the next run so a wedged pooled
connection is not reused indefinitely.
"""

from typing import Mapping, Sequence

import streamlit as st

from fact_engine import Fact
from fact_store import utc_now
from supabase_fact_store import SupabaseFactStore


def _key(attempt_id: str) -> str:
    return f"pending_daily_save::{attempt_id}"


def _retry_count_key(attempt_id: str) -> str:
    return f"pending_daily_retry_count::{attempt_id}"


def pending_daily_payload(attempt_id: str) -> dict | None:
    payload = st.session_state.get(_key(attempt_id))
    if isinstance(payload, dict) and payload.get("status") == "complete":
        return payload
    return None


def clear_pending_daily_payload(attempt_id: str) -> None:
    st.session_state.pop(_key(attempt_id), None)
    st.session_state.pop(_retry_count_key(attempt_id), None)


def _capture(attempt_id: str, payload: Mapping) -> dict:
    saved = dict(payload)
    st.session_state[_key(attempt_id)] = saved
    return saved


def _render_retry(exc: Exception, *, attempt_id: str, button_key: str) -> None:
    # Keep diagnostics private and coarse: no student, question, answer, or PIN data.
    print(f"[TDFC connection] daily_save: {type(exc).__name__}", flush=True)
    count_key = _retry_count_key(attempt_id)
    failures = int(st.session_state.get(count_key, 0)) + 1
    st.session_state[count_key] = failures

    st.error("Your finished Daily has not finished saving yet.")
    st.caption(
        "Your 10 completed answers are safe on this device. "
        "Tap Try saving again — you do not need to redo the Daily 10."
    )
    if failures > 1:
        st.caption("The last retry still could not reach the save service. The next try will use a fresh connection.")
    if st.button("🔄 Try saving again", type="primary", use_container_width=True, key=button_key):
        # The previous v2.20.1 button merely reran the same cached Supabase client.
        # Ask app.py to build a one-run fresh client before retrying the preserved payload.
        st.session_state["tdfc_force_fresh_store_once"] = True
        st.rerun()
    if str(st.query_params.get("dbcheck", "0")) == "1":
        st.exception(exc)


def save_multiplication_daily(
    store: SupabaseFactStore,
    attempt,
    facts: Sequence[Fact],
    component_result: Mapping,
) -> bool:
    payload = _capture(str(attempt.attempt_id), component_result)
    try:
        raw_answers = payload.get("answers")
        raw_first_answers = payload.get("first_answers")
        raw_response_seconds = payload.get("response_seconds")
        timed_seconds = float(payload.get("timed_seconds"))
        if not isinstance(raw_answers, list) or len(raw_answers) != 10:
            raise ValueError("Daily component returned an incomplete answer set.")
        values = [int(value) for value in raw_answers]
        if not isinstance(raw_first_answers, list) or len(raw_first_answers) != 10:
            raw_first_answers = raw_answers
        first_values = [int(value) for value in raw_first_answers]
        if not isinstance(raw_response_seconds, list) or len(raw_response_seconds) != 10:
            raw_response_seconds = [None] * 10
        response_seconds = [None if value is None else float(value) for value in raw_response_seconds]
        if any(value < 0 or value > 200 for value in values):
            raise ValueError("Daily component returned an invalid answer.")

        # Make the official result durable first.  Do not make mastery/follow-up
        # bookkeeping part of the classroom-critical save transaction.
        store.complete_full_attempt(
            attempt.attempt_id,
            list(zip(facts, values)),
            timed_seconds,
            response_seconds=response_seconds,
            first_answers=list(zip(facts, first_values)),
            completed_at=utc_now(),
            attempt_record=attempt,
            defer_evidence=True,
        )
    except Exception as exc:
        _render_retry(
            exc,
            attempt_id=str(attempt.attempt_id),
            button_key=f"retry_daily_save_{attempt.attempt_id}",
        )
        return False
    clear_pending_daily_payload(str(attempt.attempt_id))
    return True


def save_alternate_daily(store: SupabaseFactStore, attempt, component_result: Mapping) -> bool:
    payload = _capture(str(attempt.attempt_id), component_result)
    try:
        raw_answers = payload.get("answers")
        timed_seconds = float(payload.get("timed_seconds"))
        if not isinstance(raw_answers, list) or len(raw_answers) != 10:
            raise ValueError("Alternate Daily component returned an incomplete answer set.")
        values = [int(value) for value in raw_answers]
        if any(value < -999 or value > 999 for value in values):
            raise ValueError("Alternate Daily component returned an invalid answer.")

        # Alternate official completion is one database mutation. Follow-up rows
        # are repaired immediately after the completed attempt reloads.
        store.complete_custom_attempt(
            attempt.attempt_id, values, timed_seconds, completed_at=utc_now(),
            attempt_record=attempt, defer_evidence=True,
        )
    except Exception as exc:
        _render_retry(
            exc,
            attempt_id=str(attempt.attempt_id),
            button_key=f"retry_alt_daily_save_{attempt.attempt_id}",
        )
        return False
    clear_pending_daily_payload(str(attempt.attempt_id))
    return True
