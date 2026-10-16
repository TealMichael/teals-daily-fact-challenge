from __future__ import annotations

"""Teacher-only setup and controls for the classroom AWTRIX display.

The clock never receives teacher-only results.  Supabase RPCs expose only the
preformatted rank + nickname Top 10 after validating a separate revocable clock
token.  This module keeps clock setup out of Student Daily and Learning Data.
"""

import streamlit as st

from fact_store import FactStoreError
from supabase_fact_store import SupabaseFactStore, normalize_supabase_url


def _public_supabase_key() -> str:
    """Return an optional public client key without ever falling back to the secret key."""
    try:
        for name in ("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY"):
            value = str(st.secrets.get(name) or "").strip()
            if value:
                return value
    except Exception:
        pass
    return ""


def queue_clock_top10_for_class(store: SupabaseFactStore, class_id: str) -> int:
    """Queue a manual display command for the block mapped to ``class_id``."""
    block = store.awtrix_block_for_class(class_id)
    if block is None:
        raise FactStoreError("That class is not mapped to Block 1, Block 2, or Block 3 in Clock Setup yet.")
    store.queue_awtrix_top10(block)
    return block


def _class_index(options: list[str], class_by_name: dict, class_id: str | None, fallback: int) -> int:
    if class_id:
        for index, name in enumerate(options):
            if class_by_name[name].class_id == str(class_id):
                return index
    return min(max(0, fallback), max(0, len(options) - 1))


def render_teacher_clock(store: SupabaseFactStore) -> None:
    st.markdown("### 🖥️ Classroom Clock")
    st.caption("Choose which classes belong to Blocks 1–3 and send the Top 10 to your classroom clock.")

    try:
        config = store.get_awtrix_clock_config()
    except Exception as exc:
        st.warning("Clock setup is not complete yet. Open One-time clock setup below for the setup steps.")
        with st.expander("⚙️ One-time clock setup", expanded=False):
            st.caption("Run `RUN_THIS_ONCE_IN_SUPABASE_v2_12.sql` once, then return here and tap Refresh data.")
        if str(st.query_params.get("dbcheck", "0")) == "1":
            st.exception(exc)
        return

    if config is None:
        st.warning("Clock setup is not complete yet. Open One-time clock setup below for the setup steps.")
        with st.expander("⚙️ One-time clock setup", expanded=False):
            st.caption("Run `RUN_THIS_ONCE_IN_SUPABASE_v2_12.sql` once, then return here and tap Refresh data.")
        return

    classes = store.list_classes()
    if len(classes) < 3:
        st.info("You need three classes before Blocks 1, 2, and 3 can all be mapped.")
        return

    class_by_name = {item.class_name: item for item in classes}
    class_names = list(class_by_name)

    if st.session_state.pop("awtrix_mapping_saved", False):
        st.success("Clock class mapping saved.")

    st.markdown("#### Class → block mapping")
    with st.form("awtrix_clock_mapping"):
        block1_name = st.selectbox(
            "Block 1 class", class_names,
            index=_class_index(class_names, class_by_name, config.get("block1_class_id"), 0),
        )
        block2_name = st.selectbox(
            "Block 2 class", class_names,
            index=_class_index(class_names, class_by_name, config.get("block2_class_id"), 1),
        )
        block3_name = st.selectbox(
            "Block 3 class", class_names,
            index=_class_index(class_names, class_by_name, config.get("block3_class_id"), 2),
        )
        save_mapping = st.form_submit_button("Save clock class mapping", use_container_width=True, type="primary")

    if save_mapping:
        ids = [class_by_name[name].class_id for name in (block1_name, block2_name, block3_name)]
        if len(set(ids)) != 3:
            st.error("Choose a different class for each block.")
        else:
            store.save_awtrix_clock_mapping(*ids)
            st.session_state["awtrix_mapping_saved"] = True
            st.rerun()

    st.markdown("#### Clock connection")
    if config.get("has_token"):
        st.success("Clock connection is ready.")
        st.caption("Use the button below only if you need a new connection code for the clock.")
    else:
        st.info("Create a connection code before the clock can receive the Top 10.")

    token_button_label = "Create new connection code" if config.get("has_token") else "Create connection code"
    if st.button(token_button_label, use_container_width=True, key="awtrix_rotate_token"):
        st.session_state["awtrix_new_token"] = store.rotate_awtrix_clock_token()
        st.rerun()

    new_token = st.session_state.get("awtrix_new_token")
    if new_token:
        st.warning("Copy this connection code now. It will not be shown again.")
        st.code(str(new_token), language=None)
        if st.button("I've copied the connection code", key="awtrix_token_copied"):
            st.session_state.pop("awtrix_new_token", None)
            st.rerun()

    with st.expander("⚙️ One-time clock setup", expanded=False):
        st.caption("You only need these details when installing or replacing the AWTRIX Top 10 script.")
        try:
            supabase_url = normalize_supabase_url(str(st.secrets.get("SUPABASE_URL") or ""))
        except Exception:
            supabase_url = ""
        rest_url = f"{supabase_url}/rest/v1" if supabase_url else ""
        public_key = _public_supabase_key()

        if rest_url:
            st.caption("Service URL")
            st.code(rest_url, language=None)
        if public_key:
            st.caption("Public key")
            st.code(public_key, language=None)
        else:
            st.info("The public key is not saved here yet. Copy the Publishable key from your Supabase API settings when you set up the clock script.")

        st.caption("Install `AWTRIX_FactTop10.berry` as the separate Top 10 script. Keep the existing Class Schedule script unchanged.")
        st.caption("For extra protection on a shared network, turn on AWTRIX web authentication in System settings.")

    st.markdown("#### Test the clock")
    test_name = st.selectbox("Class to send", class_names, key="awtrix_test_class")
    if st.button("📟 Send Top 10 to Clock Now", use_container_width=True, type="primary", key="awtrix_test_send"):
        try:
            block = queue_clock_top10_for_class(store, class_by_name[test_name].class_id)
            st.success(f"Block {block} Top 10 sent. The clock should show it within about 15 seconds.")
        except FactStoreError as exc:
            st.warning(str(exc))
