from __future__ import annotations

from datetime import datetime, timezone
import html
import hmac
import random
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
from fact_store import FactStoreError, NameTaken, generate_pin, utc_now
from adaptive_engine import (
    FOCUS_SESSION_LENGTH,
    STATUS_BUILDING,
    STATUS_FLUENT,
    STATUS_FOCUS,
    STATUS_UNKNOWN,
    build_focus_plan,
    complete_mastery_map,
    status_for_display,
)
from supabase_fact_store import SupabaseFactStore
from persistent_login import REMEMBER_DAYS, issue_student_token, peek_student_id, verify_student_token
from weekly_mystery import (
    MYSTERIES,
    default_mystery_key_for_week,
    is_correct_guess,
    learning_paragraph_for,
    mystery_for_key,
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
def load_store() -> SupabaseFactStore:
    return SupabaseFactStore.from_secrets(st.secrets)


def get_store() -> SupabaseFactStore | None:
    if not database_configured():
        return None
    try:
        return load_store()
    except Exception:
        return None


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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


def switch_mode(mode: str) -> None:
    st.session_state.app_mode = mode


def sign_out() -> None:
    st.session_state.persistent_login_pending_action = {"action": "clear"}
    st.session_state.persistent_login_check_complete = False
    for key in ("student_id", "student_nickname", "student_class_id", "student_class_name"):
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
        student_id = peek_student_id(token)
        if not student_id:
            raise ValueError("Missing student id")
        student = store.get_student(student_id)
        if not student.active:
            raise ValueError("Inactive student")
        payload = verify_student_token(token, student.pin_code, _persistent_login_secret())
        if payload is None:
            raise ValueError("Expired or invalid remembered login")
        classes = store.list_classes()
        class_record = next((item for item in classes if item.class_id == student.class_id), None)
        if class_record is None:
            raise ValueError("Student class is not active")
        _set_student_session(student, class_record)
        st.rerun()
    except Exception:
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


def format_seconds(seconds: float | None) -> str:
    value = float(seconds or 0.0)
    if value < 60:
        return f"{value:.1f}s"
    minutes = int(value // 60)
    remainder = value - minutes * 60
    return f"{minutes}:{remainder:04.1f}"


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
        "mystery": "4 · Mystery",
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


def strategy_tip(fact: Fact) -> str:
    a, b = fact.a, fact.b
    pair = {a, b}
    if 10 in pair:
        other = b if a == 10 else a
        return f"Think ×10: {other} tens = {fact.product}."
    if 5 in pair:
        other = b if a == 5 else a
        return f"Count by 5s {other} times, or take half of {other} × 10."
    if 2 in pair:
        other = b if a == 2 else a
        return f"×2 means double: {other} + {other} = {fact.product}."
    if a == b:
        return f"This is a square fact: {a} × {a} = {fact.product}."
    if 9 in pair:
        other = b if a == 9 else a
        return f"Use ×10 and subtract one group: {other * 10} − {other} = {fact.product}."
    if 11 in pair:
        other = b if a == 11 else a
        return f"Break 11 apart: 10 × {other} + 1 × {other} = {other * 10} + {other} = {fact.product}."
    if 12 in pair:
        other = b if a == 12 else a
        return f"Break 12 apart: 10 × {other} + 2 × {other} = {other * 10} + {other * 2} = {fact.product}."
    if 4 in pair:
        other = b if a == 4 else a
        return f"Double twice: {other} × 2 = {other * 2}, then double {other * 2} to get {fact.product}."
    if 3 in pair:
        other = b if a == 3 else a
        return f"Use a double plus one more group: 2 × {other} = {2 * other}, then + {other} = {fact.product}."
    if 6 in pair:
        other = b if a == 6 else a
        return f"Use 5 groups plus 1 more: 5 × {other} = {5 * other}, then + {other} = {fact.product}."
    if 7 in pair:
        other = b if a == 7 else a
        return f"Use 5 groups plus 2 more: 5 × {other} = {5 * other} and 2 × {other} = {2 * other}; together = {fact.product}."
    if 8 in pair:
        other = b if a == 8 else a
        return f"Use 10 groups minus 2 groups: {10 * other} − {2 * other} = {fact.product}."
    larger = max(a, b)
    smaller = min(a, b)
    return f"Break it into an easier fact you know, then put the groups back together: {smaller} × {larger} = {fact.product}."


def render_header() -> str:
    st.markdown("<h1 class='top-title'>Teal's Daily Fact Challenge</h1>", unsafe_allow_html=True)
    st.markdown("<div class='subtitle'>10 facts a day · accuracy first · speed breaks ties</div>", unsafe_allow_html=True)
    mode = st.radio(
        "App mode",
        ["Daily Challenge", "Practice", "Teacher"],
        horizontal=True,
        label_visibility="collapsed",
        key="app_mode",
    )
    if student_signed_in() and mode != "Teacher":
        left, right = st.columns([5, 1.4])
        with left:
            st.caption(f"👤 {st.session_state.student_nickname} · {st.session_state.student_class_name}")
        with right:
            st.button("Sign out", use_container_width=True, on_click=sign_out)
    return mode


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
        if st.button("Open Practice without signing in", use_container_width=True, on_click=switch_mode, args=("Practice",)):
            pass
        return False

    try:
        classes = store.list_classes()
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
def ensure_weekly_mystery(store: SupabaseFactStore, day):
    week_start = week_start_for(day)
    record = store.get_or_create_weekly_mystery(week_start, default_mystery_key_for_week(week_start))
    return week_start, record, mystery_for_key(record.mystery_key)


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
    _render_mystery_learning(mystery)


def render_weekly_mystery_reward(store: SupabaseFactStore, day, challenge) -> None:
    """Earn clues Monday-Thursday; guessing exists only Thursday and Friday."""
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

    # Clues are earned only by completing Monday-Thursday. Friday never
    # backfills clues a student skipped earlier in the week.
    clue_count = min(4, sum(1 for row in unlocks if 1 <= int(row.day_number) <= 4))
    completed_days = {int(row.day_number) for row in unlocks}
    guess_by_day = {int(row.guess_day): row for row in guesses}
    solved_guess = next((row for row in guesses if row.correct), None)

    st.markdown("### 🕵️ This Week's Mystery")
    st.caption("Earn one clue for each full routine Monday–Thursday. Guess #1 is Thursday; Guess #2 is Friday.")
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

    # Friday: completing Friday unlocks the second/final guess and the reveal,
    # but it does not grant any missed Monday-Thursday clues.
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

    st.markdown("### 🏆 Today's Top 10")
    st.caption(f"{finished} of {roster_count} finished · rank is based on accuracy first, with time used privately as the tiebreaker")
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
    return {
        "activity_index": int(activity_index),
        "a": fact.a, "b": fact.b, "product": fact.product,
        "strategy": strategy_tip(fact),
        "repeated_addition": repeated_addition_text(fact),
        "start_state": start_state,
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
            fact, activity_index=q, start_state="teach",
            original_answer=int(ans.student_answer), first_already_recorded=True,
        )
        for q, fact, ans in remaining
    ]

    st.markdown("## Learning Step 2 of 3 · Fix Your Misses")
    st.caption("A miss is useful information. Learn it, answer it correctly, then move on.")
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
        st.error("That correction session did not finish cleanly. Please try the remaining fact again.")
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
        st.error("Your Focus Practice plan could not be prepared. Ask your teacher to refresh the app.")
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
            start_state="teach" if first is not None and not first.correct else "question",
            first_already_recorded=first is not None,
        ))

    override = get_cached_focus_override(store, challenge)
    st.markdown("## Learning Step 3 of 3 · 🎯 Your Focus Practice")
    if override:
        st.caption(f"8 short retrievals · your teacher has temporarily focused this practice on the {override}s")
    else:
        st.caption("8 short retrievals picked from what the app is gradually learning about you — no placement test.")
    st.caption("Answer all 8. If one is tricky, the app will teach it and let you try again.")

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
            st.error("That Focus session did not finish cleanly. Please try the remaining fact again.")
            return False
        if idx not in existing_first and item_events[0]["is_retry"]:
            st.error("That Focus session could not verify the first attempt. Please try again.")
            return False
        if idx in existing_first and any(not event["is_retry"] for event in item_events):
            st.error("That Focus session duplicated a first attempt. Please try again.")
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
    st.caption("Your fact map grows from normal Daily and Focus work. It starts blank — there is no placement test.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟢 Fluent", summary.get(STATUS_FLUENT, 0))
    c2.metric("🟡 Building", summary.get(STATUS_BUILDING, 0))
    c3.metric("🔴 Focus", summary.get(STATUS_FOCUS, 0))
    c4.metric("⚪ Learning", summary.get(STATUS_UNKNOWN, 0))


def render_day_complete(store: SupabaseFactStore, day, facts: list[Fact], challenge, attempt, answers) -> None:
    stats = store.student_learning_stats(st.session_state.student_id, day)
    streak = int(stats.get("current_streak", 0))
    stars = int(stats.get("stars", 0))

    render_routine_strip("mystery")
    st.markdown(
        "<div class='finish-banner'><div class='big'>✅ YOU'RE DONE FOR TODAY!</div>"
        "<div class='sub'>Daily 10 ✓ &nbsp; · &nbsp; Fix Misses ✓ &nbsp; · &nbsp; Focus Practice ✓</div>"
        "<div style='margin-top:.45rem'>Your learning work is finished for today.</div></div>",
        unsafe_allow_html=True,
    )
    if streak in {3, 5, 10, 20, 30, 50} or (streak > 0 and streak % 50 == 0):
        st.success(f"🎉 {streak}-day Learning Streak! · ⭐ {stars} total Daily Stars")
    elif streak:
        st.success(f"🔥 {streak}-day Learning Streak · ⭐ {stars} total Daily Stars")
    else:
        st.success(f"⭐ Daily Star earned · {stars} total")

    st.markdown("## 🕵️ You earned today's Mystery reward!")
    render_weekly_mystery_reward(store, day, challenge)

    st.markdown("### ✅ That's it — see you next Challenge day! 👋")
    st.caption("Everything below is optional. Your required work is complete.")
    with st.expander("🌱 See My Growth", expanded=False):
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


def render_classroom_connection_retry(exc: Exception, *, key: str = "classroom_retry") -> None:
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


def render_completed_daily(store: SupabaseFactStore, day, facts: list[Fact], challenge, attempt) -> None:
    try:
        answers = store.get_answers(attempt.attempt_id)
        progress = store.get_or_create_learning_progress(st.session_state.student_id, challenge.challenge_id)
    except Exception as exc:
        render_classroom_connection_retry(exc, key="retry_completed_load")
        return

    # Keep one leaderboard snapshot through Fix Your Misses + Focus Practice.
    # Every submitted Focus answer reruns Streamlit, so reloading roster + standings
    # here was making the Top 10 compete with the student's personalized practice.
    try:
        leaderboard_context = get_cached_leaderboard_context(
            store, challenge, refresh=bool(progress.completed_at)
        )
    except Exception:
        leaderboard_context = st.session_state.get(_leaderboard_cache_key(challenge))

    if leaderboard_context is not None:
        render_daily_result_summary(store, day, challenge, attempt, leaderboard_context=leaderboard_context)
    else:
        st.markdown(f"## Daily 10 complete · {day.strftime('%B %d').replace(' 0', ' ')}")
        st.success("Daily 10 saved ✓")
        st.caption("The class Top 10 is updating. It will reappear when the classroom connection settles.")

    leaderboard_seen_key = f"student_top10_seen_{st.session_state.student_id}_{challenge.challenge_id}"
    if leaderboard_context is not None and not st.session_state.get(leaderboard_seen_key):
        render_leaderboard(
            store, challenge, highlight_student_id=st.session_state.student_id, context=leaderboard_context
        )
        # Show the board once immediately after the Daily. Later Fix/Focus reruns
        # reuse the cached standings without making students scroll past it again.
        st.session_state[leaderboard_seen_key] = True

    missed_count = sum(not answer.correct for answer in answers)
    render_learning_path(progress, missed_count)

    if progress.completed_at is not None:
        try:
            render_day_complete(store, day, facts, challenge, attempt, answers)
        except Exception as exc:
            render_classroom_connection_retry(exc, key="retry_day_complete")
        return

    try:
        if progress.fix_completed_at is None:
            if render_fix_misses(store, challenge, facts, answers):
                st.rerun()
            return

        if progress.focus_completed_at is None:
            if render_focus_practice(store, day, challenge, answers, progress=progress):
                st.rerun()
            return

        store.mark_focus_complete(st.session_state.student_id, challenge.challenge_id)
        st.rerun()
    except Exception as exc:
        render_classroom_connection_retry(exc, key="retry_learning_step")
        return


def render_daily(store: SupabaseFactStore | None) -> None:
    st.markdown("## Daily Challenge")
    st.caption("The same balanced 10 facts for everyone today. No right/wrong feedback until the end.")

    if not render_student_sign_in(store):
        return
    assert store is not None

    try:
        day, facts, challenge = ensure_today(store)
        attempt = store.get_or_create_attempt(st.session_state.student_id, challenge.challenge_id)
    except Exception as exc:
        st.error("Today's challenge could not be loaded. Your teacher can check the hidden database diagnostic if needed.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return

    if attempt.completed_at is not None:
        render_completed_daily(store, day, facts, challenge, attempt)
        return

    st.markdown(f"### {day.strftime('%A, %B %d').replace(' 0', ' ')}")
    render_routine_strip("daily")
    st.caption("Finish the three learning steps to earn today's Mystery reward.")
    st.markdown(
        "<div class='private-note'><strong>How today's timing works:</strong> Fact 1 counts toward accuracy, but it is untimed. "
        "The clock starts the instant you submit Fact 1 and runs quietly in the background. Facts 2–10 then appear one at a time. Accuracy always ranks before speed.</div>",
        unsafe_allow_html=True,
    )

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
            raw_response_seconds = component_result.get("response_seconds")
            timed_seconds = float(component_result.get("timed_seconds"))
            if not isinstance(raw_answers, list) or len(raw_answers) != 10:
                raise ValueError("Daily component returned an incomplete answer set.")
            values = [int(value) for value in raw_answers]
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
                completed_at=utc_now(),
            )
            st.rerun()
        except Exception as exc:
            st.error("Your finished Daily could not be saved. Leave this page open and try once more; your completed answers are still held in this browser.")
            if str(st.query_params.get("dbcheck", "0")) == "1":
                st.exception(exc)

    st.caption("A refresh on this device resumes the same Daily run. If a real technology problem occurs, your teacher can reset today's attempt from Student Tools.")


# ---------------------------------------------------------------------------
# Practice
# ---------------------------------------------------------------------------
def reset_practice_question() -> None:
    st.session_state.practice_fact = None
    st.session_state.practice_result = None
    st.session_state.practice_retry_correct = False
    st.session_state.practice_retry_count = 0
    st.session_state.practice_question_serial = int(st.session_state.get("practice_question_serial", 0)) + 1
    st.session_state.practice_started_at = None


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
    if signed_in:
        try:
            summary = store.practice_summary(st.session_state.student_id)
            if summary["attempts"]:
                st.caption(f"👤 {st.session_state.student_nickname} · {summary['correct']}/{summary['attempts']} correct in saved Practice rounds")
        except Exception:
            pass
    elif not student_signed_in():
        st.info("You can Practice as a guest. Sign in from Daily Challenge to unlock 🎯 My Focus Facts and save your Practice rounds.")

    options = (["🎯 My Focus Facts"] if signed_in else []) + fact_family_options()
    focus = st.selectbox("What do you want to practice?", options, key="practice_focus")
    if st.session_state.practice_focus_last != focus:
        st.session_state.practice_focus_last = focus
        reset_practice_question()

    if st.session_state.practice_fact is None:
        recent = st.session_state.practice_recent[-4:]
        if focus == "🎯 My Focus Facts" and signed_in:
            mastery = store.get_mastery(st.session_state.student_id)
            override = store.get_effective_focus_override(st.session_state.student_id)
            plan = build_focus_plan(
                mastery,
                student_id=st.session_state.student_id,
                date_key=f"manual-{current_daily_date().isoformat()}",
                override_family=override,
            )
            candidates = [fact for fact in plan if fact.key not in set(recent)] or plan
            fact = random.choice(candidates)
        else:
            fact = practice_fact(focus, random.Random(), avoid=recent)
        st.session_state.practice_fact = fact.as_dict()
        st.session_state.practice_started_at = datetime.now(timezone.utc).timestamp()
    fact = Fact.from_dict(st.session_state.practice_fact)

    if focus == "🎯 My Focus Facts":
        st.caption("These facts come from your growing mastery profile. The profile learns slowly from your normal Daily + assigned Focus Practice — never from a giant pretest.")

    st.markdown(f'<div class="fact-big">{fact.a} × {fact.b}</div>', unsafe_allow_html=True)

    if st.session_state.practice_result is None:
        pad_result = render_number_pad(
            key=f"practice_first_pad_{st.session_state.practice_question_serial}_{fact.a}_{fact.b}"
        )
        if pad_result is not None:
            value, response_seconds = pad_result
            correct = value == fact.product
            st.session_state.practice_result = {
                "answer": value,
                "correct": correct,
                "fact": fact.as_dict(),
            }
            st.session_state.practice_recent.append(fact.key)
            st.session_state.practice_recent = st.session_state.practice_recent[-8:]
            if store is not None and student_signed_in():
                try:
                    store.record_practice(
                        st.session_state.student_id,
                        focus,
                        fact,
                        value,
                        response_seconds=response_seconds,
                        activity_type="free_practice",
                        count_for_mastery=False,
                    )
                except Exception:
                    pass
            st.rerun()
        return

    result = st.session_state.practice_result
    if result["correct"]:
        st.success(f"✅ Yes! {fact.a} × {fact.b} = {fact.product}")
    else:
        st.error(f"Not yet — {fact.a} × {fact.b} = {fact.product}. You answered {result['answer']}.")

    st.markdown("### See the multiplication")
    render_array(fact)
    st.markdown(f"<div class='soft-card'><strong>💡 A way to think about it:</strong><br>{html.escape(strategy_tip(fact))}</div>", unsafe_allow_html=True)

    if not result["correct"] and not st.session_state.practice_retry_correct:
        st.markdown(f"### Now try it again: {fact.label} = ?")
        pad_result = render_number_pad(
            key=f"practice_retry_pad_{st.session_state.practice_question_serial}_{st.session_state.practice_retry_count}"
        )
        if pad_result is not None:
            retry_value, _ = pad_result
            if store is not None and student_signed_in():
                try:
                    store.record_practice(
                        st.session_state.student_id, focus, fact, retry_value,
                        activity_type="free_practice", is_retry=True, count_for_mastery=False,
                    )
                except Exception:
                    pass
            if retry_value == fact.product:
                st.session_state.practice_retry_correct = True
                st.rerun()
            else:
                st.session_state.practice_retry_count = int(st.session_state.get("practice_retry_count", 0)) + 1
                st.session_state.practice_retry_message = True
                st.rerun()
        if st.session_state.pop("practice_retry_message", False):
            st.error("Not yet — look at the array and strategy, then try that same fact again.")
        return

    if not result["correct"] and st.session_state.practice_retry_correct:
        st.success(f"✅ Got it — {fact.a} × {fact.b} = {fact.product}.")

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


def render_teacher_today(store: SupabaseFactStore) -> None:
    st.markdown("### 📊 Today")
    st.caption("Done means Daily 10 + Fix Your Misses + Focus Practice are complete. The Mystery guess is optional.")
    classes = store.list_classes()
    if not classes:
        st.info("Create your first class in Classes & Rosters.")
        return
    class_by_name = {item.class_name: item for item in classes}
    selected_name = st.selectbox("Class", list(class_by_name), key="teacher_today_class")
    selected = class_by_name[selected_name]
    day, facts, challenge = ensure_today(store)
    status = store.daily_status(selected.class_id, challenge.challenge_id)
    completed_rows = store.completed_attempts_for_class(selected.class_id, challenge.challenge_id)
    progress_map = store.class_learning_progress(selected.class_id, challenge.challenge_id)
    learning_stats = store.class_learning_stats(selected.class_id, day)

    total = len(status)
    full_complete = sum(
        bool(progress_map.get(row["student_id"]) and progress_map[row["student_id"]].completed_at)
        for row in status
    )
    not_started = sum(row["status"] == "Not started" for row in status)
    working = max(0, total - full_complete - not_started)
    daily_complete = sum(row["status"] == "Complete" for row in status)
    average_accuracy = (
        sum(int(row["correct_count"]) for row in completed_rows) / len(completed_rows)
        if completed_rows else 0
    )
    median_time = (
        float(pd.Series([row["timed_seconds"] for row in completed_rows]).median())
        if completed_rows else 0
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟢 Done", f"{full_complete}/{total}")
    c2.metric("🟡 Working", working)
    c3.metric("⚪ Not started", not_started)
    c4.metric("Daily 10 finished", f"{daily_complete}/{total}")

    teacher_students = {student.student_id: student for student in store.list_students(selected.class_id)}
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
            "Stars": int(stats.get("stars", 0)),
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

    with st.expander("Student-visible Top 10 preview", expanded=False):
        st.caption("This is exactly the information students are allowed to see: rank + nickname only.")
        board = store.leaderboard(selected.class_id, challenge.challenge_id, limit=10)
        if board:
            board_frame = pd.DataFrame([{"Rank": row["rank"], "Nickname": row["nickname"]} for row in board])
            st.dataframe(board_frame, hide_index=True, use_container_width=True)
        else:
            st.caption("No completed Daily attempts yet today.")

    with st.expander("Preview today's balanced 10", expanded=False):
        mix = daily_mix_summary(facts)
        st.caption(
            f"Core mix: {mix['easy']} easier retrieval · {mix['medium']} medium · {mix['hard']} harder"
            + (f" · {mix['extension']} 11/12 extension" if mix["extension"] else " · no 11/12 fact today")
        )
        for index, fact in enumerate(facts, start=1):
            st.write(f"{index}. **{fact.label} = {fact.product}** · {fact.tier}")

def _override_label(value: int | None) -> str:
    return "Automatic" if value is None else f"{value}s"


def _override_value(label: str) -> int | None:
    return None if label == "Automatic" else int(label.rstrip("s"))


def render_teacher_mastery_focus(store: SupabaseFactStore) -> None:
    st.markdown("### 🎯 Mastery & Focus")
    st.caption("See what students are learning now. New students begin as Learning — there is no placement test.")
    classes = store.list_classes()
    if not classes:
        st.info("Create a class first.")
        return

    class_by_name = {item.class_name: item for item in classes}
    class_name = st.selectbox("Class", list(class_by_name), key="teacher_mastery_class")
    selected = class_by_name[class_name]

    rows = store.class_mastery_summary(selected.class_id)
    if not rows:
        st.info("No students are in this class yet.")
        return
    frame = pd.DataFrame(rows)
    frame["Observed"] = frame["students"] - frame["Unknown"]
    frame["Need score"] = frame["Focus"] * 2 + frame["Building"]

    observed_needs = frame[(frame["Observed"] > 0) & ((frame["Focus"] > 0) | (frame["Building"] > 0))].copy()
    st.markdown("#### What this class needs most")
    if not observed_needs.empty:
        top = observed_needs.sort_values(["Need score", "Focus", "Building"], ascending=False).head(8)
        for _, row in top.iterrows():
            st.write(f"**{row['fact']}** · 🔴 {int(row['Focus'])} Focus · 🟡 {int(row['Building'])} Building · 🟢 {int(row['Fluent'])} Fluent")
    else:
        st.info("The app is still gathering evidence. That's intentional — it learns gradually instead of giving students a placement test.")

    st.markdown("#### Full class fact map")
    heat = frame[["fact", "Fluent", "Building", "Focus", "Unknown"]].copy()
    heat.columns = ["Fact", "🟢 Fluent", "🟡 Building", "🔴 Focus", "⚪ Learning"]
    st.dataframe(heat, hide_index=True, use_container_width=True)

    students = store.list_students(selected.class_id)
    if students:
        with st.expander("View one student's private fact map", expanded=False):
            student_by_name = {
                f"{student.nickname} · PIN {student.pin_code or 'reset once'}": student
                for student in students
            }
            student_label = st.selectbox("Student", list(student_by_name), key="mastery_student_select")
            student = student_by_name[student_label]
            mastery = complete_mastery_map(store.get_mastery(student.student_id))
            individual = []
            for key in sorted(mastery):
                row = mastery[key]
                icon, label = status_for_display(row.status)
                individual.append({
                    "Fact": f"{row.a} × {row.b}",
                    "Status": f"{icon} {label}",
                    "Evidence": row.evidence_count,
                    "First-try correct": "—" if not row.evidence_count else f"{row.correct_count}/{row.evidence_count}",
                })
            st.dataframe(pd.DataFrame(individual), hide_index=True, use_container_width=True)

    with st.expander("Teacher Focus overrides", expanded=False):
        st.caption("Leave these on Automatic unless you intentionally want to steer Focus Practice. Student override > class override > everyone > Automatic.")
        override_options = ["Automatic"] + [f"{value}s" for value in range(2, 11)]
        current_global = store.get_global_focus_override()
        global_choice = st.selectbox(
            "Everyone",
            override_options,
            index=override_options.index(_override_label(current_global)),
            key="global_focus_override_ui",
        )
        if st.button("Save everyone focus", use_container_width=True):
            store.set_global_focus_override(_override_value(global_choice))
            st.success("Everyone Focus setting saved.")
            st.rerun()

        current_class = store.get_class_focus_override(selected.class_id)
        class_choice = st.selectbox(
            f"{selected.class_name}",
            override_options,
            index=override_options.index(_override_label(current_class)),
            key=f"class_focus_override_{selected.class_id}",
        )
        if st.button("Save class focus", use_container_width=True):
            store.set_class_focus_override(selected.class_id, _override_value(class_choice))
            st.success("Class Focus setting saved.")
            st.rerun()

def render_teacher_classes(store: SupabaseFactStore) -> None:
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

    classes = store.list_classes(include_inactive=True)
    if not classes:
        return
    class_by_name = {item.class_name: item for item in classes}
    selected_name = st.selectbox("Class to manage", list(class_by_name), key="teacher_manage_class")
    selected = class_by_name[selected_name]
    st.caption(f"Class code: {selected.class_code} · {'Active' if selected.active else 'Inactive'}")

    roster = store.list_students(selected.class_id, include_inactive=True)

    with st.expander("➕ Add students", expanded=not bool(roster)):
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
                    st.success(f"Created {len(created)} student account{'s' if len(created) != 1 else ''}.")
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

    roster = store.list_students(selected.class_id, include_inactive=True)
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

def render_teacher_student_tools(store: SupabaseFactStore) -> None:
    st.markdown("### 🛠️ Student Support")
    st.caption("Use this area for one-student fixes: PINs, nickname changes, Daily resets, Focus overrides, moves, and account status.")
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
        f"{s.nickname} · PIN {s.pin_code or 'reset once'}{' (inactive)' if not s.active else ''}": s
        for s in students
    }
    label = st.selectbox("Student", list(student_by_label), key="teacher_tools_student")
    student = student_by_label[label]

    st.info(f"**{student.nickname}** · PIN **{student.pin_code or 'Reset once'}** · {class_record.class_name} · {'Active' if student.active else 'Inactive'}")

    with st.expander("🔑 Nickname & PIN", expanded=True):
        with st.form("rename_student_form"):
            new_name = st.text_input("Nickname", value=student.nickname, max_chars=28)
            rename = st.form_submit_button("Save nickname", use_container_width=True)
        if rename:
            try:
                store.rename_student(student.student_id, new_name)
                st.success("Nickname updated.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

        if student.pin_code:
            st.markdown(f"**Current classroom PIN: {student.pin_code}**")
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

    with st.expander("🧰 Today's Daily troubleshooting", expanded=False):
        try:
            _, _, challenge = ensure_today(store)
            attempt = store.get_attempt_for_student(student.student_id, challenge.challenge_id)
        except Exception:
            attempt = None
            challenge = None
        if attempt is None:
            st.caption("No attempt started today.")
        else:
            state = "Complete" if attempt.completed_at else "Timer running" if attempt.timed_started_at else "Opened"
            st.write(f"Current state: **{state}**")
            st.warning("Reset only for a technology problem or accidental start. It gives the student a fresh Daily attempt.")
            if st.button("Reset today's Daily attempt", use_container_width=True, key=f"reset_daily_{student.student_id}"):
                store.reset_daily_attempt(student.student_id, challenge.challenge_id)
                st.success("Today's attempt was reset.")
                st.rerun()

    with st.expander("🎯 Personal Focus override", expanded=False):
        st.caption("Automatic follows this student's evolving mastery. A student setting overrides class/everyone settings.")
        override_options = ["Automatic"] + [f"{value}s" for value in range(2, 11)]
        current_override = store.get_student_focus_override(student.student_id)
        personal_choice = st.selectbox(
            "Student Focus", override_options, index=override_options.index(_override_label(current_override)),
            key=f"student_focus_override_{student.student_id}",
        )
        if st.button("Save student focus", use_container_width=True, key=f"save_student_focus_{student.student_id}"):
            store.set_student_focus_override(student.student_id, _override_value(personal_choice))
            st.success("Student Focus setting saved.")
            st.rerun()

    with st.expander("↔️ Move or change account status", expanded=False):
        if len(classes) >= 2:
            destination_options = [item for item in classes if item.class_id != student.class_id]
            destination_by_name = {item.class_name: item for item in destination_options}
            destination_name = st.selectbox("Move to another class", list(destination_by_name), key=f"move_student_destination_{student.student_id}")
            st.caption("Moving keeps the student's PIN, mastery, Stars, streak, saved work, and Mystery history.")
            if st.button("Move student", use_container_width=True, key=f"move_student_{student.student_id}"):
                try:
                    destination = destination_by_name[destination_name]
                    store.move_student(student.student_id, destination.class_id)
                    st.session_state["teacher_roster_flash"] = ("success", f"Moved {student.nickname} to {destination.class_name}.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        target_active = not student.active
        if st.button(("Reactivate student" if target_active else "Deactivate student"), use_container_width=True, key=f"student_active_{student.student_id}"):
            store.set_student_active(student.student_id, target_active)
            st.rerun()

    with st.expander("📦 Bulk move shortcut", expanded=False):
        st.caption("The same bulk move tool also lives in Classes & Rosters → Roster Management.")
        if len(classes) >= 2:
            source_by_name = {item.class_name: item for item in classes}
            source_name = st.selectbox("From class", list(source_by_name), key="bulk_move_source_class")
            source = source_by_name[source_name]
            source_students = store.list_students(source.class_id, include_inactive=True)
            destination_options = [item for item in classes if item.class_id != source.class_id]
            destination_by_name = {item.class_name: item for item in destination_options}
            destination_name = st.selectbox("To class", list(destination_by_name), key="bulk_move_destination_class")
            selected_labels = st.multiselect(
                "Students to move", [f"{s.nickname} · PIN {s.pin_code or 'reset once'}" for s in source_students], key="bulk_move_students",
            )
            source_by_label = {f"{s.nickname} · PIN {s.pin_code or 'reset once'}": s for s in source_students}
            if st.button("Move selected students", use_container_width=True, disabled=not selected_labels, key="support_bulk_move"):
                destination = destination_by_name[destination_name]
                moved = 0
                errors = []
                for selected_label in selected_labels:
                    target = source_by_label[selected_label]
                    try:
                        store.move_student(target.student_id, destination.class_id)
                        moved += 1
                    except Exception as exc:
                        errors.append(f"{target.nickname}: {exc}")
                st.session_state["teacher_roster_flash"] = (
                    "warning" if errors else "success",
                    (f"Moved {moved} student(s). Could not move: " + " | ".join(errors[:8])) if errors
                    else f"Moved {moved} student(s) from {source.class_name} to {destination.class_name}.",
                )
                st.rerun()
        else:
            st.info("Create another class first.")

    with st.expander("⚠️ Permanently delete this student", expanded=False):
        st.warning("Permanent: removes the student's account and linked Daily, mastery, reward, and mystery history. Use Move instead if they belong in another class.")
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

def render_teacher_weekly_mystery(store: SupabaseFactStore) -> None:
    st.markdown("### 🕵️ Weekly Mystery")
    st.caption("One shared just-for-fun mystery. Monday–Thursday routines earn clues; students may guess once Thursday and once Friday.")
    day = current_daily_date()
    try:
        week_start, record, mystery = ensure_weekly_mystery(store, day)
        locked = store.weekly_mystery_locked(week_start)
        stats = store.weekly_mystery_teacher_stats(week_start)
    except Exception as exc:
        st.error("The Weekly Mystery tables are not ready. Run RUN_THIS_ONCE_IN_SUPABASE_v2_5.sql once.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return

    st.markdown(f"**Week of {week_start.strftime('%B %d, %Y').replace(' 0', ' ')}**")
    st.markdown(
        f"<div class='hero-card'><div class='section-label'>Teacher preview · {html.escape(mystery.category)}</div>"
        f"<div style='font-size:1.65rem;font-weight:950'>{html.escape(mystery.answer)}</div>"
        f"<div style='margin-top:.35rem'>{html.escape(mystery.reveal_note)}</div></div>",
        unsafe_allow_html=True,
    )
    for index, clue in enumerate(mystery.clues, start=1):
        st.write(f"**Clue #{index}:** {clue}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Students unlocked", int(stats.get("students_unlocked", 0)))
    c2.metric("Guesses used", int(stats.get("guesses", 0)))
    c3.metric("Solved", int(stats.get("correct", 0)))

    if locked:
        st.info("🔒 This week's mystery is locked because at least one student has already earned a clue.")
    else:
        st.success("You can still swap this mystery. It locks automatically when the first student earns a clue.")
        if st.button("🔄 Pick another mystery", use_container_width=True):
            try:
                store.replace_weekly_mystery(week_start, next_mystery_key(record.mystery_key))
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with st.expander(f"Mystery bank · {len(MYSTERIES)} curated mysteries", expanded=False):
        st.caption("Places · animals · foods · sports · science/nature · history/people · music/entertainment · games/toys/objects")
        st.write("The bank is stored inside the app, so clue delivery never depends on a live internet search.")


def render_teacher(store: SupabaseFactStore | None) -> None:
    if store is None:
        st.markdown("## Teacher Dashboard")
        render_db_setup_message()
        return
    if not teacher_login():
        return

    top_left, top_right = st.columns([5, 1.6])
    with top_left:
        st.markdown("## Teacher Dashboard")
        st.caption("Full class visibility stays here; students only see their class Top 10.")
    with top_right:
        if st.button("Lock", use_container_width=True):
            st.session_state.teacher_authed = False
            st.rerun()

    st.caption("Start with Today. Use Classes & Rosters for whole-class setup; use Student Support when one student needs help.")
    today_tab, class_tab, mastery_tab, mystery_tab, tools_tab = st.tabs([
        "📊 Today", "👥 Classes & Rosters", "🎯 Mastery & Focus", "🕵️ Weekly Mystery", "🛠️ Student Support"
    ])
    with today_tab:
        render_teacher_today(store)
    with class_tab:
        render_teacher_classes(store)
    with mastery_tab:
        render_teacher_mastery_focus(store)
    with mystery_tab:
        render_teacher_weekly_mystery(store)
    with tools_tab:
        render_teacher_student_tools(store)

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


store = get_store()
handle_persistent_student_login(store)
mode = render_header()
maybe_render_db_diagnostic(store)

if mode == "Daily Challenge":
    render_daily(store)
elif mode == "Practice":
    render_practice(store)
else:
    render_teacher(store)
