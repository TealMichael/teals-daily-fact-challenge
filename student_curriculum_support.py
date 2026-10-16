from __future__ import annotations

"""Small recovery controls shared by the student curriculum screens."""

import streamlit as st


def render_curriculum_retry(message: str, exc: Exception, *, key: str) -> None:
    st.error(message)
    st.caption("Your saved answers are safe. Try again without signing out. If this keeps happening, show your teacher.")
    if st.button("🔄 Try Again", type="primary", use_container_width=True, key=key):
        st.session_state["tdfc_force_fresh_store_once"] = True
        st.rerun()
    if str(st.query_params.get("dbcheck", "0")) == "1":
        st.exception(exc)
