from __future__ import annotations

"""Teacher-only calendar override for the Test Student sandbox.

Real student sessions always use the app's actual Indiana calendar date. The
simulated date exists only in the teacher's Streamlit session while Test Student
mode is active.
"""

from datetime import date, datetime

import streamlit as st

from fact_engine import current_daily_date

_SESSION_KEY = "teacher_test_student_date"


def effective_student_date() -> date:
    """Return the Test Student's simulated date, otherwise the real app date."""
    if st.session_state.get("teacher_test_student_mode"):
        selected = st.session_state.get(_SESSION_KEY)
        if isinstance(selected, datetime):
            return selected.date()
        if isinstance(selected, date):
            return selected
        if selected:
            try:
                return date.fromisoformat(str(selected))
            except (TypeError, ValueError):
                pass
    return current_daily_date()


def render_test_student_date_selector(*, active: bool = False) -> date:
    """Render the teacher-only date picker used to preview future/past routines."""
    if active:
        st.warning("🧪 **TEST STUDENT** · This practice account stays separate from class results and raffles.")
    else:
        st.caption("Try the student experience as many times as you want without affecting class results or raffles.")

    if _SESSION_KEY not in st.session_state:
        st.session_state[_SESSION_KEY] = current_daily_date()
    selected = st.date_input(
        "Test as date",
        key=_SESSION_KEY,
        help="Only Test Student uses this simulated date. Real students always use the actual calendar date.",
    )
    if selected != current_daily_date():
        st.info(
            f"Test Student will simulate {selected.strftime('%A, %B %d').replace(' 0', ' ')}. "
            "Real student sessions are not affected."
        )
    elif not active:
        st.caption("Choose a future or past date to preview that day's routine, including a saved Friday quiz.")
    return selected
