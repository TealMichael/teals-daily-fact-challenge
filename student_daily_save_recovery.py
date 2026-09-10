from __future__ import annotations

"""Recover a finished browser-local Daily without trapping a student.

The browser components keep a completed Daily payload in localStorage, while
this module keeps a Streamlit-session copy before the first database mutation.
v2.20.3 adds server reconciliation: whenever a preserved payload exists, the
server is checked before that payload is trusted or retried. If the official
attempt is already complete, stale recovery state is discarded automatically.
"""

from typing import Mapping, Sequence

import streamlit as st

from fact_engine import Fact
from fact_store import utc_now
from supabase_fact_store import SupabaseFactStore


def _key(attempt_id: str) -> str:
    return f"pending_daily_save::{attempt_id}"


def _meta_key(attempt_id: str) -> str:
    return f"pending_daily_save_meta::{attempt_id}"


def _retry_count_key(attempt_id: str) -> str:
    return f"pending_daily_retry_count::{attempt_id}"


def _generation_key(attempt_id: str) -> str:
    return f"daily_browser_recovery_generation::{attempt_id}"


def pending_daily_payload(
    attempt_id: str, *, student_id: str | None = None, challenge_id: str | None = None
) -> dict | None:
    """Return a pending payload only when it belongs to the current Daily context.

    v2.20.1/v2.20.2 session payloads did not store metadata, so a legacy payload
    with the exact attempt id remains readable during an in-place deployment.
    New captures are additionally scoped to student + challenge.
    """
    aid = str(attempt_id)
    payload = st.session_state.get(_key(aid))
    if not (isinstance(payload, dict) and payload.get("status") == "complete"):
        return None

    meta = st.session_state.get(_meta_key(aid))
    if isinstance(meta, dict):
        if student_id is not None and str(meta.get("student_id") or "") != str(student_id):
            clear_pending_daily_payload(aid)
            return None
        if challenge_id is not None and str(meta.get("challenge_id") or "") != str(challenge_id):
            clear_pending_daily_payload(aid)
            return None
    return payload


def clear_pending_daily_payload(attempt_id: str) -> None:
    aid = str(attempt_id)
    st.session_state.pop(_key(aid), None)
    st.session_state.pop(_meta_key(aid), None)
    st.session_state.pop(_retry_count_key(aid), None)


def _capture(attempt_id: str, payload: Mapping) -> dict:
    aid = str(attempt_id)
    saved = dict(payload)
    st.session_state[_key(aid)] = saved
    return saved


def _scope_pending_daily_payload(attempt) -> None:
    aid = str(attempt.attempt_id)
    st.session_state[_meta_key(aid)] = {
        "student_id": str(getattr(attempt, "student_id", "") or ""),
        "challenge_id": str(getattr(attempt, "challenge_id", "") or ""),
    }


def daily_component_attempt_key(student_id: str, challenge_id: str, attempt_id: str) -> str:
    """Return the established browser storage key, changing it only after recovery reset.

    Generation zero deliberately returns the exact pre-v2.20.3 key so an ordinary
    deployment cannot erase a student's in-progress Daily. A confirmed-incomplete
    recovery reset increments the generation and therefore ignores the poisoned
    localStorage payload without touching the browser component implementation.
    """
    aid = str(attempt_id)
    base = f"{student_id}:{challenge_id}:{aid}"
    generation = int(st.session_state.get(_generation_key(aid), 0) or 0)
    return base if generation <= 0 else f"{base}:recovery-{generation}"


def _restart_daily_on_this_device(attempt_id: str) -> None:
    aid = str(attempt_id)
    generation = int(st.session_state.get(_generation_key(aid), 0) or 0) + 1
    clear_pending_daily_payload(aid)
    st.session_state[_generation_key(aid)] = generation


def _fresh_server_attempt(store: SupabaseFactStore, attempt):
    """Read the current server attempt, preferring a brand-new Supabase client.

    Returns ``(attempt_or_none, confirmed)``. ``confirmed`` is False only when
    both a fresh client and the supplied client could not read the server state.
    """
    student_id = str(getattr(attempt, "student_id", "") or "")
    challenge_id = str(getattr(attempt, "challenge_id", "") or "")
    if not student_id or not challenge_id:
        return None, False

    try:
        fresh_store = SupabaseFactStore.from_secrets(st.secrets)
        return fresh_store.get_attempt_for_student(student_id, challenge_id), True
    except Exception:
        try:
            return store.get_attempt_for_student(student_id, challenge_id), True
        except Exception:
            return None, False


def reconcile_pending_daily_attempt(store: SupabaseFactStore, attempt):
    """Self-heal a stale device/session recovery state against Supabase.

    This function is intentionally a no-op on the normal student path. It only
    performs a server read when a completed payload is being held for recovery.
    """
    aid = str(attempt.attempt_id)
    pending = pending_daily_payload(
        aid,
        student_id=str(getattr(attempt, "student_id", "") or ""),
        challenge_id=str(getattr(attempt, "challenge_id", "") or ""),
    )
    if pending is None:
        return attempt

    # The attempt already loaded by the page may itself prove completion.
    if getattr(attempt, "completed_at", None) is not None:
        clear_pending_daily_payload(aid)
        return attempt

    server_attempt, confirmed = _fresh_server_attempt(store, attempt)
    if not confirmed:
        return attempt

    # A teacher reset/reopen can replace the attempt. Never carry the old
    # device-local completion payload into the replacement attempt.
    if server_attempt is None or str(server_attempt.attempt_id) != aid:
        clear_pending_daily_payload(aid)
        return server_attempt if server_attempt is not None else attempt

    if getattr(server_attempt, "completed_at", None) is not None:
        clear_pending_daily_payload(aid)
    return server_attempt


def _render_retry(
    exc: Exception, *, attempt_id: str, button_key: str, allow_restart: bool = False
) -> None:
    # Keep diagnostics private and coarse: no student, question, answer, or PIN data.
    print(f"[TDFC connection] daily_save: {type(exc).__name__}", flush=True)
    aid = str(attempt_id)
    count_key = _retry_count_key(aid)
    failures = int(st.session_state.get(count_key, 0)) + 1
    st.session_state[count_key] = failures

    st.error("Your finished Daily has not finished saving yet.")
    st.caption(
        "Your 10 completed answers are safe on this device. "
        "Tap Try saving again — you do not need to redo the Daily 10."
    )
    if failures > 1:
        st.caption("The last retry still did not save. We checked the server before offering another retry.")
    if st.button("🔄 Try saving again", type="primary", use_container_width=True, key=button_key):
        st.session_state["tdfc_force_fresh_store_once"] = True
        st.rerun()

    # Never leave a student permanently trapped by one poisoned local payload.
    # This escape is shown only after the server positively confirms that today's
    # official attempt is still incomplete.
    if allow_restart and failures > 1:
        st.caption(
            "If this same save keeps failing, you can restart today's Daily on this device. "
            "Use this only after Try saving again has failed."
        )
        if st.button(
            "↩️ Start Daily 10 over on this device",
            use_container_width=True,
            key=f"restart_daily_device_{aid}",
        ):
            _restart_daily_on_this_device(aid)
            st.session_state["tdfc_force_fresh_store_once"] = True
            st.rerun()

    if str(st.query_params.get("dbcheck", "0")) == "1":
        st.exception(exc)


def _already_saved_or_restart_safe(store: SupabaseFactStore, attempt) -> tuple[object | None, bool]:
    """Check server after a save error. Return (server_attempt, confirmed_incomplete)."""
    server_attempt, confirmed = _fresh_server_attempt(store, attempt)
    if not confirmed:
        return None, False
    if server_attempt is not None and getattr(server_attempt, "completed_at", None) is not None:
        clear_pending_daily_payload(str(attempt.attempt_id))
        return server_attempt, False
    same_attempt = (
        server_attempt is not None
        and str(getattr(server_attempt, "attempt_id", "")) == str(attempt.attempt_id)
    )
    return server_attempt, bool(same_attempt)


def save_multiplication_daily(
    store: SupabaseFactStore,
    attempt,
    facts: Sequence[Fact],
    component_result: Mapping,
) -> bool:
    # A previous request may have committed successfully even if the browser never
    # received the response. Reconcile first so we never retry a result the server
    # already owns.
    if pending_daily_payload(
        str(attempt.attempt_id),
        student_id=str(getattr(attempt, "student_id", "") or ""),
        challenge_id=str(getattr(attempt, "challenge_id", "") or ""),
    ) is not None:
        reconciled = reconcile_pending_daily_attempt(store, attempt)
        if getattr(reconciled, "completed_at", None) is not None:
            return True
        attempt = reconciled

    payload = _capture(str(attempt.attempt_id), component_result)
    _scope_pending_daily_payload(attempt)
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
        server_attempt, confirmed_incomplete = _already_saved_or_restart_safe(store, attempt)
        if server_attempt is not None and getattr(server_attempt, "completed_at", None) is not None:
            return True
        _render_retry(
            exc,
            attempt_id=str(attempt.attempt_id),
            button_key=f"retry_daily_save_{attempt.attempt_id}",
            allow_restart=confirmed_incomplete,
        )
        return False
    clear_pending_daily_payload(str(attempt.attempt_id))
    return True


def save_alternate_daily(store: SupabaseFactStore, attempt, component_result: Mapping) -> bool:
    if pending_daily_payload(
        str(attempt.attempt_id),
        student_id=str(getattr(attempt, "student_id", "") or ""),
        challenge_id=str(getattr(attempt, "challenge_id", "") or ""),
    ) is not None:
        reconciled = reconcile_pending_daily_attempt(store, attempt)
        if getattr(reconciled, "completed_at", None) is not None:
            return True
        attempt = reconciled

    payload = _capture(str(attempt.attempt_id), component_result)
    _scope_pending_daily_payload(attempt)
    try:
        raw_answers = payload.get("answers")
        timed_seconds = float(payload.get("timed_seconds"))
        if not isinstance(raw_answers, list) or len(raw_answers) != 10:
            raise ValueError("Alternate Daily component returned an incomplete answer set.")
        values = [int(value) for value in raw_answers]
        if any(value < -999 or value > 999 for value in values):
            raise ValueError("Alternate Daily component returned an invalid answer.")

        store.complete_custom_attempt(
            attempt.attempt_id, values, timed_seconds, completed_at=utc_now(),
            attempt_record=attempt, defer_evidence=True,
        )
    except Exception as exc:
        server_attempt, confirmed_incomplete = _already_saved_or_restart_safe(store, attempt)
        if server_attempt is not None and getattr(server_attempt, "completed_at", None) is not None:
            return True
        _render_retry(
            exc,
            attempt_id=str(attempt.attempt_id),
            button_key=f"retry_alt_daily_save_{attempt.attempt_id}",
            allow_restart=confirmed_incomplete,
        )
        return False
    clear_pending_daily_payload(str(attempt.attempt_id))
    return True
