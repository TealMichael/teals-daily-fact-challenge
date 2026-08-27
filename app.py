from __future__ import annotations

from datetime import datetime, timezone, timedelta
import html
import hmac
import random
import time
from pathlib import Path

import pandas as pd
import httpx
import streamlit as st
import streamlit.components.v1 as components

from fact_engine import (
    APP_VERSION,
    CHALLENGE_VERSION,
    Fact,
    current_daily_date,
    daily_facts_for_date,
    daily_mix_summary,
    fact_family_options,
    practice_fact,
    repeated_addition_text,
    validate_daily_facts,
)
from fact_store import NameTaken, generate_pin, utc_now
from fact_coach import coach_plan_for_fact
from adaptive_engine import (
    FOCUS_SESSION_LENGTH,
    STATUS_BUILDING,
    STATUS_FLUENT,
    STATUS_FOCUS,
    STATUS_UNKNOWN,
    build_focus_plan,
)
from supabase_fact_store import SupabaseFactStore
from persistent_login import REMEMBER_DAYS, issue_student_token, peek_student_id, verify_student_token
from ui_helpers import format_seconds, strategy_tip
from student_igniter_ui import render_quick_warmup
from daily_modes import configured_daily_mode, questions_for_mode
from student_alt_daily_ui import render_alternate_daily
from teacher_daily_setup_ui import render_teacher_daily_setup
from teacher_learning_ui import render_teacher_mastery_focus, _override_label, _override_value
from teacher_warmup_ui import render_teacher_warmup as _render_teacher_warmup_module
from teacher_warmup_ui import _render_warmup_groups_and_email
from teacher_clock_ui import render_teacher_clock, queue_clock_top10_for_class
from weekly_mystery import (
    MYSTERIES,
    default_mystery_key_for_week,
    is_correct_guess,
    learning_paragraph_for,
    mystery_for_key,
    mystery_from_plan,
    mystery_to_plan,
    next_mystery_key,
    school_day_number,
    week_start_for,
)

st.set_page_config(
    page_title="Teal's Daily Fact Challenge",
    page_icon="✖️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

DAILY_SPRINT_COMPONENT = components.declare_component(
    "tdfc_daily_sprint",
    path=str(Path(__file__).with_name("daily_sprint_component")),
)

PERSISTENT_LOGIN_COMPONENT = components.declare_component(
    "tdfc_persistent_login",
    path=str(Path(__file__).with_name("persistent_login_component")),
)

ANSWER_PAD_COMPONENT = components.declare_component(
    "tdfc_answer_pad",
    path=str(Path(__file__).with_name("answer_pad_component")),
)

GUIDED_PRACTICE_COMPONENT = components.declare_component(
    "tdfc_guided_practice",
    path=str(Path(__file__).with_name("guided_practice_component")),
)

PIN_ENTRY_COMPONENT = components.declare_component(
    "tdfc_student_pin",
    path=str(Path(__file__).with_name("pin_entry_component")),
)

def render_student_pin(*, key: str) -> tuple[str, bool]:
    """Return a completed PIN only when the student explicitly taps the keypad check."""
    result = PIN_ENTRY_COMPONENT(key=key, default=None)
    if not isinstance(result, dict) or not result.get("submitted"):
        return "", False
    cleaned = "".join(ch for ch in str(result.get("pin") or "") if ch.isdigit())[:4]
    nonce = str(result.get("nonce") or "")
    nonce_key = f"student_pin_submit_nonce::{key}"
    if len(cleaned) != 4 or not nonce or st.session_state.get(nonce_key) == nonce:
        return "", False
    st.session_state[nonce_key] = nonce
    return cleaned, True

def render_number_pad(*, key: str) -> tuple[int, float] | None:
    """Browser-local touch keypad; digit taps never rerun Streamlit."""
    result = ANSWER_PAD_COMPONENT(key=key, default=None)
    if not isinstance(result, dict) or result.get("answer") is None:
        return None
    try:
        value = int(result["answer"])
        latency = max(0.0, float(result.get("response_seconds") or 0.0))
    except (TypeError, ValueError):
        return None
    if value < 0 or value > 200:
        return None
    nonce = str(result.get("nonce") or f"{value}:{latency}")
    processed_key = f"answer_pad_processed::{key}"
    if st.session_state.get(processed_key) == nonce:
        return None
    st.session_state[processed_key] = nonce
    return value, latency

def render_guided_practice(*, key: str, mode: str, session_key: str, items: list[dict], step_label: str, done_title: str) -> list[dict] | None:
    """Run a whole Fix/Focus mini-session in the browser and return one evidence batch.

    Digit taps, feedback, arrays, retries, and question-to-question navigation stay
    browser-local. Streamlit receives one payload only when the whole step ends.
    """
    result = GUIDED_PRACTICE_COMPONENT(
        mode=mode,
        session_key=session_key,
        items=items,
        step_label=step_label,
        done_title=done_title,
        key=key,
        default=None,
    )
    if not isinstance(result, dict) or not result.get("submitted"):
        return None
    events = result.get("events")
    if not isinstance(events, list):
        return None
    nonce = str(result.get("nonce") or "")
    processed_key = f"guided_practice_processed::{session_key}"
    if nonce and st.session_state.get(processed_key) == nonce:
        return None
    if nonce:
        st.session_state[processed_key] = nonce
    cleaned: list[dict] = []
    for raw in events:
        if not isinstance(raw, dict):
            continue
        try:
            activity_index = int(raw["activity_index"])
            a = int(raw["a"]); b = int(raw["b"]); answer = int(raw["student_answer"])
            latency = max(0.0, float(raw.get("response_seconds") or 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        if not (2 <= a <= 12 and 2 <= b <= 12 and 0 <= answer <= 200):
            continue
        event_id = str(raw.get("client_event_id") or "").strip()
        if not event_id:
            continue
        cleaned.append({
            "client_event_id": event_id[:180],
            "activity_index": activity_index,
            "a": a, "b": b,
            "student_answer": answer,
            "response_seconds": latency,
            "is_retry": bool(raw.get("is_retry")),
        })
    return cleaned

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.7rem;
        padding-bottom: 2.5rem;
        max-width: 760px;
    }
    h1, h2, h3 { letter-spacing: -0.035em; }
    .top-title { text-align:center; margin:0.05rem 0 0.05rem 0; font-weight:950; }
    .subtitle { text-align:center; color:#6b7280; font-size:0.96rem; margin:-0.15rem 0 0.75rem 0; }
    .tiny-muted { color:#6b7280; font-size:0.82rem; }
    .center { text-align:center; }

    .soft-card {
        border:1px solid rgba(15,118,110,0.16);
        border-radius:20px;
        padding:0.9rem 1rem;
        background:#ffffff;
        box-shadow:0 2px 12px rgba(0,0,0,0.045);
        margin:0.55rem 0;
        color:#111827 !important;
    }
    .soft-card * { color:inherit; }
    .hero-card {
        border:1px solid #99f6e4;
        border-radius:22px;
        padding:1rem;
        background:linear-gradient(180deg,#f0fdfa 0%,#ffffff 100%);
        margin:0.7rem 0;
        color:#111827 !important;
    }
    .hero-card * { color:inherit; }
    .mystery-win-card {
        border:2px solid #f59e0b;
        border-radius:24px;
        padding:1.15rem 1rem;
        background:linear-gradient(180deg,#fffbeb 0%,#ffffff 100%);
        margin:0.75rem 0 0.9rem 0;
        color:#111827 !important;
    }
    .mystery-win-kicker { font-size:1.05rem; font-weight:950; letter-spacing:0.01em; }
    .mystery-win-answer { font-size:clamp(2rem,8vw,3.2rem); font-weight:950; margin-top:0.35rem; color:#92400e; }
    .mystery-win-title { font-size:1.1rem; font-weight:900; margin-top:0.35rem; }
    .mystery-win-detail { font-size:0.98rem; margin-top:0.25rem; color:#4b5563; }
    .section-label {
        color:#6b7280;
        font-size:0.77rem;
        text-transform:uppercase;
        letter-spacing:0.06em;
        font-weight:850;
        margin:0.75rem 0 0.28rem 0;
    }
    .fact-big {
        font-size:clamp(2.8rem,10vw,4.8rem);
        font-weight:950;
        letter-spacing:-0.055em;
        text-align:center;
        line-height:1.03;
        margin:0.55rem 0 0.7rem 0;
        color:#0f766e;
    }
    .fact-row {
        border:1px solid #d1d5db;
        border-radius:16px;
        padding:0.55rem 0.7rem;
        margin:0.35rem 0;
        background:#ffffff;
        color:#111827 !important;
        font-weight:850;
    }
    .result-grid {
        display:grid;
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:0.5rem;
        margin:0.6rem 0;
    }
    .result-box {
        border:1px solid #d1d5db;
        border-radius:16px;
        padding:0.72rem 0.5rem;
        background:#f9fafb;
        text-align:center;
        color:#111827 !important;
    }
    .result-label { color:#6b7280 !important; font-size:0.76rem; font-weight:800; text-transform:uppercase; letter-spacing:0.05em; }
    .result-value { color:#111827 !important; font-size:1.55rem; font-weight:950; line-height:1.15; }

    .progress-row { display:flex; gap:0.28rem; margin:0.55rem 0 0.8rem 0; }
    .progress-seg { height:0.55rem; flex:1; border-radius:999px; background:#e5e7eb; }
    .progress-seg.done { background:#14b8a6; }
    .progress-seg.current { background:#99f6e4; }

    .routine-strip {
        display:grid;
        grid-template-columns:repeat(4,minmax(0,1fr));
        gap:0.42rem;
        margin:0.65rem 0 0.9rem 0;
    }
    .routine-step {
        border:1px solid #d1d5db;
        border-radius:14px;
        padding:0.55rem 0.4rem;
        background:#f9fafb;
        color:#6b7280 !important;
        text-align:center;
        font-size:0.78rem;
        font-weight:850;
        line-height:1.15;
    }
    .routine-step.done { border-color:#5eead4; background:#f0fdfa; color:#115e59 !important; }
    .routine-step.current { border-color:#14b8a6; background:#ccfbf1; color:#115e59 !important; }
    .routine-step.reward { border-color:#facc15; background:#fefce8; color:#854d0e !important; }
    .finish-banner {
        border:2px solid #14b8a6;
        border-radius:24px;
        padding:1.15rem 1rem;
        background:linear-gradient(180deg,#ccfbf1 0%,#ffffff 100%);
        text-align:center;
        margin:0.75rem 0 0.85rem 0;
        color:#111827 !important;
    }
    .finish-banner .big { font-size:clamp(1.8rem,6vw,2.7rem); font-weight:950; line-height:1.03; }
    .finish-banner .sub { margin-top:0.45rem; font-size:1rem; font-weight:800; }

    .timer-pill {
        display:inline-block;
        border:1px solid #99f6e4;
        background:#f0fdfa;
        color:#115e59;
        border-radius:999px;
        padding:0.28rem 0.65rem;
        font-size:0.84rem;
        font-weight:850;
        margin:0.1rem 0 0.5rem 0;
    }
    .leader-row {
        display:grid;
        grid-template-columns:2.2rem 1fr;
        align-items:center;
        gap:0.5rem;
        border-bottom:1px solid #e5e7eb;
        padding:0.5rem 0.1rem;
        color:#111827 !important;
    }
    .leader-rank { font-size:1.03rem; font-weight:950; text-align:center; }
    .leader-name { font-weight:850; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

    .answer-correct { border-left:5px solid #16a34a; }
    .answer-miss { border-left:5px solid #dc2626; }

    .array-shell {
        overflow-x:auto;
        padding:0.5rem 0.15rem 0.2rem 0.15rem;
        text-align:center;
    }
    .array-grid {
        display:grid;
        gap:4px;
        width:max-content;
        margin:0 auto;
        padding:0.65rem;
        border-radius:16px;
        background:#f0fdfa;
        border:1px solid #99f6e4;
    }
    .array-dot {
        width:16px;
        height:16px;
        border-radius:5px;
        background:#0f766e;
        box-shadow:inset 0 0 0 1px rgba(255,255,255,0.35);
    }
    .teach-line { text-align:center; font-weight:850; font-size:1.06rem; margin:0.45rem 0 0.1rem 0; }
    .teach-sub { text-align:center; color:#4b5563; margin:0.1rem 0 0.3rem 0; }

    .private-note {
        border-radius:16px;
        padding:0.65rem 0.75rem;
        background:#f3f4f6;
        color:#374151 !important;
        font-size:0.9rem;
        margin:0.55rem 0;
    }
    @media (max-width: 520px) {
        .block-container { padding-left:0.85rem; padding-right:0.85rem; }
        .result-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        .leader-row { grid-template-columns:2rem 1fr; }
        .array-dot { width:14px; height:14px; }
        .routine-strip { grid-template-columns:repeat(2,minmax(0,1fr)); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Store / session helpers
# ---------------------------------------------------------------------------
def database_configured() -> bool:
    try:
        return bool(st.secrets.get("SUPABASE_URL")) and bool(st.secrets.get("SUPABASE_SECRET_KEY"))
    except Exception:
        return False

@st.cache_resource(show_spinner=False)
def load_store(app_version: str) -> SupabaseFactStore:
    # Include the app version in the cache key. Streamlit Cloud can preserve a
    # cached resource across a hot deployment; without a versioned key the new
    # app can receive an instance of the *previous* SupabaseFactStore class.
    # That became visible in v2.10 when the new Warm-Up methods were added.
    _ = app_version
    return SupabaseFactStore.from_secrets(st.secrets)

def get_store() -> SupabaseFactStore | None:
    if not database_configured():
        return None
    try:
        store = load_store(APP_VERSION)
        # Defensive recovery for any stale pre-v2.10 resource that survives a
        # deployment despite the versioned cache key. Rebuild before rendering
        # so Teacher Today / student Warm-Up never sees a half-upgraded store.
        required = ("get_warmup_set", "get_warmup_answers", "list_warmup_answers")
        if not all(hasattr(store, name) for name in required):
            load_store.clear()
            store = load_store(APP_VERSION)
        return store
    except Exception:
        return None

def _timed_app_call(label: str, operation, *, log_after_seconds: float = 1.0):
    """Run one app operation and emit a privacy-safe timing line only when it is slow.

    The log deliberately contains no nickname, class name, PIN, question, or answer.
    It gives us something useful to inspect in Streamlit Cloud after an intermittent
    spinner instead of guessing whether startup, Supabase, or a page render stalled.
    """
    started = time.perf_counter()
    try:
        return operation()
    finally:
        elapsed = time.perf_counter() - started
        if elapsed >= float(log_after_seconds):
            print(f"[TDFC timing] {label}: {elapsed:.2f}s", flush=True)

def teacher_password_configured() -> bool:
    try:
        return bool(str(st.secrets.get("TEACHER_PASSWORD") or "").strip())
    except Exception:
        return False

def init_state() -> None:
    defaults = {
        "app_mode": "Daily Challenge",
        "student_id": None,
        "student_nickname": None,
        "student_class_id": None,
        "student_class_name": None,
        "teacher_authed": False,
        "practice_fact": None,
        "practice_result": None,
        "practice_recent": [],
        "practice_focus_last": None,
        "practice_focus_queue": [],
        "practice_focus_queue_batch": 0,
        "student_nav": "Today",
        "teacher_section": "📊 Today",
        "bulk_created_credentials": None,
        "practice_retry_correct": False,
        "practice_retry_count": 0,
        "practice_question_serial": 0,
        "practice_started_at": None,
        "fix_feedback": None,
        "focus_feedback": None,
        "focus_started_at": None,
        "persistent_login_pending_action": None,
        "persistent_login_check_complete": False,
        "persistent_login_reader_nonce": 0,
        "persistent_login_restore_error": None,
        "warmup_feedback": None,
        "warmup_just_completed": None,
        "teacher_warmup_export_ready": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

def switch_mode(mode: str) -> None:
    st.session_state.app_mode = mode
    if mode == "Daily Challenge":
        st.session_state.student_nav = "Today"
    elif mode == "Practice":
        st.session_state.student_nav = "Practice"

def switch_student_nav() -> None:
    """Keep the fifth-grade navigation simple while preserving the internal mode names."""
    st.session_state.app_mode = "Daily Challenge" if st.session_state.student_nav == "Today" else "Practice"

def sign_out() -> None:
    st.session_state.persistent_login_pending_action = {"action": "clear"}
    st.session_state.persistent_login_check_complete = False
    for key in ("student_id", "student_nickname", "student_class_id", "student_class_name", "student_is_test"):
        st.session_state[key] = None
    st.session_state.practice_result = None

def _persistent_login_secret() -> str:
    try:
        return str(st.secrets.get("SUPABASE_SECRET_KEY") or "")
    except Exception:
        return ""

def _set_student_session(student, class_record) -> None:
    st.session_state.student_id = student.student_id
    st.session_state.student_nickname = student.nickname
    st.session_state.student_class_id = student.class_id
    st.session_state.student_class_name = class_record.class_name
    st.session_state.student_is_test = bool(getattr(student, "is_test", False))

def handle_persistent_student_login(store: SupabaseFactStore | None) -> None:
    """Read/write the optional 30-day browser login token.

    The browser stores only a signed token, never the PIN itself. Every restore
    re-checks the current student record so deleted/deactivated students stop
    working, and a PIN reset invalidates the older token.
    """
    pending = st.session_state.get("persistent_login_pending_action")
    if pending:
        action = str(pending.get("action") or "")
        token = str(pending.get("token") or "")
        result = PERSISTENT_LOGIN_COMPONENT(
            action=action,
            token=token,
            default={"ready": False},
            key=f"persistent_login_{action}_{abs(hash(token)) if token else 'empty'}",
        )
        if isinstance(result, dict) and result.get("ready"):
            st.session_state.persistent_login_pending_action = None
            if action == "clear":
                st.session_state.persistent_login_reader_nonce = int(st.session_state.get("persistent_login_reader_nonce", 0)) + 1
                st.session_state.persistent_login_check_complete = True
        return

    if student_signed_in() or store is None:
        st.session_state.persistent_login_check_complete = True
        return

    result = PERSISTENT_LOGIN_COMPONENT(
        action="read",
        token="",
        default={"ready": False},
        key=f"persistent_login_reader_{st.session_state.get('persistent_login_reader_nonce', 0)}",
    )
    if not isinstance(result, dict) or not result.get("ready"):
        st.session_state.persistent_login_check_complete = False
        return

    st.session_state.persistent_login_check_complete = True
    token = str(result.get("token") or "")
    if not token:
        return

    try:
        # The signed payload tells us which student to load; validation still
        # requires the student's current visible PIN and active class/account.
        # v2.11.0.3 keeps the student + class restore in one PostgREST read instead
        # of loading the student and then the entire class list.
        student_id = peek_student_id(token)
        if not student_id:
            raise ValueError("Missing student id")
        student, class_record = _timed_app_call(
            "remembered_login_db",
            lambda: store.get_student_login_context(student_id),
            log_after_seconds=0.75,
        )
        if not student.active or not class_record.active:
            raise ValueError("Inactive student or class")
        payload = verify_student_token(token, student.pin_code, _persistent_login_secret())
        if payload is None:
            raise ValueError("Expired or invalid remembered login")
        _set_student_session(student, class_record)
        st.session_state.persistent_login_restore_error = None
        st.rerun()
    except Exception as exc:
        if _is_transient_classroom_error(exc):
            # A temporary network problem should never erase a valid 30-day token.
            # Let the student sign in manually now or retry the saved sign-in.
            st.session_state.persistent_login_restore_error = (
                "The saved sign-in is taking longer than usual. You can try it again or sign in below."
            )
            st.session_state.persistent_login_check_complete = True
            return
        st.session_state.persistent_login_restore_error = None
        st.session_state.persistent_login_pending_action = {"action": "clear"}
        st.session_state.persistent_login_check_complete = False
        st.rerun()

def student_signed_in() -> bool:
    return bool(st.session_state.student_id and st.session_state.student_class_id)

def parse_answer(value: str) -> int:
    text = str(value or "").strip()
    if not text or not text.isdigit():
        raise ValueError("Enter a whole-number answer.")
    number = int(text)
    if not 0 <= number <= 200:
        raise ValueError("Enter a reasonable whole-number answer.")
    return number

def progress_bar(completed: int, total: int = 10, current: int | None = None) -> None:
    cells = []
    for index in range(1, total + 1):
        cls = "progress-seg done" if index <= completed else "progress-seg"
        if current is not None and index == current and index > completed:
            cls = "progress-seg current"
        cells.append(f'<div class="{cls}"></div>')
    st.markdown('<div class="progress-row">' + "".join(cells) + "</div>", unsafe_allow_html=True)

def render_routine_strip(stage: str) -> None:
    """Make the four-part student path obvious without turning Mystery into required work."""
    stages = ["daily", "fix", "focus", "mystery"]
    labels = {
        "daily": "1 · Daily 10",
        "fix": "2 · Fix Misses",
        "focus": "3 · Focus",
        # v2.3 legacy label was "4 · Mystery"; v2.9.1 makes clear it is a reward, not Step 4.
        "mystery": "Mystery Reward",
    }
    current_index = stages.index(stage) if stage in stages else 0
    cells = []
    for index, key in enumerate(stages):
        if index < current_index:
            cls = "routine-step done"
            prefix = "✓ "
        elif index == current_index:
            cls = "routine-step reward" if key == "mystery" else "routine-step current"
            prefix = "★ " if key == "mystery" else "→ "
        else:
            cls = "routine-step"
            prefix = "🔒 "
        cells.append(f'<div class="{cls}">{prefix}{labels[key]}</div>')
    st.markdown('<div class="routine-strip">' + "".join(cells) + "</div>", unsafe_allow_html=True)

def render_array(fact: Fact) -> None:
    columns = fact.b
    cells = "".join('<div class="array-dot"></div>' for _ in range(fact.a * fact.b))
    st.markdown(
        f"""
        <div class="array-shell">
            <div class="array-grid" style="grid-template-columns:repeat({columns},16px);">
                {cells}
            </div>
        </div>
        <div class="teach-line">{fact.a} rows of {fact.b} = {fact.product}</div>
        <div class="teach-sub">{html.escape(repeated_addition_text(fact))}</div>
        """,
        unsafe_allow_html=True,
    )

def render_header() -> str:
    st.markdown("<h1 class='top-title'>Teal's Daily Fact Challenge</h1>", unsafe_allow_html=True)
    st.markdown("<div class='subtitle'>10 facts a day · accuracy first · speed breaks ties</div>", unsafe_allow_html=True)

    signed_in = student_signed_in()
    mode = st.session_state.app_mode

    # Before sign-in there are only two paths: student sign-in or Teacher.
    # Today / Practice becomes meaningful only after we know which student is here.
    if not signed_in and mode != "Teacher":
        st.session_state.app_mode = "Daily Challenge"
        st.session_state.student_nav = "Today"
        mode = "Daily Challenge"

    if signed_in and mode != "Teacher":
        nav_col, teacher_col = st.columns([5.2, 1.35])
        with nav_col:
            st.radio(
                "Student navigation", ["Today", "Practice"], horizontal=True,
                label_visibility="collapsed", key="student_nav", on_change=switch_student_nav,
            )
        with teacher_col:
            if st.button("🔒 Teacher", use_container_width=True, key="open_teacher_nav"):
                st.session_state.app_mode = "Teacher"
                st.rerun()

        left, right = st.columns([5, 1.4])
        with left:
            st.caption(f"👤 {st.session_state.student_nickname} · {st.session_state.student_class_name}")
        with right:
            st.button("Sign out", use_container_width=True, on_click=sign_out)
    elif mode != "Teacher":
        _, teacher_col = st.columns([5.2, 1.35])
        with teacher_col:
            if st.button("🔒 Teacher", use_container_width=True, key="open_teacher_nav"):
                st.session_state.app_mode = "Teacher"
                st.rerun()

    return st.session_state.app_mode

def render_db_setup_message() -> None:
    st.info(
        "Daily Challenge accounts are not connected yet. Practice still works. "
        "For the full app, finish the Supabase + Streamlit Secrets steps in DEPLOYMENT_STEPS.txt."
    )

def render_student_sign_in(store: SupabaseFactStore | None) -> bool:
    if student_signed_in():
        return True
    if store is not None and not st.session_state.get("persistent_login_check_complete", False):
        st.caption("Checking this device for a saved sign-in…")
        return False
    if store is None:
        render_db_setup_message()
        return False

    restore_error = st.session_state.get("persistent_login_restore_error")
    if restore_error:
        st.warning(str(restore_error))
        if st.button("Try saved sign-in again", use_container_width=True, key="retry_saved_student_login"):
            st.session_state.persistent_login_restore_error = None
            st.session_state.persistent_login_check_complete = False
            st.session_state.persistent_login_reader_nonce = int(
                st.session_state.get("persistent_login_reader_nonce", 0)
            ) + 1
            st.rerun()

    try:
        classes = _timed_app_call("student_signin_classes", store.list_classes, log_after_seconds=0.75)
    except Exception as exc:
        st.error("The class database could not be loaded. Ask your teacher to check the app setup.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return False

    if not classes:
        st.info("No classes are set up yet. The teacher can create the first class in the Teacher tab.")
        return False

    st.markdown("### Student sign in")
    st.caption("Choose your class, enter your nickname, then tap your 4-digit classroom PIN and ✓.")
    class_by_name = {item.class_name: item for item in classes}
    class_name = st.selectbox("Class", list(class_by_name), key="student_login_class")
    nickname = st.text_input("Nickname", max_chars=28, key="student_login_nickname")
    remember_device = st.checkbox(
        f"Keep me signed in on this device for {REMEMBER_DAYS} days",
        key="student_login_remember",
    )
    st.caption("Great for your assigned Chromebook or iPad. Leave this unchecked on a shared device.")
    login_error = st.session_state.pop("student_login_error", None)
    if login_error:
        st.error(login_error)
    st.markdown("**4-digit PIN**")
    pin_reset = int(st.session_state.get("student_pin_reset_counter", 0))
    pin, submitted = render_student_pin(key=f"student_login_pin_pad_{pin_reset}")
    if submitted:
        selected = class_by_name[class_name]
        if not nickname.strip():
            st.session_state.student_login_error = "Enter your nickname before your PIN."
            st.session_state.student_pin_reset_counter = pin_reset + 1
            st.rerun()
        try:
            student = store.authenticate_student(selected.class_id, nickname, pin)
        except Exception:
            student = None
        if student is None:
            st.session_state.student_login_error = "That nickname/PIN combination did not match this class. Try again."
            st.session_state.student_pin_reset_counter = pin_reset + 1
            st.rerun()
        _set_student_session(student, selected)
        st.session_state.pop("student_pin_reset_counter", None)
        st.session_state.pop("student_login_error", None)
        if remember_device:
            token = issue_student_token(student.student_id, pin, _persistent_login_secret())
            st.session_state.persistent_login_pending_action = {"action": "store", "token": token}
        else:
            # If this device previously remembered somebody else, a manual
            # sign-in without the checkbox deliberately clears that old login.
            st.session_state.persistent_login_pending_action = {"action": "clear"}
        st.session_state.persistent_login_check_complete = True
        st.rerun()
    st.markdown(f"<div class='private-note'>Nicknames are public inside the class leaderboard. PINs stay private and are never shown to classmates. Remembered sign-ins expire after {REMEMBER_DAYS} days or when you sign out.</div>", unsafe_allow_html=True)
    return False

# ---------------------------------------------------------------------------
# Weekly Mystery reward
# ---------------------------------------------------------------------------
def resolve_weekly_mystery(store: SupabaseFactStore, week_start, record=None):
    plan = store.get_mystery_plan(week_start)
    if plan:
        return mystery_from_plan(plan)
    if record is None:
        record = store.get_weekly_mystery(week_start)
    key = record.mystery_key if record is not None else default_mystery_key_for_week(week_start)
    return mystery_for_key(key)

def ensure_weekly_mystery(store: SupabaseFactStore, day):
    week_start = week_start_for(day)
    plan = store.get_mystery_plan(week_start)
    planned_key = str(plan.get("mystery_key") or "").strip() if plan else ""
    record = store.get_or_create_weekly_mystery(
        week_start, planned_key or default_mystery_key_for_week(week_start)
    )
    return week_start, record, resolve_weekly_mystery(store, week_start, record)

def _mystery_solve_title(clue_count: int) -> str:
    clue_count = int(clue_count)
    if clue_count <= 1:
        return "🔮 One-Clue Wonder"
    if clue_count == 2:
        return "🕵️ Sharp Detective"
    if clue_count <= 4:
        return "🔍 Mystery Solver"
    return "🎯 Friday Solver"

def _render_mystery_clues(mystery, clue_count: int) -> None:
    if clue_count <= 0:
        st.caption("No clues unlocked yet this week.")
        return
    for index, clue in enumerate(mystery.clues[:clue_count], start=1):
        st.markdown(
            f"<div class='soft-card'><strong>Clue #{index}</strong><br>{html.escape(clue)}</div>",
            unsafe_allow_html=True,
        )

def _render_mystery_stats(store: SupabaseFactStore) -> None:
    stats = store.mystery_student_stats(st.session_state.student_id)
    solved = int(stats.get("solved") or 0)
    earliest = stats.get("earliest_solve")
    if solved:
        earliest_text = "Friday" if int(earliest or 5) >= 5 else f"{int(earliest)} clue{'s' if int(earliest) != 1 else ''}"
        st.caption(f"Mysteries solved: {solved} · Earliest solve: {earliest_text}")

def _render_mystery_learning(mystery) -> None:
    st.markdown(f"### 📚 Meet {mystery.answer}")
    st.markdown(learning_paragraph_for(mystery))
    st.info(f"🤯 **Fun fact:** {mystery.reveal_note}")

def _render_mystery_win(mystery, solved_guess, week_start) -> None:
    clue_count = max(1, int(solved_guess.clue_count or 1))
    title = _mystery_solve_title(clue_count)
    celebration_key = f"mystery_win_fanfare::{st.session_state.student_id}::{week_start.isoformat()}::{solved_guess.guess_day}"
    if not st.session_state.get(celebration_key):
        st.session_state[celebration_key] = True
        st.balloons()
    st.markdown(
        f"<div class='mystery-win-card center'>"
        f"<div class='mystery-win-kicker'>🎉🎉 YOU SOLVED THE MYSTERY! 🎉🎉</div>"
        f"<div class='mystery-win-answer'>{html.escape(mystery.answer)}</div>"
        f"<div class='mystery-win-title'>{html.escape(title)}</div>"
        f"<div class='mystery-win-detail'>You solved it with {clue_count} clue{'s' if clue_count != 1 else ''}!</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if st.session_state.get("student_is_test"):
        st.info("🧪 Test Student: this correct guess is sandbox-only and is not entered in a real class raffle.")
    else:
        st.success("🎟️ **You're in your class's Friday prize raffle!** Every correct solver gets one equal entry.")
    _render_mystery_learning(mystery)

def render_weekly_mystery_reward(store: SupabaseFactStore, day, challenge, *, show_heading: bool = True) -> None:
    """Earn one clue Monday-Friday; guessing exists only Thursday and Friday."""
    try:
        week_start, _, mystery = ensure_weekly_mystery(store, day)
        day_number = school_day_number(day)
        if day_number is not None:
            store.unlock_mystery_day(
                st.session_state.student_id, week_start, day_number, challenge.challenge_id
            )
        unlocks = store.list_mystery_unlocks(st.session_state.student_id, week_start)
        guesses = store.list_mystery_guesses(st.session_state.student_id, week_start)
    except Exception as exc:
        st.info("🕵️ Weekly Mystery will appear after your teacher finishes the v2.5 database update.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return

    # One clue is earned for each completed school day, including Friday.
    # Skipped days never backfill: two completed days means exactly two clues.
    clue_count = min(5, sum(1 for row in unlocks if 1 <= int(row.day_number) <= 5))
    completed_days = {int(row.day_number) for row in unlocks}
    guess_by_day = {int(row.guess_day): row for row in guesses}
    solved_guess = next((row for row in guesses if row.correct), None)

    if show_heading:
        st.markdown("### 🕵️ This Week's Mystery")
        st.caption("Earn one clue for each full routine Monday–Friday. Guess #1 is Thursday; Guess #2 is Friday.")
    _render_mystery_clues(mystery, clue_count)

    if day_number is None:
        st.info("The Weekly Mystery continues on school days.")
        _render_mystery_stats(store)
        return

    if day_number <= 3:
        if clue_count:
            st.success(f"🎁 Clue #{clue_count} earned! You're completely done for today.")
        st.caption("No guessing yet — your first guess opens Thursday.")
        _render_mystery_stats(store)
        return

    if day_number == 4:
        st.success(f"🎁 You earned Clue #{clue_count}! Thursday Guess #1 is unlocked.")
        existing = guess_by_day.get(4)
        if existing is not None:
            if existing.correct:
                _render_mystery_win(mystery, existing, week_start)
                st.caption("You solved it early! Friday will still reveal the mystery to everyone who finishes.")
            else:
                st.info(f"Thursday guess: **{existing.guess_text}** · Not quite. You get one final guess Friday.")
        else:
            st.markdown("**🎯 Guess #1 of 2 — Thursday**")
            st.caption("Use it now or skip it. Thursday's unused guess does not carry over to Friday.")
            with st.form(f"weekly_mystery_thursday_guess_{week_start.isoformat()}", clear_on_submit=True):
                raw_guess = st.text_input("Thursday guess", max_chars=80, placeholder="What do you think the answer is?")
                submit_guess = st.form_submit_button("Submit Thursday guess", use_container_width=True, type="primary")
            if submit_guess:
                cleaned = " ".join(str(raw_guess or "").strip().split())
                if not cleaned:
                    st.error("Type a guess first — or simply wait until Friday.")
                else:
                    store.submit_mystery_guess(
                        st.session_state.student_id,
                        week_start,
                        cleaned,
                        correct=is_correct_guess(mystery, cleaned),
                        clue_count=max(1, clue_count),
                        guess_day=4,
                    )
                    st.rerun()
        _render_mystery_stats(store)
        return

    # Friday: completing Friday earns that day's clue, then unlocks the
    # second/final guess and reveal. It never grants clues for skipped days.
    if 5 not in completed_days:
        st.caption("Complete Friday's full routine to unlock the final guess and reveal.")
        return

    thursday_guess = guess_by_day.get(4)
    friday_guess = guess_by_day.get(5)
    reveal_key = f"mystery_reveal_without_guess_{week_start.isoformat()}"

    if solved_guess is not None:
        _render_mystery_win(mystery, solved_guess, week_start)
        _render_mystery_stats(store)
        return
    elif friday_guess is None and not st.session_state.get(reveal_key):
        if thursday_guess is not None:
            st.caption(f"Thursday guess: {thursday_guess.guess_text}")
        st.markdown("**🎯 Guess #2 of 2 — Friday**")
        st.caption(f"Final guess using the {clue_count} clue{'s' if clue_count != 1 else ''} you actually earned this week.")
        with st.form(f"weekly_mystery_friday_guess_{week_start.isoformat()}", clear_on_submit=True):
            raw_guess = st.text_input("Friday guess", max_chars=80, placeholder="What is your final guess?")
            submit_guess = st.form_submit_button("Submit Friday guess & reveal", use_container_width=True, type="primary")
        if submit_guess:
            cleaned = " ".join(str(raw_guess or "").strip().split())
            if not cleaned:
                st.error("Type your final guess first.")
            else:
                store.submit_mystery_guess(
                    st.session_state.student_id,
                    week_start,
                    cleaned,
                    correct=is_correct_guess(mystery, cleaned),
                    clue_count=max(1, clue_count),
                    guess_day=5,
                )
                st.rerun()
        if st.button("Reveal without using my Friday guess", use_container_width=True, type="secondary", key=f"mystery_reveal_{week_start.isoformat()}"):
            st.session_state[reveal_key] = True
            st.rerun()
        return

    st.markdown(
        f"<div class='hero-card center'><div style='font-size:1rem;font-weight:850'>🎉 MYSTERY REVEALED</div>"
        f"<div style='font-size:2rem;font-weight:950;margin-top:.25rem'>{html.escape(mystery.answer)}</div></div>",
        unsafe_allow_html=True,
    )
    _render_mystery_learning(mystery)
    if friday_guess is not None:
        if friday_guess.correct:
            st.success("✅ Your Friday guess was correct!")
        else:
            st.caption(f"Your Friday guess was: {friday_guess.guess_text}")
    _render_mystery_stats(store)

# ---------------------------------------------------------------------------
# Daily Challenge
# ---------------------------------------------------------------------------
def ensure_today(store: SupabaseFactStore):
    day = current_daily_date()
    facts = daily_facts_for_date(day)
    validate_daily_facts(facts)
    challenge = store.get_or_create_challenge(day, CHALLENGE_VERSION, facts)
    return day, list(challenge.facts), challenge

def load_leaderboard_context(store: SupabaseFactStore, challenge) -> dict:
    """Load a privacy-sanitized student leaderboard snapshot.

    Supabase performs the accuracy-first/time-second ranking.  After ranking,
    the student session intentionally keeps only rank, nickname, and student ID.
    Classmates' scores and times never enter the student-facing context.
    """
    class_id = st.session_state.student_class_id
    roster = store.list_students(class_id)
    completed = store.completed_attempts_for_class(class_id, challenge.challenge_id, students=roster)
    rows = [
        {
            "student_id": row["student_id"],
            "nickname": row["nickname"],
            "rank": index,
        }
        for index, row in enumerate(completed[:10], start=1)
    ]
    return {"rows": rows, "finished": len(completed), "roster_count": len(roster)}

def _leaderboard_cache_key(challenge) -> str:
    return f"leaderboard_context_{st.session_state.student_id}_{challenge.challenge_id}"

def get_cached_leaderboard_context(store: SupabaseFactStore, challenge, *, refresh: bool = False) -> dict:
    """Reuse one leaderboard snapshot during Fix/Focus reruns.

    Streamlit reruns the entire script after every Focus answer. Reloading the
    class roster + completed attempts each time created avoidable whole-class
    traffic. Refresh only when the Daily is first completed or the whole
    learning routine is done.
    """
    key = _leaderboard_cache_key(challenge)
    if refresh or key not in st.session_state:
        st.session_state[key] = load_leaderboard_context(store, challenge)
    return st.session_state[key]

def _focus_rows_cache_key(challenge) -> str:
    return f"focus_rows_{st.session_state.student_id}_{challenge.challenge_id}"

def get_cached_focus_rows(store: SupabaseFactStore, challenge) -> list:
    key = _focus_rows_cache_key(challenge)
    if key not in st.session_state:
        st.session_state[key] = store.learning_activity_rows(
            st.session_state.student_id, challenge.challenge_id, "focus"
        )
    return list(st.session_state[key])

def append_cached_focus_row(challenge, row) -> None:
    key = _focus_rows_cache_key(challenge)
    rows = list(st.session_state.get(key, []))
    rows.append(row)
    st.session_state[key] = rows

def get_cached_focus_override(store: SupabaseFactStore, challenge) -> int | None:
    key = f"focus_override_{st.session_state.student_id}_{challenge.challenge_id}"
    if key not in st.session_state:
        st.session_state[key] = store.get_effective_focus_override(st.session_state.student_id)
    return st.session_state[key]

def render_leaderboard(
    store: SupabaseFactStore, challenge, *, highlight_student_id: str | None = None, context: dict | None = None
) -> None:
    context = context or load_leaderboard_context(store, challenge)
    rows = list(context["rows"])
    finished = int(context["finished"])
    roster_count = int(context["roster_count"])

    st.markdown("### 🏆 Current Top 10")
    st.caption(f"{finished} of {roster_count} finished · standings may change as more classmates finish · accuracy ranks first, with time used privately as the tiebreaker")
    if not rows:
        st.info("No one has finished yet. The first completed challenge will start the board!")
        return

    medal = {1: "🥇", 2: "🥈", 3: "🥉"}
    html_rows = []
    for row in rows:
        marker = medal.get(row["rank"], str(row["rank"]))
        name = html.escape(str(row["nickname"]))
        own = row["student_id"] == highlight_student_id
        suffix = " · you" if own else ""
        html_rows.append(
            f'<div class="leader-row"><div class="leader-rank">{marker}</div>'
            f'<div class="leader-name">{name}{suffix}</div></div>'
        )
    st.markdown('<div class="soft-card">' + "".join(html_rows) + "</div>", unsafe_allow_html=True)
    if highlight_student_id and not any(row["student_id"] == highlight_student_id for row in rows):
        st.caption("Only the Top 10 is shown. Your exact class rank stays private.")

def render_daily_review(facts: list[Fact], answers) -> None:
    with st.expander("Review your Daily 10", expanded=False):
        for fact, answer in zip(facts, answers):
            cls = "answer-correct" if answer.correct else "answer-miss"
            symbol = "✅" if answer.correct else "❌"
            correct_text = "" if answer.correct else f" · correct answer {answer.correct_answer}"
            st.markdown(
                f'<div class="soft-card {cls}"><strong>{symbol} {answer.question_number}. {fact.label}</strong><br>'
                f'You answered <strong>{answer.student_answer}</strong>{correct_text}</div>',
                unsafe_allow_html=True,
            )
        if all(answer.correct for answer in answers):
            st.success("Perfect accuracy — all 10 Daily facts were correct.")

def render_learning_path(progress, missed_count: int) -> None:
    if progress.completed_at is not None or progress.focus_completed_at is not None:
        stage = "mystery"
    elif progress.fix_completed_at is not None:
        stage = "focus"
    else:
        stage = "fix"
    render_routine_strip(stage)
    if stage == "fix":
        if missed_count:
            st.caption(f"Next: fix {missed_count} missed fact{'s' if missed_count != 1 else ''}, then your personalized Focus Practice.")
        else:
            st.caption("No misses today ✓ · next up is your personalized Focus Practice.")
    elif stage == "focus":
        st.caption("Next: finish 8 Focus Facts. Then your learning work is DONE and your Mystery reward unlocks.")
    else:
        st.caption("Learning work complete ✓ · your Weekly Mystery is the reward, not another assignment.")

def render_daily_result_summary(store: SupabaseFactStore, day, challenge, attempt, *, leaderboard_context: dict | None = None) -> None:
    leaderboard = list((leaderboard_context or load_leaderboard_context(store, challenge))["rows"])
    own_top = next((row for row in leaderboard if row["student_id"] == st.session_state.student_id), None)
    st.markdown(f"## Daily 10 complete · {day.strftime('%B %d').replace(' 0', ' ')}")
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="result-grid">
                <div class="result-box"><div class="result-label">Daily 10</div><div class="result-value">Complete ✓</div></div>
                <div class="result-box"><div class="result-label">Top 10</div><div class="result-value">{('#' + str(own_top['rank'])) if own_top else '—'}</div></div>
                <div class="result-box"><div class="result-label">Facts to Fix</div><div class="result-value">{10 - int(attempt.correct_count or 0)}</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if own_top:
        st.success(f"You're #{own_top['rank']} in your class Top 10 right now!")
    elif len(leaderboard) >= 10:
        st.info("Only the class Top 10 is shown. Your exact class rank stays private.")
    else:
        st.caption("The class Top 10 will keep filling in as classmates finish.")

def _missed_daily_items(facts: list[Fact], answers) -> list[tuple[int, Fact, object]]:
    result = []
    for fact, answer in zip(facts, answers):
        if not answer.correct:
            result.append((int(answer.question_number), fact, answer))
    return result

def _guided_item(fact: Fact, *, activity_index: int, start_state: str, original_answer: int | None = None, first_already_recorded: bool = False) -> dict:
    normalized_state = "coach" if start_state == "teach" else start_state
    return {
        "activity_index": int(activity_index),
        "a": fact.a, "b": fact.b, "product": fact.product,
        "strategy": strategy_tip(fact),
        "repeated_addition": repeated_addition_text(fact),
        "coach": coach_plan_for_fact(fact),
        "start_state": normalized_state,
        "original_answer": original_answer,
        "first_already_recorded": bool(first_already_recorded),
    }

def render_fix_misses(store: SupabaseFactStore, challenge, facts: list[Fact], answers) -> bool:
    missed = _missed_daily_items(facts, answers)
    if not missed:
        store.mark_fix_complete(st.session_state.student_id, challenge.challenge_id)
        return True

    rows = store.learning_activity_rows(st.session_state.student_id, challenge.challenge_id, "fix_miss")
    corrected = {int(row.activity_index) for row in rows if row.correct and row.activity_index is not None}
    if all(question_number in corrected for question_number, _, _ in missed):
        store.mark_fix_complete(st.session_state.student_id, challenge.challenge_id)
        return True

    remaining = [(q, fact, ans) for q, fact, ans in missed if q not in corrected]
    item_by_index = {q: fact for q, fact, _ in remaining}
    items = [
        _guided_item(
            fact, activity_index=q, start_state="coach",
            original_answer=int(ans.student_answer), first_already_recorded=True,
        )
        for q, fact, ans in remaining
    ]

    events = render_guided_practice(
        key=f"guided_fix_{challenge.challenge_id}",
        mode="fix",
        session_key=f"{st.session_state.student_id}:{challenge.challenge_id}:fix",
        items=items,
        step_label="Step 2 · Fix Your Misses",
        done_title="Fix Your Misses complete!",
    )
    if events is None:
        return False

    valid: list[dict] = []
    correct_indices: set[int] = set()
    for event in events:
        fact = item_by_index.get(int(event["activity_index"]))
        if fact is None or (event["a"], event["b"]) != (fact.a, fact.b) or not event["is_retry"]:
            continue
        valid.append(event)
        if int(event["student_answer"]) == fact.product:
            correct_indices.add(int(event["activity_index"]))
    if set(item_by_index) - correct_indices:
        st.error("Oops — that didn’t save correctly. Try this step again. If it happens again, show your teacher.")
        return False

    if valid:
        store.record_practice_batch(
            st.session_state.student_id,
            "Fix Your Misses",
            challenge.challenge_id,
            "fix_miss",
            valid,
        )
    st.rerun()
    return False

def _focus_index_state(rows, index: int) -> tuple[object | None, bool]:
    at_index = [row for row in rows if row.activity_index == index]
    first = next((row for row in at_index if not row.is_retry), None)
    if first is None:
        return None, False
    if first.correct:
        return first, True
    corrected = any(row.is_retry and row.correct for row in at_index)
    return first, corrected

def ensure_focus_plan(store: SupabaseFactStore, day, challenge, answers, progress=None):
    progress = progress or store.get_learning_progress(st.session_state.student_id, challenge.challenge_id)
    if progress.focus_plan:
        return progress
    mastery = store.get_mastery(st.session_state.student_id)
    misses = [(answer.a, answer.b) for answer in answers if not answer.correct and max(answer.a, answer.b) <= 10]
    override = get_cached_focus_override(store, challenge)
    plan = build_focus_plan(
        mastery,
        student_id=st.session_state.student_id,
        date_key=day.isoformat(),
        override_family=override,
        recent_daily_misses=misses,
    )
    return store.set_focus_plan(st.session_state.student_id, challenge.challenge_id, plan)

def render_focus_practice(store: SupabaseFactStore, day, challenge, answers, progress=None) -> bool:
    progress = ensure_focus_plan(store, day, challenge, answers, progress=progress)
    plan = list(progress.focus_plan)
    if len(plan) != FOCUS_SESSION_LENGTH:
        st.error("Oops — your Focus Practice isn’t ready yet. Show your teacher and they can refresh it.")
        return False

    rows = get_cached_focus_rows(store, challenge)
    done_indices = []
    state_by_index: dict[int, tuple[object | None, bool]] = {}
    for index in range(FOCUS_SESSION_LENGTH):
        state = _focus_index_state(rows, index)
        state_by_index[index] = state
        if state[1]:
            done_indices.append(index)
    if len(done_indices) == FOCUS_SESSION_LENGTH:
        first_tries = [row for row in rows if not row.is_retry and row.activity_index is not None]
        evidence = []
        seen_indices: set[int] = set()
        for row in first_tries:
            idx = int(row.activity_index)
            if idx in seen_indices or not (0 <= idx < len(plan)):
                continue
            seen_indices.add(idx)
            evidence.append((plan[idx], bool(row.correct), row.response_seconds, row.created_at))
        if evidence:
            store.record_mastery_evidence_batch(st.session_state.student_id, evidence)
        store.mark_focus_complete(st.session_state.student_id, challenge.challenge_id)
        return True

    remaining_indices = [i for i in range(FOCUS_SESSION_LENGTH) if i not in done_indices]
    items = []
    for index in remaining_indices:
        fact = plan[index]
        first, _ = state_by_index[index]
        items.append(_guided_item(
            fact, activity_index=index,
            start_state="coach" if first is not None and not first.correct else "question",
            first_already_recorded=first is not None,
        ))

    override = get_cached_focus_override(store, challenge)
    if override:
        st.caption(f"Your teacher has you practicing the {override}s today.")
    st.caption("If one is tricky, the app will teach it and let you try again.")

    events = render_guided_practice(
        key=f"guided_focus_{challenge.challenge_id}",
        mode="focus",
        session_key=f"{st.session_state.student_id}:{challenge.challenge_id}:focus",
        items=items,
        step_label="Step 3 · Your Focus Practice",
        done_title="Focus Practice complete!",
    )
    if events is None:
        return False

    allowed = {i: plan[i] for i in remaining_indices}
    existing_first = {i for i in remaining_indices if state_by_index[i][0] is not None}
    by_index: dict[int, list[dict]] = {i: [] for i in remaining_indices}
    valid: list[dict] = []
    for event in events:
        idx = int(event["activity_index"])
        fact = allowed.get(idx)
        if fact is None or (event["a"], event["b"]) != (fact.a, fact.b):
            continue
        by_index[idx].append(event)
        valid.append(event)

    for idx in remaining_indices:
        fact = allowed[idx]
        item_events = by_index[idx]
        if not item_events:
            st.error("Oops — that didn’t save correctly. Try this step again. If it happens again, show your teacher.")
            return False
        if idx not in existing_first and item_events[0]["is_retry"]:
            st.error("Oops — that didn’t save correctly. Try this step again. If it happens again, show your teacher.")
            return False
        if idx in existing_first and any(not event["is_retry"] for event in item_events):
            st.error("Oops — that didn’t save correctly. Try this step again. If it happens again, show your teacher.")
            return False
        if not any(int(event["student_answer"]) == fact.product for event in item_events):
            st.error("Finish the correction before moving on.")
            return False

    if valid:
        saved = store.record_practice_batch(
            st.session_state.student_id,
            "My Focus Facts",
            challenge.challenge_id,
            "focus",
            valid,
        )
        for row in saved:
            append_cached_focus_row(challenge, row)
    st.rerun()
    return False

def render_mastery_card(store: SupabaseFactStore) -> None:
    """Render the student's private mastery summary from saved Daily/Focus evidence."""
    summary = store.mastery_summary(st.session_state.student_id)
    st.markdown("### 🌱 My Growth")
    st.caption("Your fact map grows as you practice. New facts start as Learning.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟢 Fluent", summary.get(STATUS_FLUENT, 0))
    c2.metric("🟡 Building", summary.get(STATUS_BUILDING, 0))
    c3.metric("🔴 Focus", summary.get(STATUS_FOCUS, 0))
    c4.metric("⚪ Learning", summary.get(STATUS_UNKNOWN, 0))

def render_final_top10_status(challenge, leaderboard_context: dict | None) -> None:
    """Show the student's status plus the full rank-and-nickname Top 10 at finish.

    Reuse the leaderboard snapshot already loaded for this Daily so the final
    celebration does not add another classroom database round trip. Only Top
    10 rank + nickname are shown; lower exact ranks remain private.
    """
    st.markdown("## 🏆 Current Top 10")
    if leaderboard_context is None:
        st.caption("Your Top 10 status is updating. You do not need to redo anything.")
        return

    rows = list(leaderboard_context.get("rows") or [])
    finished = int(leaderboard_context.get("finished") or 0)
    roster_count = int(leaderboard_context.get("roster_count") or 0)
    own_top = next((row for row in rows if row.get("student_id") == st.session_state.student_id), None)

    if own_top:
        st.success(f"🏆 You're #{int(own_top['rank'])} in your class Top 10 right now!")
    else:
        st.info("You finished today's challenge! Only Top 10 places are shown, so lower exact ranks stay private.")

    if roster_count:
        st.caption(f"{finished} of {roster_count} finished · standings may change as classmates finish")
    else:
        st.caption("Standings may change as classmates finish.")

    if not rows:
        st.info("No one has finished yet. The first completed challenge will start the board!")
        return

    medal = {1: "🥇", 2: "🥈", 3: "🥉"}
    html_rows = []
    for row in rows:
        rank = int(row.get("rank") or 0)
        marker = medal.get(rank, str(rank))
        name = html.escape(str(row.get("nickname") or ""))
        own = row.get("student_id") == st.session_state.student_id
        suffix = " · you" if own else ""
        html_rows.append(
            f'<div class="leader-row"><div class="leader-rank">{marker}</div>'
            f'<div class="leader-name">{name}{suffix}</div></div>'
        )
    st.markdown('<div class="soft-card">' + "".join(html_rows) + "</div>", unsafe_allow_html=True)

def render_day_complete(
    store: SupabaseFactStore, day, facts: list[Fact], challenge, attempt, answers,
    *, leaderboard_context: dict | None = None,
) -> None:
    stats = store.student_learning_stats(st.session_state.student_id, day)
    streak = int(stats.get("current_streak", 0))

    st.markdown(
        "<div class='finish-banner'><div class='big'>✅ YOU'RE DONE FOR TODAY!</div>"
        "<div class='sub'>Daily 10 ✓ &nbsp; · &nbsp; Fix Misses ✓ &nbsp; · &nbsp; Focus Practice ✓</div>"
        "<div style='margin-top:.45rem'>Your learning work is finished for today.</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("## 🕵️ Today's Mystery Reward")
    render_weekly_mystery_reward(store, day, challenge, show_heading=False)

    render_final_top10_status(challenge, leaderboard_context)

    if streak in {3, 5, 10, 20, 30, 50} or (streak > 0 and streak % 50 == 0):
        st.success(f"🎉 {streak}-day Learning Streak!")
    elif streak:
        st.success(f"🔥 {streak}-day Learning Streak")

    st.markdown("### ✅ That's it — see you next Challenge day! 👋")
    st.caption("Everything below is optional. Your required work is complete.")
    show_growth = st.toggle("🌱 See My Growth", value=False, key=f"show_growth_{challenge.challenge_id}")
    if show_growth:
        render_mastery_card(store)
    with st.expander("📝 Review My Daily 10", expanded=False):
        for fact, answer in zip(facts, answers):
            symbol = "✅" if answer.correct else "❌"
            correct_text = "" if answer.correct else f" · correct answer {answer.correct_answer}"
            st.markdown(
                f'<div class="soft-card"><strong>{symbol} {answer.question_number}. {fact.label}</strong><br>'
                f'You answered <strong>{answer.student_answer}</strong>{correct_text}</div>',
                unsafe_allow_html=True,
            )
    if st.button("Extra Practice (optional)", use_container_width=True, type="secondary", on_click=switch_mode, args=("Practice",)):
        pass

def _is_transient_classroom_error(exc: Exception) -> bool:
    """Only classify real short-lived HTTP transport failures as classroom congestion."""
    transient_types = (
        httpx.ReadError,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        httpx.ReadTimeout,
        httpx.ConnectTimeout,
        httpx.PoolTimeout,
    )
    if isinstance(exc, transient_types):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(token in text for token in (
        "readerror", "connection reset", "server disconnected",
        "remoteprotocolerror", "read timeout", "connect timeout", "pool timeout",
    ))

def _connection_failure_kind(exc: Exception) -> str:
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout)):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    if isinstance(exc, httpx.ReadError):
        return "read_error"
    if isinstance(exc, httpx.RemoteProtocolError):
        return "remote_protocol"
    text = f"{type(exc).__name__}: {exc}".lower()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "connection reset" in text or "connecterror" in text or "connect error" in text:
        return "connect_error"
    if "server disconnected" in text or "remoteprotocolerror" in text:
        return "remote_protocol"
    if "readerror" in text or "read error" in text:
        return "read_error"
    if _is_transient_classroom_error(exc):
        return "transient_transport"
    return "unexpected"

def _log_private_connection_failure(label: str, exc: Exception) -> None:
    """Log only a coarse failure class + exception type; never student data."""
    kind = _connection_failure_kind(exc)
    print(f"[TDFC connection] {label}: {kind} ({type(exc).__name__})", flush=True)

def render_classroom_connection_retry(exc: Exception, *, key: str = "classroom_retry") -> None:
    _log_private_connection_failure("completed_daily", exc)
    if _is_transient_classroom_error(exc):
        st.warning("The classroom connection is busy for a moment. Your completed Daily is still saved.")
        st.caption("Wait a second and try again — you do not need to redo your 10 facts.")
    else:
        st.error("This part of the finished screen hit an unexpected display error. Your completed Daily is still saved.")
        st.caption("Refresh once and try again. If it keeps happening, your teacher can report it without redoing the Daily 10.")
    if st.button("Try again", use_container_width=True, type="primary", key=key):
        st.rerun()
    if str(st.query_params.get("dbcheck", "0")) == "1":
        st.exception(exc)

def render_daily_load_retry(exc: Exception) -> None:
    """Recover from a temporary Daily-load failure without losing student state."""
    _log_private_connection_failure("daily_load", exc)
    st.warning("Having trouble reaching today's Daily 10.")
    st.caption("Your sign-in and any completed Igniter work are safe. Tap Try Again to retry without signing out.")
    if st.button("🔄 Try Again", use_container_width=True, type="primary", key="retry_daily_load"):
        st.rerun()
    if str(st.query_params.get("dbcheck", "0")) == "1":
        st.exception(exc)

def render_completed_daily(store: SupabaseFactStore, day, facts: list[Fact], challenge, attempt) -> None:
    try:
        evidence_key = f"daily_evidence_verified::{attempt.attempt_id}"
        if not st.session_state.get(evidence_key, False):
            store.ensure_daily_learning_evidence(attempt.attempt_id)
            st.session_state[evidence_key] = True
        answers = store.get_answers(attempt.attempt_id)
        progress = store.get_or_create_learning_progress(st.session_state.student_id, challenge.challenge_id)
    except Exception as exc:
        render_classroom_connection_retry(exc, key="retry_completed_load")
        return

    # The midpoint between Daily 10 and the required learning steps should stay
    # extremely light.  Do not load or render standings here: the leaderboard is
    # a reward/status item for the true end-of-day screen, not a roadblock before
    # Fix Your Misses or Focus Practice.
    if progress.completed_at is not None:
        try:
            try:
                leaderboard_context = get_cached_leaderboard_context(store, challenge, refresh=True)
            except Exception:
                leaderboard_context = st.session_state.get(_leaderboard_cache_key(challenge))
            render_day_complete(
                store, day, facts, challenge, attempt, answers,
                leaderboard_context=leaderboard_context,
            )
        except Exception as exc:
            render_classroom_connection_retry(exc, key="retry_day_complete")
        return

    missed_count = sum(not answer.correct for answer in answers)
    st.success("✅ Daily 10 complete!")

    try:
        if progress.fix_completed_at is None:
            if missed_count:
                st.markdown("### Next: Fix Your Misses")
                st.caption(f"You have {missed_count} fact{'s' if missed_count != 1 else ''} to fix.")
            else:
                st.markdown("### Next: Focus Practice")
                st.caption("You got all 10 correct. Keep building fluency with your personalized practice.")
            if render_fix_misses(store, challenge, facts, answers):
                st.rerun()
            render_daily_review(facts, answers)
            return

        if progress.focus_completed_at is None:
            st.markdown("### Next: Focus Practice")
            st.caption("8 facts picked just for you.")
            if render_focus_practice(store, day, challenge, answers, progress=progress):
                st.rerun()
            render_daily_review(facts, answers)
            return

        store.mark_focus_complete(st.session_state.student_id, challenge.challenge_id)
        st.rerun()
    except Exception as exc:
        render_classroom_connection_retry(exc, key="retry_learning_step")
        return

def render_daily(store: SupabaseFactStore | None) -> None:
    if not render_student_sign_in(store):
        return
    assert store is not None

    day = current_daily_date()
    if not render_quick_warmup(store, day):
        return

    try:
        day, facts, challenge = ensure_today(store)
        configured_mode = configured_daily_mode(store, st.session_state.student_class_id, day)
        custom_questions = questions_for_mode(day, configured_mode) if configured_mode != "Multiplication" else None
        attempt = store.get_or_create_attempt(
            st.session_state.student_id, challenge.challenge_id,
            daily_mode=configured_mode, custom_questions=custom_questions,
        )
    except Exception as exc:
        render_daily_load_retry(exc)
        return

    # Once a student starts, the attempt itself is the source of truth even if
    # the teacher later changes that class/date setup.
    daily_mode = str(getattr(attempt, "daily_mode", None) or "Multiplication")

    st.markdown("## Daily 10")
    if daily_mode == "Multiplication":
        st.caption("10 facts. Do your best. You’ll see your results after all 10.")
    else:
        st.caption(f"{daily_mode} · 10 questions. Accuracy comes first; time only breaks ties.")

    if attempt.completed_at is not None:
        if daily_mode == "Multiplication":
            render_completed_daily(store, day, facts, challenge, attempt)
        else:
            render_alternate_daily(
                store, day, challenge, attempt, render_mystery_reward=render_weekly_mystery_reward
            )
        return

    st.markdown(f"### {day.strftime('%A, %B %d').replace(' 0', ' ')}")
    if daily_mode == "Multiplication":
        render_routine_strip("daily")
        st.caption("Finish the three learning steps to earn today's Mystery reward.")
        st.markdown(
            "<div class='private-note'><strong>Fact 1 is untimed.</strong> After you submit it, the hidden timer starts. Accuracy comes first.</div>",
            unsafe_allow_html=True,
        )

        # Protected v2.12 multiplication browser sprint. Its component file and
        # TDFC-DAILY-v1 challenge generator are intentionally unchanged.
        component_result = DAILY_SPRINT_COMPONENT(
            facts=[{"a": fact.a, "b": fact.b} for fact in facts],
            attempt_key=f"{st.session_state.student_id}:{challenge.challenge_id}:{attempt.attempt_id}",
            challenge_version=CHALLENGE_VERSION,
            default=None,
            key=f"daily_sprint_{attempt.attempt_id}",
        )

        if isinstance(component_result, dict) and component_result.get("status") == "complete":
            try:
                raw_answers = component_result.get("answers")
                raw_first_answers = component_result.get("first_answers")
                raw_response_seconds = component_result.get("response_seconds")
                timed_seconds = float(component_result.get("timed_seconds"))
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
                )
                st.rerun()
            except Exception as exc:
                st.error("Your finished Daily could not be saved. Leave this page open and try once more; your completed answers are still held in this browser.")
                if str(st.query_params.get("dbcheck", "0")) == "1":
                    st.exception(exc)
    else:
        render_alternate_daily(
            store, day, challenge, attempt, render_mystery_reward=render_weekly_mystery_reward
        )

    st.caption("Your work stays with you on this device. If something goes wrong, show your teacher.")

# ---------------------------------------------------------------------------
# Practice
# ---------------------------------------------------------------------------
def reset_practice_question(*, clear_focus_queue: bool = False) -> None:
    st.session_state.practice_fact = None
    st.session_state.practice_result = None
    st.session_state.practice_retry_correct = False
    st.session_state.practice_retry_count = 0
    st.session_state.practice_question_serial = int(st.session_state.get("practice_question_serial", 0)) + 1
    st.session_state.practice_started_at = None
    if clear_focus_queue:
        st.session_state.practice_focus_queue = []

def next_practice_question() -> None:
    st.session_state.practice_fact = None
    st.session_state.practice_result = None
    st.session_state.practice_retry_correct = False
    st.session_state.practice_retry_count = 0
    st.session_state.practice_question_serial = int(st.session_state.get("practice_question_serial", 0)) + 1
    st.session_state.practice_started_at = None

def render_practice(store: SupabaseFactStore | None) -> None:
    st.markdown("## Practice")
    st.caption("Choose your area of need · unlimited facts · instant teaching after every answer")

    signed_in = student_signed_in() and store is not None
    if not student_signed_in():
        st.info("You can Practice as a guest. Sign in from Daily Challenge to unlock 🎯 My Focus Facts and save your Practice rounds.")

    options = (["🎯 My Focus Facts"] if signed_in else []) + fact_family_options()
    focus = st.selectbox("What do you want to practice?", options, key="practice_focus")
    if st.session_state.practice_focus_last != focus:
        st.session_state.practice_focus_last = focus
        reset_practice_question(clear_focus_queue=True)

    if st.session_state.practice_fact is None:
        recent = st.session_state.practice_recent[-4:]
        if focus == "🎯 My Focus Facts" and signed_in:
            queue = list(st.session_state.get("practice_focus_queue") or [])
            if not queue:
                mastery = store.get_mastery(st.session_state.student_id)
                override = store.get_effective_focus_override(st.session_state.student_id)
                batch = int(st.session_state.get("practice_focus_queue_batch", 0))
                plan = build_focus_plan(
                    mastery,
                    student_id=st.session_state.student_id,
                    date_key=f"manual-{current_daily_date().isoformat()}-{batch}",
                    override_family=override,
                )
                queue = [item.as_dict() for item in plan]
                st.session_state.practice_focus_queue_batch = batch + 1
            fact = Fact.from_dict(queue.pop(0))
            st.session_state.practice_focus_queue = queue
        else:
            fact = practice_fact(focus, random.Random(), avoid=recent)
        st.session_state.practice_fact = fact.as_dict()
        st.session_state.practice_started_at = datetime.now(timezone.utc).timestamp()
    fact = Fact.from_dict(st.session_state.practice_fact)

    if focus == "🎯 My Focus Facts":
        st.caption("These are facts picked for you based on your recent work.")

    if st.session_state.practice_result is None:
        practice_identity = st.session_state.student_id if signed_in else "guest"
        items = [_guided_item(fact, activity_index=0, start_state="question")]
        events = render_guided_practice(
            key=f"guided_free_practice_{st.session_state.practice_question_serial}_{fact.a}_{fact.b}",
            mode="practice",
            session_key=f"{practice_identity}:free-practice:{st.session_state.practice_question_serial}:{fact.a}:{fact.b}",
            items=items,
            step_label="Extra Practice",
            done_title="Practice fact complete!",
        )
        if events is None:
            return

        first = next((event for event in events if not event["is_retry"]), None)
        final_correct = any(
            int(event["student_answer"]) == fact.product
            for event in events
        )
        if first is None or not final_correct:
            st.error("Oops — that didn’t save correctly. Try this fact again. If it happens again, show your teacher.")
            return

        if signed_in:
            try:
                store.record_practice_batch(
                    st.session_state.student_id,
                    focus,
                    "free-practice",
                    "free_practice",
                    events,
                )
            except Exception:
                pass

        st.session_state.practice_result = {
            "answer": int(first["student_answer"]),
            "correct": int(first["student_answer"]) == fact.product,
            "fact": fact.as_dict(),
            "used_coach": any(bool(event["is_retry"]) for event in events),
        }
        st.session_state.practice_recent.append(fact.key)
        st.session_state.practice_recent = st.session_state.practice_recent[-8:]
        st.rerun()
        return

    result = st.session_state.practice_result
    if result["correct"]:
        st.success(f"✅ Yes! {fact.a} × {fact.b} = {fact.product}")
    else:
        st.success(f"✅ You worked it out — {fact.a} × {fact.b} = {fact.product}.")
        st.caption("Your first try stays recorded as a miss; the Fact Coach correction is teaching practice, not instant mastery.")

    if st.button("Next Practice Fact →", use_container_width=True, type="primary", on_click=next_practice_question):
        pass
    st.caption("Change the menu above anytime to focus on a different fact family.")

# ---------------------------------------------------------------------------
# Teacher dashboard
# ---------------------------------------------------------------------------
def teacher_login() -> bool:
    if st.session_state.teacher_authed:
        return True
    if not teacher_password_configured():
        st.warning("Teacher Dashboard needs TEACHER_PASSWORD in Streamlit Secrets. The deployment guide has the exact setup.")
        return False
    st.markdown("## 🔒 Teacher Dashboard")
    st.caption("This area shows full class results and roster tools. Students only see the Top 10.")
    with st.form("teacher_login_form"):
        password = st.text_input("Teacher password", type="password")
        submit = st.form_submit_button("Open Teacher Dashboard", use_container_width=True, type="primary")
    if submit:
        expected = str(st.secrets.get("TEACHER_PASSWORD") or "")
        if hmac.compare_digest(str(password), expected):
            st.session_state.teacher_authed = True
            st.rerun()
        else:
            st.error("That teacher password did not match.")
    return False

def _leaderboard_final_key(day, class_id: str) -> str:
    return f"teacher_leaderboard_final::{day.isoformat()}::{class_id}"

def _leaderboard_is_final(store: SupabaseFactStore, day, class_id: str, *, completed: int, total: int) -> bool:
    if total > 0 and completed >= total:
        return True
    return bool(store.get_app_setting(_leaderboard_final_key(day, class_id), False))

def _leaderboard_from_status(status: list[dict], *, limit: int = 10) -> list[dict]:
    """Derive standings from the already-loaded teacher status snapshot."""
    completed = [row for row in status if row.get("status") == "Complete"]
    completed.sort(key=lambda row: (
        -int(row.get("correct_count") or 0),
        float(row.get("timed_seconds") or 0.0),
        row.get("completed_at") or datetime.max.replace(tzinfo=timezone.utc),
    ))
    return [dict(row, rank=index) for index, row in enumerate(completed[:limit], start=1)]

def _set_teacher_refresh_stamp() -> None:
    st.session_state["teacher_last_refresh_at"] = datetime.now().strftime("%I:%M:%S %p").lstrip("0")

def _request_teacher_refresh() -> None:
    """Force the next teacher render to use a brand-new Supabase client.

    Streamlit button callbacks run before the script reruns. Clearing the cached
    store here means the top-level ``get_store()`` call on that rerun creates a
    fresh client *before* Teacher Today/Projector reads any data. This makes the
    Refresh button a real data refresh rather than merely rerunning the page
    with the same long-lived cached connection.
    """
    load_store.clear()
    st.session_state["teacher_refresh_pending"] = True

def _finish_teacher_refresh() -> None:
    """Mark a requested refresh complete only after fresh reads succeeded."""
    if st.session_state.pop("teacher_refresh_pending", False):
        _set_teacher_refresh_stamp()
        st.toast("✅ Teacher data refreshed from Supabase")

def _teacher_refresh_control(*, key: str) -> None:
    st.button(
        "🔄 Refresh data",
        use_container_width=True,
        key=key,
        on_click=_request_teacher_refresh,
    )
    pending = bool(st.session_state.get("teacher_refresh_pending"))
    stamp = st.session_state.get("teacher_last_refresh_at")
    if pending:
        st.caption("Refreshing latest Supabase data…")
    elif stamp:
        st.caption(f"✅ Data updated {stamp}")

def render_teacher_projector(store: SupabaseFactStore) -> None:
    class_id = st.session_state.get("teacher_projector_class_id")
    class_name = st.session_state.get("teacher_projector_class_name") or "Class"
    if not class_id:
        st.session_state["teacher_projector_mode"] = False
        st.rerun()
        return

    day, _, challenge = ensure_today(store)
    students = store.list_students(class_id)
    status_error = None
    try:
        status = store.daily_status(class_id, challenge.challenge_id, students=students)
    except Exception as exc:
        # Keep Back/Refresh available during a transient Daily-status API failure.
        status = []
        status_error = exc
    completed = sum(row["status"] == "Complete" for row in status)
    total = len(status) if status_error is None else len(students)
    final = False if status_error is not None else _leaderboard_is_final(
        store, day, class_id, completed=completed, total=total
    )
    if status_error is None:
        board = _leaderboard_from_status(status, limit=10)
        _finish_teacher_refresh()
    else:
        board = []
        st.session_state.pop("teacher_refresh_pending", False)

    top_a, top_b = st.columns([1, 1])
    with top_a:
        if st.button("← Back to Teacher Dashboard", use_container_width=True, key="projector_back"):
            st.session_state["teacher_projector_mode"] = False
            st.rerun()
    with top_b:
        _teacher_refresh_control(key="projector_refresh")

    if status_error is not None:
        st.warning("Daily 10 status could not load just now. Tap Refresh data to try again, or go back to the Teacher Dashboard.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(status_error)
        return

    status_text = "FINAL TOP 10" if final else "LIVE TOP 10"
    sub = "Final standings for today" if final else f"{completed} of {total} finished · standings may change"
    st.markdown(
        f"<div class='finish-banner'><div class='big'>🏆 {html.escape(str(class_name))} — {status_text}</div>"
        f"<div class='sub'>{html.escape(sub)}</div></div>",
        unsafe_allow_html=True,
    )
    if not board:
        st.info("No students have finished the Daily 10 yet.")
        return

    medal = {1: "🥇", 2: "🥈", 3: "🥉"}
    rows = []
    for row in board:
        marker = medal.get(int(row["rank"]), f"{int(row['rank'])}.")
        rows.append(
            f"<div style='display:grid;grid-template-columns:76px 1fr;align-items:center;gap:18px;"
            f"padding:14px 18px;border-bottom:1px solid #e5e7eb;font-size:clamp(1.35rem,3vw,2.1rem);font-weight:850'>"
            f"<div>{marker}</div><div>{html.escape(str(row['nickname']))}</div></div>"
        )
    st.markdown("<div class='soft-card'>" + "".join(rows) + "</div>", unsafe_allow_html=True)
    st.caption("Student-safe display: rank + nickname only. Scores, times, PINs, and teacher data are hidden.")

def render_teacher_today(store: SupabaseFactStore) -> None:
    header_left, header_right = st.columns([4.2, 1.4])
    with header_left:
        st.markdown("### 📊 Today")
        st.caption("Done means Daily 10 + Fix Your Misses + Focus Practice are complete. The Mystery guess is optional.")
    with header_right:
        _teacher_refresh_control(key="teacher_today_refresh")

    classes = store.list_classes()
    if not classes:
        st.info("Create your first class in Classes & Rosters.")
        return
    class_by_name = {item.class_name: item for item in classes}
    selected_name = st.selectbox("Class", list(class_by_name), key="teacher_today_class")
    selected = class_by_name[selected_name]
    day, facts, challenge = ensure_today(store)

    # One roster read feeds every Today section. The remaining reads are the
    # actual data sets we need rather than reloading the roster for each one.
    students = store.list_students(selected.class_id)
    daily_status_error = None
    try:
        status = store.daily_status(selected.class_id, challenge.challenge_id, students=students)
    except Exception as exc:
        # Daily status cannot block independently loaded Igniter/teacher tools.
        status = []
        daily_status_error = exc
    if daily_status_error is None:
        progress_map = store.class_learning_progress(selected.class_id, challenge.challenge_id, students=students)
        learning_stats = store.class_learning_stats(selected.class_id, day, students=students)
    else:
        progress_map = {}
        learning_stats = {}
    warmup_error = None
    try:
        warmup_today = store.get_warmup_set(selected.class_id, day)
        warmup_rows = store.list_warmup_answers(day, day, class_id=selected.class_id) if warmup_today is not None else []
    except Exception as exc:
        # Warm-Up is a trial feature and must never take down the rest of the
        # Teacher Today dashboard. Surface the issue while preserving Daily,
        # Focus, leaderboard, and roster data.
        warmup_today = None
        warmup_rows = []
        warmup_error = exc
    completed_rows = [row for row in status if row.get("status") == "Complete"]
    if daily_status_error is None:
        _finish_teacher_refresh()
    else:
        st.session_state.pop("teacher_refresh_pending", False)

    total = len(status) if daily_status_error is None else len(students)
    full_complete = sum(
        bool(progress_map.get(row["student_id"]) and progress_map[row["student_id"]].completed_at)
        for row in status
    )
    not_started = sum(row["status"] == "Not started" for row in status)
    working = max(0, total - full_complete - not_started) if daily_status_error is None else 0
    daily_complete = len(completed_rows)
    average_accuracy = (
        sum(int(row["correct_count"]) for row in completed_rows) / len(completed_rows)
        if completed_rows else 0
    )
    median_time = (
        float(pd.Series([row["timed_seconds"] for row in completed_rows]).median())
        if completed_rows else 0
    )

    c1, c2, c3, c4 = st.columns(4)
    if daily_status_error is None:
        c1.metric("🟢 Done", f"{full_complete}/{total}")
        c2.metric("🟡 Working", working)
        c3.metric("⚪ Not started", not_started)
        c4.metric("Daily 10 finished", f"{daily_complete}/{total}")
    else:
        c1.metric("🟢 Done", "—")
        c2.metric("🟡 Working", "—")
        c3.metric("⚪ Not started", "—")
        c4.metric("Daily 10 finished", "—")
        st.warning("Daily 10 status could not load just now. Igniter results and other teacher tools are still available; tap Refresh data to retry the Daily snapshot.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(daily_status_error)
    if warmup_error is not None:
        st.warning("Warm-Up data could not load just now. The rest of Today is still available; try Refresh data once.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(warmup_error)

    if warmup_today is not None:
        real_ids = {student.student_id for student in students}
        warmup_rows = [row for row in warmup_rows if row.student_id in real_ids]
        q1_rows = [row for row in warmup_rows if row.question_slot == 1]
        q2_rows = [row for row in warmup_rows if row.question_slot == 2]
        warmup_done = {row.student_id for row in q1_rows} & {row.student_id for row in q2_rows}
        q1_accuracy = (sum(row.correct for row in q1_rows) / len(q1_rows) * 100) if q1_rows else None
        q2_accuracy = (sum(row.correct for row in q2_rows) / len(q2_rows) * 100) if q2_rows else None
        st.markdown("#### 🧠 Quick Warm-Up")
        w1, w2, w3 = st.columns(3)
        w1.metric("Finished", f"{len(warmup_done)}/{len(students)}")
        w2.metric("Spiral accuracy", "—" if q1_accuracy is None else f"{q1_accuracy:.0f}%")
        w3.metric("Yesterday accuracy", "—" if q2_accuracy is None else f"{q2_accuracy:.0f}%")
        st.caption("Unfinished students are not counted as incorrect. Open the groups below whenever you are ready to act on the current data.")
        if st.toggle("🎯 Show Warm-Up groups & email", key=f"teacher_today_warmup_groups_{selected.class_id}"):
            _render_warmup_groups_and_email(
                store, selected, day, warmup_today, warmup_rows, students,
                key_prefix=f"teacher_today_warmup_{selected.class_id}_{day.isoformat()}",
            )

    st.markdown("#### 🏆 Class Top 10")
    if daily_status_error is not None:
        st.caption("Daily standings are temporarily unavailable. Igniter results above are unaffected; tap Refresh data to retry.")
    else:
        board = _leaderboard_from_status(status, limit=10)
        final = _leaderboard_is_final(store, day, selected.class_id, completed=daily_complete, total=total)
        if final:
            st.success("**Final Top 10** · final standings for today")
        else:
            st.info(f"**Live Top 10** · {daily_complete} of {total} finished · standings may change")
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
                    store.set_app_setting(_leaderboard_final_key(day, selected.class_id), False)
                    st.rerun()
            elif not final:
                if st.button("Mark standings Final", use_container_width=True, key=f"final_top10_{selected.class_id}"):
                    store.set_app_setting(_leaderboard_final_key(day, selected.class_id), True)
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
        mix = daily_mix_summary(facts)
        st.caption(
            f"Core mix: {mix['easy']} easier retrieval · {mix['medium']} medium · {mix['hard']} harder"
            + (f" · {mix['extension']} 11/12 extension" if mix["extension"] else " · no 11/12 fact today")
        )
        for index, fact in enumerate(facts, start=1):
            st.write(f"{index}. **{fact.label} = {fact.product}** · {fact.tier}")

def render_teacher_classes(store: SupabaseFactStore, *, show_heading: bool = True) -> None:
    if show_heading:
        st.markdown("### 👥 Classes & Rosters")
        st.caption("Create classes, add students, view PINs, move students, or clean up accidental accounts.")
    flash = st.session_state.pop("teacher_roster_flash", None)
    if flash:
        kind, message = flash
        getattr(st, kind)(message)

    classes = store.list_classes(include_inactive=True)
    with st.expander("➕ Create a class", expanded=not bool(classes)):
        with st.form("create_class_form", clear_on_submit=True):
            class_name = st.text_input("New class name", placeholder="Example: Block 1")
            create = st.form_submit_button("Create class", use_container_width=True)
        if create:
            try:
                record = store.create_class(class_name)
                st.success(f"Created {record.class_name}.")
                st.rerun()
            except (ValueError, NameTaken) as exc:
                st.error(str(exc))
            except Exception:
                st.error("That class could not be created.")

    if not classes:
        return
    class_by_name = {item.class_name: item for item in classes}
    selected_name = st.selectbox("Class to manage", list(class_by_name), key="teacher_manage_class")
    selected = class_by_name[selected_name]
    st.caption(f"Class code: {selected.class_code} · {'Active' if selected.active else 'Inactive'}")

    roster = store.list_students(selected.class_id, include_inactive=True)
    created_info = st.session_state.bulk_created_credentials
    show_new_pins = bool(
        isinstance(created_info, dict)
        and created_info.get("class_id") == selected.class_id
        and created_info.get("rows")
    )

    with st.expander("➕ Add students", expanded=(not bool(roster) or show_new_pins)):
        st.caption("Paste nicknames one per line. Each student receives a 4-digit classroom PIN that stays visible to you.")
        with st.form("bulk_student_form", clear_on_submit=True):
            pasted = st.text_area("Nicknames", height=180, placeholder="FalconFox\nMathMaster\nBlueSky")
            create_students = st.form_submit_button("Create students + PINs", use_container_width=True, type="primary")
        if create_students:
            names = []
            seen = set()
            for line in pasted.splitlines():
                name = " ".join(line.strip().split())
                if not name:
                    continue
                key = name.casefold()
                if key not in seen:
                    names.append(name)
                    seen.add(key)
            if not names:
                st.error("Paste at least one nickname.")
            else:
                created = []
                errors = []
                for name in names:
                    pin = generate_pin()
                    try:
                        student = store.create_student(selected.class_id, name, pin)
                        created.append({"Nickname": student.nickname, "PIN": pin, "Class": selected.class_name})
                    except Exception as exc:
                        errors.append(f"{name}: {exc}")
                st.session_state.bulk_created_credentials = {"class_id": selected.class_id, "rows": created}
                if created:
                    message = f"Created {len(created)} student account{'s' if len(created) != 1 else ''}."
                    if errors:
                        message += " Some nicknames were skipped: " + " | ".join(errors[:8])
                    st.session_state["teacher_roster_flash"] = ("warning" if errors else "success", message)
                    st.rerun()
                if errors:
                    st.warning("Some nicknames were skipped: " + " | ".join(errors[:8]))

        created_info = st.session_state.bulk_created_credentials
        created = created_info.get("rows", []) if isinstance(created_info, dict) and created_info.get("class_id") == selected.class_id else []
        if created:
            st.markdown("#### New student PINs")
            cred_frame = pd.DataFrame(created)
            st.dataframe(cred_frame, hide_index=True, use_container_width=True)
            st.download_button(
                "Download new student PIN sheet (CSV)",
                cred_frame.to_csv(index=False).encode("utf-8"),
                file_name="new_student_pins.csv",
                mime="text/csv",
                use_container_width=True,
            )
            if st.button("Clear PIN sheet from screen", use_container_width=True):
                st.session_state.bulk_created_credentials = None
                st.rerun()

    st.markdown(f"#### Roster · {len(roster)} students")
    if not roster:
        st.info("No students in this class yet.")
        return

    roster_frame = pd.DataFrame([
        {
            "Nickname": student.nickname,
            "PIN": student.pin_code or "Reset once",
            "Status": "Active" if student.active else "Inactive",
        }
        for student in roster
    ])
    st.dataframe(roster_frame, hide_index=True, use_container_width=True)

    missing_pin_students = [student for student in roster if not student.pin_code]
    if missing_pin_students:
        st.warning(
            f"{len(missing_pin_students)} older account{'s' if len(missing_pin_students) != 1 else ''} need one new visible PIN. "
            "Their old hashed PIN cannot be recovered."
        )
        if st.button("Generate visible PINs for older accounts", use_container_width=True):
            regenerated = []
            for legacy_student in missing_pin_students:
                new_pin = generate_pin()
                store.reset_student_pin(legacy_student.student_id, new_pin)
                regenerated.append({"Nickname": legacy_student.nickname, "PIN": new_pin, "Class": selected.class_name})
            st.session_state["legacy_pin_refresh"] = {"class_id": selected.class_id, "rows": regenerated}
            st.rerun()

    refreshed = st.session_state.get("legacy_pin_refresh")
    if isinstance(refreshed, dict) and refreshed.get("class_id") == selected.class_id and refreshed.get("rows"):
        refreshed_frame = pd.DataFrame(refreshed["rows"])
        st.success("Replacement classroom PINs created. Students must use these new PINs from now on.")
        st.dataframe(refreshed_frame, hide_index=True, use_container_width=True)
        st.download_button(
            "Download replacement PINs (CSV)",
            refreshed_frame.to_csv(index=False).encode("utf-8"),
            file_name="replacement_student_pins.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.download_button(
        "Download roster + PINs",
        roster_frame.to_csv(index=False).encode("utf-8"),
        file_name=f"{selected.class_name.replace(' ', '_')}_roster.csv",
        mime="text/csv",
        use_container_width=True,
    )

    with st.expander("🔧 Roster Management", expanded=False):
        st.caption("Select one student or several. Moving preserves all student history. Delete is permanent.")
        roster_labels = [
            f"{student.nickname} · PIN {student.pin_code or 'reset once'}{' (inactive)' if not student.active else ''}"
            for student in roster
        ]
        roster_by_label = {
            f"{student.nickname} · PIN {student.pin_code or 'reset once'}{' (inactive)' if not student.active else ''}": student
            for student in roster
        }
        selected_roster_labels = st.multiselect(
            "Select student(s)", roster_labels, key=f"roster_manage_students_{selected.class_id}",
            placeholder="Choose one or more students",
        )

        other_classes = [item for item in classes if item.class_id != selected.class_id and item.active]
        st.markdown("##### Move selected")
        if other_classes:
            destination_by_name = {item.class_name: item for item in other_classes}
            destination_name = st.selectbox("Move to", list(destination_by_name), key=f"roster_move_destination_{selected.class_id}")
            if st.button("Move selected student(s)", use_container_width=True, disabled=not selected_roster_labels, key=f"roster_bulk_move_{selected.class_id}"):
                destination = destination_by_name[destination_name]
                moved = 0
                errors = []
                for selected_label in selected_roster_labels:
                    target = roster_by_label[selected_label]
                    try:
                        store.move_student(target.student_id, destination.class_id)
                        moved += 1
                    except Exception as exc:
                        errors.append(f"{target.nickname}: {exc}")
                st.session_state["teacher_roster_flash"] = (
                    "warning" if errors else "success",
                    (f"Moved {moved} student(s). Could not move: " + " | ".join(errors[:8])) if errors
                    else f"Moved {moved} student(s) from {selected.class_name} to {destination.class_name}.",
                )
                st.rerun()
        else:
            st.info("Create another active class first, then you can move students into it.")

        st.markdown("##### Delete selected")
        st.caption("Use only for accidental or duplicate accounts. Student-linked history is removed too.")
        confirm_bulk_delete = st.checkbox("I understand deletion is permanent.", key=f"roster_bulk_delete_confirm_{selected.class_id}")
        if st.button(
            "Delete selected student(s)", use_container_width=True,
            disabled=not selected_roster_labels or not confirm_bulk_delete, key=f"roster_bulk_delete_{selected.class_id}",
        ):
            targets = [roster_by_label[label] for label in selected_roster_labels]
            try:
                deleted = store.delete_students([target.student_id for target in targets])
                st.session_state["teacher_roster_flash"] = ("success", f"Permanently deleted {deleted} student account{'s' if deleted != 1 else ''}.")
            except Exception as exc:
                st.session_state["teacher_roster_flash"] = ("warning", f"Bulk delete did not finish: {exc}")
            st.rerun()

        with st.expander(f"⚠️ Clear this entire roster ({len(roster)} students)"):
            st.caption(f"Permanently deletes every student currently in {selected.class_name}, but keeps the class itself.")
            clear_phrase = f"DELETE {selected.class_name}"
            typed_clear = st.text_input(f"Type {clear_phrase} to confirm", key=f"clear_roster_phrase_{selected.class_id}")
            if st.button(
                f"Permanently delete all {len(roster)} students from {selected.class_name}",
                type="secondary", use_container_width=True, disabled=typed_clear.strip() != clear_phrase, key=f"clear_roster_{selected.class_id}",
            ):
                try:
                    deleted = store.delete_class_students(selected.class_id)
                    st.session_state["teacher_roster_flash"] = ("success", f"Permanently deleted all {deleted} student accounts from {selected.class_name}. The class itself was kept.")
                except Exception as exc:
                    st.session_state["teacher_roster_flash"] = ("warning", f"Roster clear did not finish: {exc}")
                st.rerun()

def render_teacher_class_hub(store: SupabaseFactStore) -> None:
    st.markdown("### 👥 Classes & Rosters")
    st.caption("Manage rosters here. Daily 10 Setup is tucked alongside class tools for the occasional schedule change.")
    class_tool = st.radio(
        "Class tools", ["👥 Rosters", "🎯 Daily 10 Setup"], horizontal=True,
        label_visibility="collapsed", key="teacher_class_tool",
    )
    if class_tool == "👥 Rosters":
        render_teacher_classes(store, show_heading=False)
    else:
        render_teacher_daily_setup(store, show_heading=False)


def render_teacher_student_tools(store: SupabaseFactStore) -> None:
    st.markdown("### 🛠️ Student Support")
    st.caption("Pick a student, then choose the one thing you need to do. Bulk roster work stays in Classes & Rosters.")
    classes = store.list_classes(include_inactive=True)
    if not classes:
        st.info("Create a class first.")
        return

    flash = st.session_state.pop("teacher_roster_flash", None)
    if flash:
        kind, message = flash
        getattr(st, kind)(message)

    class_by_name = {item.class_name: item for item in classes}
    class_name = st.selectbox("Class", list(class_by_name), key="teacher_tools_class")
    class_record = class_by_name[class_name]
    students = store.list_students(class_record.class_id, include_inactive=True)
    if not students:
        st.info("This class has no students yet.")
        return

    student_by_label = {
        f"{s.nickname}{' · inactive' if not s.active else ''}": s
        for s in students
    }
    label = st.selectbox("Student", list(student_by_label), key="teacher_tools_student")
    student = student_by_label[label]

    st.markdown(f"#### {student.nickname}")
    st.caption(f"{class_record.class_name} · {'Active' if student.active else 'Inactive'} · PIN {student.pin_code or 'reset once'}")

    action_key = f"student_support_action::{student.student_id}"
    if action_key not in st.session_state:
        st.session_state[action_key] = "account"
    row1a, row1b = st.columns(2)
    with row1a:
        if st.button("🔑 Account & PIN", use_container_width=True, key=f"support_account_{student.student_id}"):
            st.session_state[action_key] = "account"
    with row1b:
        if st.button("🧰 Fix today's Daily", use_container_width=True, key=f"support_daily_{student.student_id}"):
            st.session_state[action_key] = "daily"
    row2a, row2b = st.columns(2)
    with row2a:
        if st.button("🎯 Adjust Focus Practice", use_container_width=True, key=f"support_focus_{student.student_id}"):
            st.session_state[action_key] = "focus"
    with row2b:
        if st.button("↔️ Move / Status", use_container_width=True, key=f"support_move_{student.student_id}"):
            st.session_state[action_key] = "move"

    action = st.session_state.get(action_key, "account")
    st.markdown("---")

    if action == "account":
        st.markdown("#### 🔑 Account & PIN")
        with st.form(f"rename_student_form_{student.student_id}"):
            new_name = st.text_input("Nickname", value=student.nickname, max_chars=28)
            rename = st.form_submit_button("Save nickname", use_container_width=True)
        if rename:
            try:
                store.rename_student(student.student_id, new_name)
                st.session_state["teacher_roster_flash"] = ("success", "Nickname updated.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        if student.pin_code:
            st.info(f"Current classroom PIN: **{student.pin_code}**")
        else:
            st.warning("This older account needs one replacement PIN before it can be shown here.")
        if st.button("Generate new PIN", use_container_width=True, key=f"generate_pin_{student.student_id}"):
            pin = generate_pin()
            try:
                store.reset_student_pin(student.student_id, pin)
                st.session_state["last_reset_pin"] = {"student_id": student.student_id, "nickname": student.nickname, "pin": pin}
                st.rerun()
            except Exception:
                st.error("PIN reset failed.")
        reset_info = st.session_state.get("last_reset_pin")
        if reset_info and reset_info.get("student_id") == student.student_id:
            st.success(f"New PIN for {reset_info['nickname']}: **{reset_info['pin']}**")
            if st.button("Clear reset message", use_container_width=True, key=f"clear_pin_msg_{student.student_id}"):
                st.session_state.pop("last_reset_pin", None)
                st.rerun()

    elif action == "daily":
        st.markdown("#### 🧰 Fix today's Daily")
        st.caption("Use this only for a technology problem or accidental start. It gives this student a fresh Daily attempt.")
        try:
            _, _, challenge = ensure_today(store)
            attempt = store.get_attempt_for_student(student.student_id, challenge.challenge_id)
        except Exception:
            attempt = None
            challenge = None
        if attempt is None:
            st.info("No Daily attempt has been started today.")
        else:
            state = "Complete" if attempt.completed_at else "Timer running" if attempt.timed_started_at else "Opened"
            st.write(f"Current state: **{state}**")
            if st.button("Reset today's Daily attempt", use_container_width=True, type="primary", key=f"reset_daily_{student.student_id}"):
                store.reset_daily_attempt(student.student_id, challenge.challenge_id)
                st.success("Today's attempt was reset.")
                st.rerun()

    elif action == "focus":
        st.markdown("#### 🎯 Adjust Focus Practice")
        st.caption("Automatic follows this student's evolving mastery. Use an override only when you intentionally want to steer practice.")
        override_options = ["Automatic"] + [f"{value}s" for value in range(2, 11)]
        current_override = store.get_student_focus_override(student.student_id)
        personal_choice = st.selectbox(
            "Student Focus", override_options, index=override_options.index(_override_label(current_override)),
            key=f"student_focus_override_{student.student_id}",
        )
        if st.button("Save Focus setting", use_container_width=True, type="primary", key=f"save_student_focus_{student.student_id}"):
            store.set_student_focus_override(student.student_id, _override_value(personal_choice))
            st.success("Student Focus setting saved.")
            st.rerun()

    else:
        st.markdown("#### ↔️ Move / Status")
        if len(classes) >= 2:
            destination_options = [item for item in classes if item.class_id != student.class_id]
            destination_by_name = {item.class_name: item for item in destination_options}
            destination_name = st.selectbox("Move to another class", list(destination_by_name), key=f"move_student_destination_{student.student_id}")
            st.caption("Moving keeps the student's PIN, mastery, completed-day history, streak, saved work, and Mystery history.")
            if st.button("Move student", use_container_width=True, key=f"move_student_{student.student_id}"):
                try:
                    destination = destination_by_name[destination_name]
                    store.move_student(student.student_id, destination.class_id)
                    st.session_state["teacher_roster_flash"] = ("success", f"Moved {student.nickname} to {destination.class_name}.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.caption("Create another class before moving this student.")

        target_active = not student.active
        status_label = "Reactivate student" if target_active else "Deactivate student"
        if st.button(status_label, use_container_width=True, key=f"student_active_{student.student_id}"):
            store.set_student_active(student.student_id, target_active)
            st.rerun()

    st.markdown("---")
    st.markdown("#### ⚠️ Danger Zone")
    st.caption("Bulk moves and roster cleanup tools are in Classes & Rosters. Permanent deletion stays here because it affects only this student.")
    with st.expander("Permanently delete this student", expanded=False):
        st.warning("Permanent: removes this account and linked Daily, mastery, reward, and Mystery history. Use Move instead if the student belongs in another class.")
        confirm_delete = st.checkbox(f"I want to permanently delete {student.nickname}.", key=f"confirm_delete_student_{student.student_id}")
        if st.button(
            "Delete student permanently", use_container_width=True, disabled=not confirm_delete, key=f"delete_student_{student.student_id}",
        ):
            try:
                store.delete_student(student.student_id)
                reset_info = st.session_state.get("last_reset_pin")
                if reset_info and reset_info.get("student_id") == student.student_id:
                    st.session_state.pop("last_reset_pin", None)
                st.session_state["teacher_roster_flash"] = ("success", f"Deleted {student.nickname}.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

def _mystery_raffle_setting_key(week_start, class_id: str) -> str:
    return f"weekly_mystery_raffle::{week_start.isoformat()}::{class_id}"

def _mystery_raffle_has_pending_draw(store: SupabaseFactStore, week_start) -> bool:
    """Return True when a class has eligible solvers but no valid saved winner."""
    try:
        eligible = store.weekly_mystery_correct_students(week_start)
        classes = store.list_classes()
    except Exception:
        return False

    eligible_by_class = {}
    for item in eligible:
        eligible_by_class.setdefault(str(item.get("class_id") or ""), []).append(item)

    for class_record in classes:
        class_id = str(class_record.class_id)
        pool = list(eligible_by_class.get(class_id, []))
        if not pool:
            continue
        try:
            saved = store.get_app_setting(_mystery_raffle_setting_key(week_start, class_id))
        except Exception:
            saved = None
        eligible_ids = {str(item.get("student_id") or "") for item in pool}
        winner_is_valid = isinstance(saved, dict) and str(saved.get("student_id") or "") in eligible_ids
        if not winner_is_valid:
            return True
    return False

def _render_teacher_mystery_raffle(
    store: SupabaseFactStore, week_start, *, day, heading: str = "Friday Prize Raffles", caption: str | None = None
) -> None:
    st.markdown(f"#### 🎟️ {heading}")
    st.caption(caption or "Each class gets its own winner. Every real student who solves the Mystery correctly gets one equal entry in their class raffle.")
    try:
        eligible = store.weekly_mystery_correct_students(week_start)
        classes = store.list_classes()
    except Exception as exc:
        st.error("The raffle list could not be loaded.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return

    eligible_by_class = {}
    for item in eligible:
        eligible_by_class.setdefault(str(item.get("class_id") or ""), []).append(item)

    raffle_open = day >= (week_start + timedelta(days=4))
    if not raffle_open:
        st.info("Entries are still building. Each class Draw Winner button opens Friday.")

    if not classes:
        st.caption("No active classes are available for a raffle.")
        return

    for class_record in classes:
        class_id = str(class_record.class_id)
        pool = list(eligible_by_class.get(class_id, []))
        setting_key = _mystery_raffle_setting_key(week_start, class_id)
        try:
            saved = store.get_app_setting(setting_key)
        except Exception:
            saved = None

        st.markdown(f"##### 🎟️ {class_record.class_name}")
        st.write(f"**{len(pool)} eligible student{'s' if len(pool) != 1 else ''}**")
        with st.expander(f"View {class_record.class_name} entries", expanded=False):
            if not pool:
                st.caption("No correct solvers yet.")
            else:
                for item in pool:
                    when = "Thursday" if int(item.get("guess_day") or 5) == 4 else "Friday"
                    st.write(f"🎟️ **{item['nickname']}** · solved {when}")

        eligible_by_id = {str(item["student_id"]): item for item in pool}
        winner = saved if isinstance(saved, dict) else None
        winner_is_valid = winner and str(winner.get("student_id") or "") in eligible_by_id
        if winner_is_valid:
            item = eligible_by_id[str(winner["student_id"])]
            st.success(f"🏆 **{class_record.class_name} winner: {item['nickname']}**")
            with st.expander(f"Need to redraw {class_record.class_name}?", expanded=False):
                st.warning("Redraw only if you need to replace the saved winner, such as when the student is absent.")
                confirm = st.checkbox(
                    f"I want to replace the saved {class_record.class_name} winner.",
                    key=f"confirm_raffle_redraw_{week_start}_{class_id}",
                )
                if st.button(
                    f"🎲 Redraw {class_record.class_name} winner", use_container_width=True,
                    disabled=not confirm, key=f"redraw_raffle_{week_start}_{class_id}",
                ):
                    new_item = random.SystemRandom().choice(pool)
                    store.set_app_setting(setting_key, {
                        "student_id": new_item["student_id"], "nickname": new_item["nickname"],
                        "class_id": class_id, "class_name": class_record.class_name,
                        "drawn_at": utc_now().isoformat(),
                    })
                    st.rerun()
        else:
            if winner:
                st.warning("The saved winner is no longer eligible. Draw a new winner below.")
            if not pool:
                st.caption("No raffle entries in this class yet.")
            if st.button(
                f"🎲 Draw {class_record.class_name} Winner", use_container_width=True, type="primary",
                disabled=(not pool or not raffle_open), key=f"draw_raffle_{week_start}_{class_id}",
            ):
                item = random.SystemRandom().choice(pool)
                store.set_app_setting(setting_key, {
                    "student_id": item["student_id"], "nickname": item["nickname"],
                    "class_id": class_id, "class_name": class_record.class_name,
                    "drawn_at": utc_now().isoformat(),
                })
                st.rerun()
        st.markdown("---")

def _mystery_bank_label(mystery) -> str:
    return f"{mystery.category} · {mystery.answer}"

def _render_teacher_mystery_preview(mystery, *, label: str) -> None:
    st.markdown(
        f"<div class='hero-card'><div class='section-label'>{html.escape(label)} · {html.escape(mystery.category)}</div>"
        f"<div style='font-size:1.65rem;font-weight:950'>{html.escape(mystery.answer)}</div>"
        f"<div style='margin-top:.35rem'>{html.escape(mystery.reveal_note)}</div></div>",
        unsafe_allow_html=True,
    )
    for index, clue in enumerate(mystery.clues[:5], start=1):
        day_name = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")[index-1]
        st.write(f"**Clue #{index} · {day_name}:** {clue}")
    with st.expander("📚 Student learning reveal", expanded=False):
        st.write(learning_paragraph_for(mystery))
        st.info(f"🤯 **Fun fact:** {mystery.reveal_note}")

def render_teacher_weekly_mystery(store: SupabaseFactStore) -> None:
    st.markdown("### 🕵️ Weekly Mystery")
    st.caption("One shared just-for-fun mystery. Full routines earn one clue Monday–Friday; Guess #1 is Thursday and Guess #2 is Friday.")
    st.caption("Student guesses ignore capitalization/punctuation, honor your accepted aliases, and allow only small plausible spelling mistakes (for example, Abraham Lincon).")
    day = current_daily_date()
    try:
        week_start, record, mystery = ensure_weekly_mystery(store, day)
        locked = store.weekly_mystery_locked(week_start)
        stats = store.weekly_mystery_teacher_stats(week_start)
    except Exception as exc:
        st.error("The Weekly Mystery tables are not ready. Check the earlier v2.5 Mystery database migration.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return

    previous_week = week_start - timedelta(days=7)
    if _mystery_raffle_has_pending_draw(store, previous_week):
        previous_label = previous_week.strftime('%B %d, %Y').replace(' 0', ' ')
        st.warning("🎟️ You still have an undrawn raffle from last week. You can finish it here without changing this week's Mystery.")
        _render_teacher_mystery_raffle(
            store, previous_week, day=day,
            heading=f"Last Week's Prize Raffles · {previous_label}",
            caption="Finish any missed Friday drawing here. Saved winners stay attached to last week and do not affect the new week's Mystery.",
        )
        st.markdown("---")

    st.markdown(f"#### This Week · {week_start.strftime('%B %d, %Y').replace(' 0', ' ')}")
    _render_teacher_mystery_preview(mystery, label="Teacher preview")

    c1, c2, c3 = st.columns(3)
    c1.metric("Students unlocked", int(stats.get("students_unlocked", 0)))
    c2.metric("Guesses used", int(stats.get("guesses", 0)))
    c3.metric("Solved", int(stats.get("correct", 0)))

    if locked:
        st.info("🔒 This week's mystery is locked because at least one student has already earned a clue.")
    else:
        st.success("You can still swap this week's mystery. It locks automatically when the first student earns a clue.")
        if st.button("🔄 Pick another mystery for this week", use_container_width=True, key="swap_current_mystery"):
            try:
                next_item = mystery_for_key(next_mystery_key(record.mystery_key))
                store.save_mystery_plan(week_start, mystery_to_plan(next_item))
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    _render_teacher_mystery_raffle(store, week_start, day=day)

    st.markdown("---")
    next_week = week_start + timedelta(days=7)
    st.markdown(f"#### 📅 Next Week's Mystery · {next_week.strftime('%B %d, %Y').replace(' 0', ' ')}")
    st.caption("Plan ahead without changing this week's mystery. Your saved choice automatically becomes active when the new school week begins.")

    saved_plan = store.get_mystery_plan(next_week)
    next_record = store.get_weekly_mystery(next_week)
    if saved_plan:
        next_mystery = mystery_from_plan(saved_plan)
        plan_status = "Saved teacher plan"
    elif next_record is not None:
        next_mystery = mystery_for_key(next_record.mystery_key)
        plan_status = "Scheduled mystery"
    else:
        next_mystery = mystery_for_key(default_mystery_key_for_week(next_week))
        plan_status = "Automatic selection"
    _render_teacher_mystery_preview(next_mystery, label=plan_status)

    bank_items = [mystery_for_key(item.key) for item in MYSTERIES]
    bank_by_label = {_mystery_bank_label(item): item for item in bank_items}
    current_bank_label = _mystery_bank_label(mystery_for_key(next_mystery.key)) if next_mystery.key in {item.key for item in MYSTERIES} else list(bank_by_label)[0]
    selected_bank_label = st.selectbox(
        "Choose a curated mystery",
        list(bank_by_label),
        index=list(bank_by_label).index(current_bank_label) if current_bank_label in bank_by_label else 0,
        key="next_week_mystery_bank",
    )
    bank_a, bank_b = st.columns(2)
    with bank_a:
        if st.button("Use selected bank mystery", use_container_width=True, key="use_next_bank_mystery"):
            try:
                store.save_mystery_plan(next_week, mystery_to_plan(bank_by_label[selected_bank_label]))
                st.success("Next week's mystery saved.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with bank_b:
        if st.button("Reset next week to automatic", use_container_width=True, key="reset_next_mystery"):
            try:
                store.clear_mystery_plan(next_week)
                default_key = default_mystery_key_for_week(next_week)
                existing = store.get_weekly_mystery(next_week)
                if existing is not None and existing.mystery_key != default_key:
                    store.replace_weekly_mystery(next_week, default_key)
                st.success("Next week is back to the automatic mystery rotation.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with st.expander("✏️ Edit/customize next week's mystery", expanded=False):
        st.caption("You can customize the answer, all five daily clues, learning paragraph, and fun fact. These edits affect next week only.")
        base_plan = mystery_to_plan(next_mystery)
        with st.form("next_week_mystery_editor"):
            answer = st.text_input("Mystery answer", value=str(base_plan["answer"]), max_chars=80)
            category = st.text_input("Category", value=str(base_plan["category"]), max_chars=80)
            edited_clues = []
            for index, clue in enumerate(base_plan["clues"][:5], start=1):
                day_name = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")[index-1]
                edited_clues.append(st.text_input(f"Clue #{index} · {day_name}", value=str(clue), max_chars=240))
            paragraph = st.text_area("Learning paragraph shown after reveal", value=str(base_plan["learning_paragraph"]), height=140, max_chars=1200)
            fun_fact = st.text_area("Fun fact", value=str(base_plan["fun_fact"]), height=90, max_chars=500)
            aliases = st.text_input("Accepted alternate answers (comma-separated, optional)", value=", ".join(base_plan.get("aliases") or []), max_chars=300)
            save_custom = st.form_submit_button("Save customized next-week mystery", use_container_width=True, type="primary")
        if save_custom:
            cleaned_clues = [" ".join(str(value or "").split()) for value in edited_clues]
            if not answer.strip() or any(not clue for clue in cleaned_clues):
                st.error("The answer and all five clues are required.")
            else:
                plan = {
                    "mystery_key": str(base_plan.get("mystery_key") or next_mystery.key),
                    "category": " ".join(category.split()) or next_mystery.category,
                    "answer": " ".join(answer.split()),
                    "clues": cleaned_clues,
                    "learning_paragraph": " ".join(paragraph.split()),
                    "fun_fact": " ".join(fun_fact.split()),
                    "aliases": [" ".join(value.split()) for value in aliases.split(",") if value.strip()],
                }
                try:
                    store.save_mystery_plan(next_week, plan)
                    st.success("Customized next-week mystery saved. This week's mystery was not changed.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with st.expander(f"Mystery bank · {len(MYSTERIES)} curated mysteries", expanded=False):
        st.caption("Places · animals · foods · sports · science/nature · history/people · music/entertainment · games/toys/objects")
        st.write("The bank is stored inside the app, so clue delivery never depends on a live internet search.")

def _test_student_backup_keys() -> tuple[str, ...]:
    return ("student_id", "student_nickname", "student_class_id", "student_class_name", "student_is_test")

def _enter_teacher_test_student(store: SupabaseFactStore, class_record, *, reset: bool = False) -> None:
    if "teacher_test_student_backup" not in st.session_state:
        st.session_state["teacher_test_student_backup"] = {key: st.session_state.get(key) for key in _test_student_backup_keys()}
    student = store.reset_test_student(class_record.class_id) if reset else store.get_test_student(class_record.class_id)
    if student is None:
        student = store.reset_test_student(class_record.class_id)
    _set_student_session(student, class_record)
    st.session_state["teacher_test_student_mode"] = True
    st.session_state["teacher_test_student_class_id"] = class_record.class_id
    st.rerun()

def _exit_teacher_test_student() -> None:
    backup = st.session_state.pop("teacher_test_student_backup", {}) or {}
    for key in _test_student_backup_keys():
        st.session_state[key] = backup.get(key)
    st.session_state["teacher_test_student_mode"] = False
    st.session_state.pop("teacher_test_student_class_id", None)
    st.rerun()

def render_teacher_warmup(store: SupabaseFactStore) -> None:
    """Render Teacher → Warm-Up using the shared teacher refresh contract."""
    return _render_teacher_warmup_module(
        store,
        refresh_control=_teacher_refresh_control,
        finish_refresh=_finish_teacher_refresh,
    )

def render_teacher_test_student_launcher(store: SupabaseFactStore) -> None:
    st.markdown("### 🧪 Test Student Sandbox")
    st.caption("Run the real student workflow as many times as you want without affecting real rosters, Top 10, mastery heatmaps, class completion, Mystery stats, or raffle entries.")
    classes = store.list_classes()
    if not classes:
        st.info("Create a real class first so the sandbox has a class context.")
        return
    by_name = {item.class_name: item for item in classes}
    class_name = st.selectbox("Use class context", list(by_name), key="teacher_test_student_class")
    selected = by_name[class_name]
    existing = store.get_test_student(selected.class_id)
    if existing is not None:
        st.success(f"Sandbox ready in {selected.class_name}. It is hidden from real class data.")
    else:
        st.info("No sandbox run exists for this class yet. Starting it will create a hidden Test Student.")
    a, b = st.columns(2)
    with a:
        if st.button("▶ Open Test Student", use_container_width=True, type="primary", key="open_test_student"):
            _enter_teacher_test_student(store, selected, reset=False)
    with b:
        if st.button("↻ Reset & start fresh", use_container_width=True, key="reset_test_student_launcher"):
            _enter_teacher_test_student(store, selected, reset=True)
    st.caption("Reset & start fresh wipes only the hidden sandbox account and immediately recreates it. Real student data is untouched.")

def render_teacher_test_student_mode(store: SupabaseFactStore) -> None:
    class_id = st.session_state.get("teacher_test_student_class_id")
    classes = store.list_classes()
    class_record = next((item for item in classes if item.class_id == class_id), None)
    if class_record is None:
        _exit_teacher_test_student()
        return
    student = store.get_test_student(class_record.class_id)
    if student is None:
        student = store.reset_test_student(class_record.class_id)
    _set_student_session(student, class_record)

    left, right = st.columns([2.5, 2])
    with left:
        if st.button("← Back to Teacher Dashboard", use_container_width=True, key="exit_test_student"):
            _exit_teacher_test_student()
    with right:
        if st.button("↻ Reset Test Student", use_container_width=True, key="reset_test_student_mode"):
            student = store.reset_test_student(class_record.class_id)
            _set_student_session(student, class_record)
            st.rerun()
    st.warning("🧪 **TEST STUDENT SANDBOX** · This is the real student workflow, but this account is excluded from real classroom results and raffle entries.")
    render_daily(store)

def render_teacher(store: SupabaseFactStore | None) -> None:
    if store is None:
        st.markdown("## Teacher Dashboard")
        render_db_setup_message()
        return
    if not teacher_login():
        return

    if st.session_state.get("teacher_test_student_mode"):
        render_teacher_test_student_mode(store)
        return

    if st.session_state.get("teacher_projector_mode"):
        render_teacher_projector(store)
        return

    top_left, top_right = st.columns([7, 1])
    with top_left:
        st.markdown("## Teacher Dashboard")
        st.caption("Today and Warm-Up are your everyday tools. Only the section you open loads; students still only see their class Top 10.")
    with top_right:
        if st.button("Log out"):
            st.session_state.teacher_authed = False
            st.session_state["teacher_projector_mode"] = False
            st.rerun()

    teacher_sections = [
        "📊 Today", "🧠 Warm-Up", "📈 Learning Data", "🛠️ Student Support",
        "🕵️ Weekly Mystery", "👥 Classes & Rosters", "🖥️ Clock", "🧪 Test Student",
    ]
    section = st.radio(
        "Teacher section", teacher_sections, horizontal=True, label_visibility="collapsed", key="teacher_section"
    )
    if section == "📊 Today":
        render_teacher_today(store)
    elif section == "🧠 Warm-Up":
        render_teacher_warmup(store)
    elif section == "📈 Learning Data":
        render_teacher_mastery_focus(store)
    elif section == "🕵️ Weekly Mystery":
        render_teacher_weekly_mystery(store)
    elif section == "🛠️ Student Support":
        render_teacher_student_tools(store)
    elif section == "👥 Classes & Rosters":
        render_teacher_class_hub(store)
    elif section == "🖥️ Clock":
        render_teacher_clock(store)
    else:
        render_teacher_test_student_launcher(store)

    st.markdown("---")
    st.caption(f"Teal's Daily Fact Challenge · v{APP_VERSION} · Teacher-only data is never shown on student leaderboards.")

# ---------------------------------------------------------------------------
# Hidden diagnostic
# ---------------------------------------------------------------------------
def maybe_render_db_diagnostic(store: SupabaseFactStore | None) -> None:
    if str(st.query_params.get("dbcheck", "0")) != "1":
        return
    with st.expander("Database diagnostic", expanded=False):
        if store is None:
            st.error("Supabase secrets are missing or the client could not initialize.")
            return
        try:
            store.health_check()
            st.success("Database connection is working.")
            if getattr(store, "url_was_normalized", False):
                st.info("SUPABASE_URL included /rest/v1 and was automatically normalized for the Python client.")
        except Exception as exc:
            st.exception(exc)

# Render the visible shell before any database-dependent startup work.  If
# Streamlit or Supabase is slow, students should see the Fact Challenge title
# and navigation rather than a blank page with only the framework spinner.
mode = render_header()
store = _timed_app_call("create_store", get_store, log_after_seconds=0.75)
if mode != "Teacher":
    _timed_app_call(
        "remembered_login",
        lambda: handle_persistent_student_login(store),
        log_after_seconds=0.75,
    )
    mode = st.session_state.app_mode
maybe_render_db_diagnostic(store)

if mode == "Daily Challenge":
    _timed_app_call("render_daily", lambda: render_daily(store), log_after_seconds=1.25)
elif mode == "Practice":
    _timed_app_call("render_practice", lambda: render_practice(store), log_after_seconds=1.25)
else:
    _timed_app_call("render_teacher", lambda: render_teacher(store), log_after_seconds=1.25)
