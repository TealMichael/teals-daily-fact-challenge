from __future__ import annotations

from datetime import datetime, timezone
import html
import hmac
import random
from pathlib import Path

import pandas as pd
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
from supabase_fact_store import SupabaseFactStore


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
        grid-template-columns:2.2rem 1fr auto;
        align-items:center;
        gap:0.5rem;
        border-bottom:1px solid #e5e7eb;
        padding:0.5rem 0.1rem;
        color:#111827 !important;
    }
    .leader-rank { font-size:1.03rem; font-weight:950; text-align:center; }
    .leader-name { font-weight:850; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .leader-score { text-align:right; font-weight:850; font-variant-numeric:tabular-nums; }

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
        .leader-row { grid-template-columns:2rem 1fr auto; }
        .array-dot { width:14px; height:14px; }
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
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


def switch_mode(mode: str) -> None:
    st.session_state.app_mode = mode


def sign_out() -> None:
    for key in ("student_id", "student_nickname", "student_class_id", "student_class_name"):
        st.session_state[key] = None
    st.session_state.practice_result = None


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
    larger = max(a, b)
    smaller = min(a, b)
    return f"Build from a fact you know: {smaller} groups of {larger} make {fact.product}."


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
    st.caption("Use the nickname and 4-digit PIN your teacher gave you.")
    class_by_name = {item.class_name: item for item in classes}
    with st.form("student_signin", clear_on_submit=False):
        class_name = st.selectbox("Class", list(class_by_name))
        nickname = st.text_input("Nickname", max_chars=28)
        pin = st.text_input("4-digit PIN", type="password", max_chars=4)
        submitted = st.form_submit_button("Sign in", use_container_width=True, type="primary")
    if submitted:
        selected = class_by_name[class_name]
        try:
            student = store.authenticate_student(selected.class_id, nickname, pin)
        except Exception:
            student = None
        if student is None:
            st.error("That nickname/PIN combination did not match this class.")
            return False
        st.session_state.student_id = student.student_id
        st.session_state.student_nickname = student.nickname
        st.session_state.student_class_id = selected.class_id
        st.session_state.student_class_name = selected.class_name
        st.rerun()
    st.markdown("<div class='private-note'>Nicknames are public inside the class leaderboard. PINs stay private and are never shown to classmates.</div>", unsafe_allow_html=True)
    return False


# ---------------------------------------------------------------------------
# Daily Challenge
# ---------------------------------------------------------------------------
def ensure_today(store: SupabaseFactStore):
    day = current_daily_date()
    facts = daily_facts_for_date(day)
    validate_daily_facts(facts)
    challenge = store.get_or_create_challenge(day, CHALLENGE_VERSION, facts)
    return day, list(challenge.facts), challenge


def render_leaderboard(store: SupabaseFactStore, challenge, *, highlight_student_id: str | None = None) -> None:
    class_id = st.session_state.student_class_id
    roster = store.list_students(class_id)
    rows = store.leaderboard(class_id, challenge.challenge_id, limit=10)
    finished = len(store.completed_attempts_for_class(class_id, challenge.challenge_id))

    st.markdown("### 🏆 Today's Top 10")
    st.caption(f"Accuracy first · time breaks ties · {finished} of {len(roster)} finished")
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
        score = f'{int(row["correct_count"])}/10 · {format_seconds(row["timed_seconds"])}'
        html_rows.append(
            f'<div class="leader-row"><div class="leader-rank">{marker}</div>'
            f'<div class="leader-name">{name}{suffix}</div>'
            f'<div class="leader-score">{score}</div></div>'
        )
    st.markdown('<div class="soft-card">' + "".join(html_rows) + "</div>", unsafe_allow_html=True)
    if highlight_student_id and not any(row["student_id"] == highlight_student_id for row in rows):
        st.caption("Only the Top 10 is shown. Your exact class rank stays private.")


def render_daily_review(facts: list[Fact], answers) -> None:
    with st.expander("Review your 10", expanded=False):
        missed = []
        for fact, answer in zip(facts, answers):
            cls = "answer-correct" if answer.correct else "answer-miss"
            symbol = "✅" if answer.correct else "❌"
            correct_text = "" if answer.correct else f" · correct answer {answer.correct_answer}"
            st.markdown(
                f'<div class="soft-card {cls}"><strong>{symbol} {answer.question_number}. {fact.label}</strong><br>'
                f'You answered <strong>{answer.student_answer}</strong>{correct_text}</div>',
                unsafe_allow_html=True,
            )
            if not answer.correct:
                missed.append(fact)
        if missed:
            st.markdown("#### Learn from the misses")
            st.caption("Arrays show the groups behind each multiplication fact.")
            for fact in missed:
                st.markdown(f"**{fact.label} = {fact.product}**")
                render_array(fact)
                st.caption(f"💡 {strategy_tip(fact)}")
                st.divider()
        else:
            st.success("Perfect accuracy — all 10 facts were correct.")


def render_completed_daily(store: SupabaseFactStore, day, facts: list[Fact], challenge, attempt) -> None:
    answers = store.get_answers(attempt.attempt_id)
    leaderboard = store.leaderboard(st.session_state.student_class_id, challenge.challenge_id, limit=10)
    own_top = next((row for row in leaderboard if row["student_id"] == st.session_state.student_id), None)
    st.markdown(f"## Daily complete · {day.strftime('%B %d').replace(' 0', ' ')}")
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="result-grid">
                <div class="result-box"><div class="result-label">Accuracy</div><div class="result-value">{attempt.correct_count}/10</div></div>
                <div class="result-box"><div class="result-label">Timed Sprint</div><div class="result-value">{format_seconds(attempt.timed_seconds)}</div></div>
                <div class="result-box"><div class="result-label">Top 10</div><div class="result-value">{('#' + str(own_top['rank'])) if own_top else '—'}</div></div>
                <div class="result-box"><div class="result-label">Facts to Review</div><div class="result-value">{10 - int(attempt.correct_count or 0)}</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if own_top:
        st.success(f"You're #{own_top['rank']} in your class Top 10 right now!")
    elif len(leaderboard) >= 10:
        st.info("Only the class Top 10 is displayed. Your exact rank is private — Practice is ready whenever you want another round.")
    else:
        st.info("The Top 10 will keep filling in as classmates finish.")

    render_leaderboard(store, challenge, highlight_student_id=st.session_state.student_id)
    render_daily_review(facts, answers)
    if st.button("Practice my facts", use_container_width=True, type="primary", on_click=switch_mode, args=("Practice",)):
        pass
    st.caption("🔒 Today's Daily is complete. A new 10-fact challenge appears tomorrow.")


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
    st.markdown(
        "<div class='private-note'><strong>How today's timing works:</strong> Fact 1 counts toward accuracy, but it is untimed. "
        "The clock starts the instant you submit Fact 1. Facts 2–10 then appear one at a time. Accuracy always ranks before speed.</div>",
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
            timed_seconds = float(component_result.get("timed_seconds"))
            if not isinstance(raw_answers, list) or len(raw_answers) != 10:
                raise ValueError("Daily component returned an incomplete answer set.")
            values = [int(value) for value in raw_answers]
            if any(value < 0 or value > 200 for value in values):
                raise ValueError("Daily component returned an invalid answer.")
            store.complete_full_attempt(
                attempt.attempt_id,
                list(zip(facts, values)),
                timed_seconds,
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


def next_practice_question() -> None:
    st.session_state.practice_fact = None
    st.session_state.practice_result = None


def render_practice(store: SupabaseFactStore | None) -> None:
    st.markdown("## Practice")
    st.caption("Choose your area of need · unlimited facts · instant teaching after every answer")

    if student_signed_in() and store is not None:
        try:
            summary = store.practice_summary(st.session_state.student_id)
            if summary["attempts"]:
                st.caption(f"👤 {st.session_state.student_nickname} · {summary['correct']}/{summary['attempts']} correct in saved Practice rounds")
        except Exception:
            pass
    elif not student_signed_in():
        st.info("You can Practice as a guest. Sign in from Daily Challenge if you want your Practice rounds saved.")

    options = fact_family_options()
    focus = st.selectbox("What do you want to practice?", options, key="practice_focus")
    if st.session_state.practice_focus_last != focus:
        st.session_state.practice_focus_last = focus
        reset_practice_question()

    if st.session_state.practice_fact is None:
        recent = st.session_state.practice_recent[-4:]
        fact = practice_fact(focus, random.Random(), avoid=recent)
        st.session_state.practice_fact = fact.as_dict()
    fact = Fact.from_dict(st.session_state.practice_fact)

    st.markdown(f'<div class="fact-big">{fact.a} × {fact.b}</div>', unsafe_allow_html=True)

    if st.session_state.practice_result is None:
        with st.form("practice_answer_form", clear_on_submit=True):
            raw = st.text_input("Answer", placeholder="Type your answer", max_chars=3)
            submit = st.form_submit_button("Check my answer", use_container_width=True, type="primary")
        if submit:
            try:
                value = parse_answer(raw)
            except ValueError as exc:
                st.error(str(exc))
                return
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
    classes = store.list_classes()
    if not classes:
        st.info("Create your first class in Classes & Students.")
        return
    class_by_name = {item.class_name: item for item in classes}
    selected_name = st.selectbox("Class", list(class_by_name), key="teacher_today_class")
    selected = class_by_name[selected_name]
    day, facts, challenge = ensure_today(store)
    status = store.daily_status(selected.class_id, challenge.challenge_id)
    completed_rows = store.completed_attempts_for_class(selected.class_id, challenge.challenge_id)

    total = len(status)
    complete = sum(row["status"] == "Complete" for row in status)
    in_progress = sum(row["status"] == "In progress" for row in status)
    average_accuracy = (
        sum(int(row["correct_count"]) for row in completed_rows) / len(completed_rows)
        if completed_rows else 0
    )
    median_time = (
        float(pd.Series([row["timed_seconds"] for row in completed_rows]).median())
        if completed_rows else 0
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Students", total)
    c2.metric("Complete", f"{complete}/{total}")
    c3.metric("Avg accuracy", f"{average_accuracy:.1f}/10" if completed_rows else "—")
    c4.metric("Median time", format_seconds(median_time) if completed_rows else "—")
    if in_progress:
        st.caption(f"⏱️ {in_progress} student{'s are' if in_progress != 1 else ' is'} currently in the timed sprint.")

    frame = pd.DataFrame(status)
    if not frame.empty:
        frame = frame[["nickname", "status", "correct_count", "timed_seconds"]].copy()
        frame.columns = ["Nickname", "Status", "Correct", "Time"]
        frame["Correct"] = frame["Correct"].apply(lambda value: "" if pd.isna(value) else f"{int(value)}/10")
        frame["Time"] = frame["Time"].apply(lambda value: "" if pd.isna(value) else format_seconds(float(value)))
        st.dataframe(frame, hide_index=True, use_container_width=True)

    st.markdown("#### Student-visible Top 10")
    board = store.leaderboard(selected.class_id, challenge.challenge_id, limit=10)
    if board:
        board_frame = pd.DataFrame([
            {"Rank": row["rank"], "Nickname": row["nickname"], "Correct": f"{row['correct_count']}/10", "Time": format_seconds(row["timed_seconds"])}
            for row in board
        ])
        st.dataframe(board_frame, hide_index=True, use_container_width=True)
    else:
        st.caption("No completed attempts yet today.")

    with st.expander("Preview today's balanced 10", expanded=False):
        mix = daily_mix_summary(facts)
        st.caption(
            f"Core mix: {mix['easy']} easier retrieval · {mix['medium']} medium · {mix['hard']} harder"
            + (f" · {mix['extension']} 11/12 extension" if mix["extension"] else " · no 11/12 fact today")
        )
        for index, fact in enumerate(facts, start=1):
            st.write(f"{index}. **{fact.label} = {fact.product}** · {fact.tier}")


def render_teacher_classes(store: SupabaseFactStore) -> None:
    st.markdown("### Classes")
    with st.form("create_class_form", clear_on_submit=True):
        class_name = st.text_input("New class name", placeholder="Example: Period 1")
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
    selected_name = st.selectbox("Manage class", list(class_by_name), key="teacher_manage_class")
    selected = class_by_name[selected_name]
    st.caption(f"Class code: {selected.class_code} · {'Active' if selected.active else 'Inactive'}")

    st.markdown("### Add students in a batch")
    st.caption("Paste nicknames one per line. The app creates a private 4-digit PIN for each student.")
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
        st.markdown("#### Save these new PINs now")
        st.caption("PINs are stored securely as hashes. If one is lost later, reset it rather than retrieving the old one.")
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
    st.markdown(f"### Roster · {len(roster)} students")
    if roster:
        roster_frame = pd.DataFrame([
            {"Nickname": student.nickname, "Status": "Active" if student.active else "Inactive"}
            for student in roster
        ])
        st.dataframe(roster_frame, hide_index=True, use_container_width=True)
        st.download_button(
            "Download roster (no PINs)",
            roster_frame.to_csv(index=False).encode("utf-8"),
            file_name=f"{selected.class_name.replace(' ', '_')}_roster.csv",
            mime="text/csv",
            use_container_width=True,
        )


def render_teacher_student_tools(store: SupabaseFactStore) -> None:
    classes = store.list_classes(include_inactive=True)
    if not classes:
        st.info("Create a class first.")
        return
    class_by_name = {item.class_name: item for item in classes}
    class_name = st.selectbox("Class", list(class_by_name), key="teacher_tools_class")
    class_record = class_by_name[class_name]
    students = store.list_students(class_record.class_id, include_inactive=True)
    if not students:
        st.info("This class has no students yet.")
        return
    student_by_label = {f"{s.nickname}{' (inactive)' if not s.active else ''}": s for s in students}
    label = st.selectbox("Student", list(student_by_label), key="teacher_tools_student")
    student = student_by_label[label]

    st.markdown("#### Rename nickname")
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

    st.markdown("#### Reset PIN")
    st.caption("The old PIN cannot be viewed. Resetting creates a new 4-digit PIN.")
    if st.button("Generate new PIN", use_container_width=True):
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
        st.caption("Give it to the student privately, then clear it from the screen.")
        if st.button("Clear new PIN", use_container_width=True):
            st.session_state.pop("last_reset_pin", None)
            st.rerun()

    st.markdown("#### Account status")
    target_active = not student.active
    if st.button(("Reactivate student" if target_active else "Deactivate student"), use_container_width=True):
        store.set_student_active(student.student_id, target_active)
        st.rerun()

    st.markdown("#### Today's Daily attempt")
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
        st.caption(f"Current state: {state}")
        st.warning("Use reset only for a technology problem or accidental start. It gives the student a fresh Daily attempt.")
        if st.button("Reset today's Daily attempt", use_container_width=True):
            store.reset_daily_attempt(student.student_id, challenge.challenge_id)
            st.success("Today's attempt was reset.")
            st.rerun()


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

    today_tab, class_tab, tools_tab = st.tabs(["Today", "Classes & Students", "Student Tools"])
    with today_tab:
        render_teacher_today(store)
    with class_tab:
        render_teacher_classes(store)
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
mode = render_header()
maybe_render_db_diagnostic(store)

if mode == "Daily Challenge":
    render_daily(store)
elif mode == "Practice":
    render_practice(store)
else:
    render_teacher(store)
