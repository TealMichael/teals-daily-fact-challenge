from __future__ import annotations

import json
import importlib
import inspect

import streamlit as st

from auth import login_player, register_player, restore_from_cookie, revoke_cookie_session
# Prior warm-reload marker: getattr(_config, "APP_BUILD_VERSION", "") != "1.0.7-hotfix7.16"
# The app file is re-executed on Streamlit reruns, but config.py may still be
# cached from the prior deploy. Read the new build key before creating the
# cached store or binding other UI modules.
import config as _config
# Prior cumulative config guard: getattr(_config, "APP_BUILD_VERSION", "") != "1.0.7-hotfix7.17"
# Previous release guard: getattr(_config, "APP_BUILD_VERSION", "") != "1.0.7-hotfix7.19"
if getattr(_config, "APP_BUILD_VERSION", "") != "1.0.8-hotfix8.1":
    _config = importlib.reload(_config)
from config import (
    APP_BUILD_VERSION,
    APP_NAME,
    APP_VERSION,
    COOKIE_NAME,
    REMEMBER_COOKIE_MAX_AGE,
    REMEMBER_STORAGE_KEY,
)
from security import safe_secret_match
import ui as _ui
if getattr(_ui, "UI_THEME_SCHEMA_VERSION", 0) < 4:
    _ui = importlib.reload(_ui)
hero, inject_css, page_config = _ui.hero, _ui.inject_css, _ui.page_config

# A Streamlit Cloud worker may survive a multi-file deploy with old imported
# modules still resident. Reload the Sunday-critical dependency chain in order
# before binding UI helpers. This is separate from the resource-cache build key:
# the build key prevents stale *instances*; these guards prevent stale *classes
# and functions* from being reused by the warm Python process.
import weekly as _weekly_core
if getattr(_weekly_core, "WEEKLY_LOGIC_SCHEMA_VERSION", 0) < 3:
    _weekly_core = importlib.reload(_weekly_core)

import store as _store
# Legacy regression marker only: getattr(_store, "STORE_SCHEMA_VERSION", 0) < 4
if (
    getattr(_store, "STORE_SCHEMA_VERSION", 0) < 6
    or not hasattr(_store.SupabaseStore, "get_app_meta")
    or not hasattr(_store.SupabaseStore, "set_app_meta")
):
    _store = importlib.reload(_store)
SupabaseStore = _store.SupabaseStore

# Hotfix 7.8 legacy warm-reload markers retained for regression coverage:
# getattr(_nfl_sync, "NFL_SYNC_SCHEMA_VERSION", 0) < 3
# getattr(_automation_recovery, "AUTOMATION_RECOVERY_SCHEMA_VERSION", 0) < 4
# getattr(_gate4_ui, "GATE4_UI_SCHEMA_VERSION", 0) < 5

import nfl_sources as _nfl_sources
if getattr(_nfl_sources, "NFL_SOURCES_SCHEMA_VERSION", 0) < 2:
    _nfl_sources = importlib.reload(_nfl_sources)

import nfl_sync as _nfl_sync
_reloaded_nfl_sync = False
if getattr(_nfl_sync, "NFL_SYNC_SCHEMA_VERSION", 0) < 6:
    _nfl_sync = importlib.reload(_nfl_sync)
    _reloaded_nfl_sync = True

import automation_recovery as _automation_recovery
_reloaded_automation_recovery = False
if _reloaded_nfl_sync or getattr(_automation_recovery, "AUTOMATION_RECOVERY_SCHEMA_VERSION", 0) < 6:
    _automation_recovery = importlib.reload(_automation_recovery)
    _reloaded_automation_recovery = True

import gate4_ui as _gate4_ui
import weekly_ui as _weekly_ui
import gate5_ui as _gate5_ui

# Reload Gate 4 *before* Weekly UI, which imports Gate 4 functions by name.
# Otherwise a warmed worker can show the old live screen even after deploying
# both updated files, because Weekly UI held stale function references.
# Legacy regression marker only: getattr(_gate4_ui, "GATE4_UI_SCHEMA_VERSION", 0) < 4
# Prior cumulative guard: getattr(_gate4_ui, "GATE4_UI_SCHEMA_VERSION", 0) < 7
# Prior cumulative guard: getattr(_gate4_ui, "GATE4_UI_SCHEMA_VERSION", 0) < 8
# Prior cumulative guard: getattr(_gate4_ui, "GATE4_UI_SCHEMA_VERSION", 0) < 9
_reloaded_gate4_ui = False
# Previous guard: if _reloaded_automation_recovery or getattr(_gate4_ui, "GATE4_UI_SCHEMA_VERSION", 0) < 10:
if _reloaded_automation_recovery or getattr(_gate4_ui, "GATE4_UI_SCHEMA_VERSION", 0) < 11:
    _gate4_ui = importlib.reload(_gate4_ui)
    _reloaded_gate4_ui = True
render_gate4_demo = _gate4_ui.render_gate4_demo

# Legacy regression marker only: getattr(_weekly_ui, "WEEKLY_UI_SCHEMA_VERSION", 0) < 9
# Prior cumulative UI guard: getattr(_weekly_ui, "WEEKLY_UI_SCHEMA_VERSION", 0) < 10
# Prior cumulative UI guard: getattr(_weekly_ui, "WEEKLY_UI_SCHEMA_VERSION", 0) < 11
# Previous UI guard: getattr(_weekly_ui, "WEEKLY_UI_SCHEMA_VERSION", 0) < 12
# Previous release guard: getattr(_weekly_ui, "WEEKLY_UI_SCHEMA_VERSION", 0) < 13
_weekly_params = inspect.signature(_weekly_ui.render_player_game).parameters
if (
    _reloaded_automation_recovery
    or _reloaded_gate4_ui
    or getattr(_weekly_ui, "WEEKLY_UI_SCHEMA_VERSION", 0) < 14
    or not hasattr(_weekly_ui, "_render_player_card_button")
    or "on_sign_out" not in _weekly_params
    or "allow_demo_week" not in _weekly_params
):
    _weekly_ui = importlib.reload(_weekly_ui)
render_player_game = _weekly_ui.render_player_game

# Legacy regression marker: GATE5_UI_SCHEMA_VERSION", 0) < 4
# Prior Gate 5 warm-reload marker: getattr(_gate5_ui, "GATE5_UI_SCHEMA_VERSION", 0) < 7
# Prior Gate 5 warm-reload marker: getattr(_gate5_ui, "GATE5_UI_SCHEMA_VERSION", 0) < 8
if getattr(_gate5_ui, "GATE5_UI_SCHEMA_VERSION", 0) < 9:
    _gate5_ui = importlib.reload(_gate5_ui)
render_commissioner_dashboard = _gate5_ui.render_commissioner_dashboard

page_config()
inject_css()
hero()


# Browser-local remembered-login bridge.
# This intentionally mirrors the working Yahtzee architecture: a high-entropy
# revocable token is stored in first-party localStorage and synchronized to a
# first-party cookie. The PIN is never stored in the browser.
_remember_storage_component = st.components.v2.component(
    "pickem_remember_storage",
    html="<span aria-hidden='true'></span>",
    css=":host { display: none !important; height: 0 !important; }",
    js=r"""
    export default function({ data, setStateValue }) {
      const key = data?.storage_key || "tsp_remember_device_v1";
      const action = data?.action || "read";
      const token = data?.token || "";
      const nonce = data?.nonce || "";
      const cookieName = data?.cookie_name || "tsp_session_v1";
      const cookieMaxAge = Number(data?.cookie_max_age || 0);
      let stored = "";
      try {
        if (action === "set" && token) {
          window.localStorage.setItem(key, token);
        } else if (action === "delete") {
          window.localStorage.removeItem(key);
          document.cookie = `${cookieName}=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax; Secure`;
        }
        stored = window.localStorage.getItem(key) || "";
        if (stored) {
          document.cookie = `${cookieName}=${stored}; Path=/; Max-Age=${cookieMaxAge}; SameSite=Lax; Secure`;
        }
      } catch (err) {
        stored = "";
      }
      setStateValue("payload", JSON.stringify({
        token: stored,
        ready: true,
        ack: nonce
      }));
    }
    """,
)


def secret(name: str) -> str:
    try:
        return str(st.secrets[name])
    except Exception:
        return ""


@st.cache_resource(show_spinner=False)
def get_store(url: str, service_key: str, build_version: str) -> SupabaseStore:
    # Include the build version in the cache key so a deploy can never reuse
    # a SupabaseStore instance created from an older class definition.
    _ = build_version
    return SupabaseStore(url, service_key)


def supabase_server_key() -> str:
    # Match the current Yahtzee secret name while retaining compatibility with
    # the original Gate 1 name.
    return secret("SUPABASE_SECRET_KEY") or secret("SUPABASE_SERVICE_ROLE_KEY")


required = ["SUPABASE_URL", "PIN_PEPPER", "SESSION_PEPPER", "COMMISH_USERNAME", "COMMISH_PIN"]
missing = [name for name in required if not secret(name)]
if not supabase_server_key():
    missing.append("SUPABASE_SECRET_KEY")
if missing:
    st.error("App setup is incomplete. Add the required secrets before using Gate 1.")
    with st.expander("Setup details"):
        st.code("Missing: " + ", ".join(missing))
        st.write("Use `.streamlit/secrets.toml.example` as the template. Never commit the real secrets file.")
    st.stop()

store = get_store(secret("SUPABASE_URL"), supabase_server_key(), APP_BUILD_VERSION)


def _record_ui_incident(scope: str, exc: Exception) -> None:
    """Record a privacy-safe runtime incident once per browser session.

    Never persist raw exception text: provider/client exceptions can contain
    URLs or implementation details. Commissioner activity only needs the error
    type, app build, and UI scope to diagnose a launch issue.
    """
    fingerprint = f"ui_incident::{scope}::{type(exc).__name__}"
    if st.session_state.get(fingerprint):
        return
    st.session_state[fingerprint] = True
    try:
        week = store.get_real_week()
        run_id = store.start_data_run(
            "ui_error",
            week_id=str(week["id"]) if week else None,
            provider="streamlit",
            metadata={"scope": scope, "error_type": type(exc).__name__, "build": APP_BUILD_VERSION},
        )
        store.finish_data_run(
            run_id,
            success=False,
            message=f"{scope} UI error ({type(exc).__name__})",
            metadata={"scope": scope, "error_type": type(exc).__name__, "build": APP_BUILD_VERSION},
        )
    except Exception:
        pass


def _friendly_runtime_error(scope: str, exc: Exception) -> None:
    _record_ui_incident(scope, exc)
    st.error("Sunday Pick'em hit a temporary snag. Your saved lineup and scores are safe.")
    st.caption("Try again in a moment. If this keeps happening, Mike can see the incident in Commissioner activity without exposing technical details here.")
    if st.button("Try Again", type="primary", use_container_width=True, key=f"retry::{scope}"):
        st.rerun()


# -----------------------------
# Gate 1 session state
# -----------------------------
if "player" not in st.session_state:
    st.session_state.player = None
if "commish" not in st.session_state:
    st.session_state.commish = False
if "active_device_token" not in st.session_state:
    st.session_state.active_device_token = None
if "remember_restore_checked" not in st.session_state:
    st.session_state.remember_restore_checked = False
if "remember_storage_command" not in st.session_state:
    st.session_state.remember_storage_command = None
if "remember_storage_nonce" not in st.session_state:
    st.session_state.remember_storage_nonce = 0


def _browser_remember_cookie() -> str:
    """Read the first-party token from the initial browser request."""
    try:
        return str(st.context.cookies.get(COOKIE_NAME, "") or "").strip()
    except Exception:
        return ""


def _next_remember_storage_nonce() -> str:
    st.session_state.remember_storage_nonce = int(st.session_state.get("remember_storage_nonce", 0)) + 1
    return str(st.session_state.remember_storage_nonce)


def _queue_remember_storage_set(token: str) -> None:
    st.session_state.remember_storage_command = {
        "action": "set",
        "token": str(token),
        "nonce": _next_remember_storage_nonce(),
    }


def _queue_remember_storage_delete() -> None:
    st.session_state.remember_storage_command = {
        "action": "delete",
        "token": "",
        "nonce": _next_remember_storage_nonce(),
    }


def _queue_remember_cookie_set(token: str) -> None:
    # The first-party Components-v2 bridge writes BOTH localStorage and the
    # first-party cookie. Keep one browser command path so auth actions never
    # compete with a second hidden widget/script rerun.
    _queue_remember_storage_set(token)


def _queue_remember_cookie_delete() -> None:
    _queue_remember_storage_delete()


def render_remember_storage_bridge() -> dict:
    """Read/write the season token through first-party browser localStorage."""
    command = st.session_state.get("remember_storage_command") or {}
    action = str(command.get("action") or "read")
    token = str(command.get("token") or "")
    nonce = str(command.get("nonce") or "")
    default_payload = json.dumps({"token": "", "ready": False, "ack": ""})
    try:
        result = _remember_storage_component(
            data={
                "storage_key": REMEMBER_STORAGE_KEY,
                "action": action,
                "token": token,
                "nonce": nonce,
                "cookie_name": COOKIE_NAME,
                "cookie_max_age": REMEMBER_COOKIE_MAX_AGE,
            },
            default={"payload": default_payload},
            on_payload_change=lambda: None,
            key="pickem_remember_storage_bridge",
        )
        payload_raw = getattr(result, "payload", default_payload) or default_payload
        payload = json.loads(str(payload_raw))
        if nonce and str(payload.get("ack") or "") == nonce:
            st.session_state.remember_storage_command = None
        return {
            "token": str(payload.get("token") or "").strip(),
            "ready": bool(payload.get("ready")),
        }
    except Exception:
        # The first-party cookie remains a compatibility fallback. A browser
        # that blocks localStorage can still use the app normally.
        return {"token": "", "ready": True}


def _sync_pending_storage_command() -> tuple[bool, str]:
    """Run a queued browser storage command and report whether it is pending.

    A login ``set`` is allowed to finish in the background while the signed-in
    home screen renders. This avoids the duplicate/ghost login form caused by
    stopping between authentication and the storage acknowledgement. A logout
    ``delete`` is still completed before the login form is shown, so a stale
    browser token cannot immediately restore the signed-out player.
    """
    command = st.session_state.get("remember_storage_command") or {}
    if not command:
        return False, ""
    action = str(command.get("action") or "")
    render_remember_storage_bridge()
    return bool(st.session_state.get("remember_storage_command")), action


def _apply_restore_result(result, token: str) -> bool:
    if result.ok:
        st.session_state.remember_restore_checked = True
        st.session_state.player = result.player
        st.session_state.active_device_token = token
        return True
    if result.message == "TEMPORARY_SESSION_CHECK_FAILURE":
        # Keep the browser token intact. A later rerun/refresh can retry.
        return False
    return False


def _restore_remembered_cookie_fast_path(cookie_token: str) -> bool:
    """Restore directly from the first-request cookie before mounting localStorage."""
    if st.session_state.player or st.session_state.remember_restore_checked:
        return False
    token = str(cookie_token or "").strip()
    if not token:
        return False
    result = restore_from_cookie(store, token, session_pepper=secret("SESSION_PEPPER"))
    if _apply_restore_result(result, token):
        return True
    # A stale/invalid cookie should not suppress a potentially newer valid
    # localStorage token. Only delete once localStorage has also had a chance.
    return False


def _restore_remembered_player(storage_state: dict | None = None, *, cookie_token: str | None = None) -> None:
    """Restore from localStorage first, with an optional cookie fallback."""
    if st.session_state.player or st.session_state.remember_restore_checked:
        return
    storage_state = storage_state or {}
    if cookie_token is None:
        cookie_token = _browser_remember_cookie()
    cookie_token = str(cookie_token or "").strip()
    storage_token = str(storage_state.get("token") or "").strip()
    storage_ready = bool(storage_state.get("ready"))

    # Components v2 returns browser localStorage on the next rerun. Do not mark
    # the restore attempt complete until that read is ready unless a cookie
    # already restored us on the fast path.
    if not cookie_token and not storage_ready:
        return

    token = storage_token or cookie_token
    if not token:
        st.session_state.remember_restore_checked = True
        return

    result = restore_from_cookie(store, token, session_pepper=secret("SESSION_PEPPER"))
    if _apply_restore_result(result, token):
        return
    if result.message == "TEMPORARY_SESSION_CHECK_FAILURE":
        return

    st.session_state.remember_restore_checked = True
    _queue_remember_cookie_delete()


def _apply_player_auth_result(result, *, error_key: str) -> None:
    """Apply an auth result inside a widget callback before the page reruns."""
    if not result.ok:
        st.session_state[error_key] = result.message
        return

    st.session_state[error_key] = ""
    st.session_state.player = result.player
    st.session_state.remember_restore_checked = True
    if result.cookie_value:
        st.session_state.active_device_token = result.cookie_value
        _queue_remember_cookie_set(result.cookie_value)
    else:
        st.session_state.active_device_token = None


def _signin_submit() -> None:
    result = login_player(
        store,
        nickname=str(st.session_state.get("signin_nickname") or ""),
        pin=str(st.session_state.get("signin_pin") or ""),
        pin_pepper=secret("PIN_PEPPER"),
        session_pepper=secret("SESSION_PEPPER"),
        remember=bool(st.session_state.get("signin_remember", True)),
    )
    _apply_player_auth_result(result, error_key="signin_error")


def _signup_submit() -> None:
    result = register_player(
        store,
        nickname=str(st.session_state.get("signup_nickname") or ""),
        emoji=str(st.session_state.get("signup_emoji") or ""),
        pin=str(st.session_state.get("signup_pin") or ""),
        pin_confirm=str(st.session_state.get("signup_pin_confirm") or ""),
        pin_pepper=secret("PIN_PEPPER"),
        session_pepper=secret("SESSION_PEPPER"),
        remember=bool(st.session_state.get("signup_remember", True)),
    )
    _apply_player_auth_result(result, error_key="signup_error")


def _sign_out_submit() -> None:
    token = st.session_state.get("active_device_token") or _browser_remember_cookie()
    revoke_cookie_session(store, token)
    _queue_remember_cookie_delete()
    # Prevent the initial cookie snapshot from restoring on the sign-out rerun.
    st.session_state.remember_restore_checked = True
    st.session_state.player = None
    st.session_state.active_device_token = None


def player_login_ui() -> None:
    tab_signin, tab_new = st.tabs(["Sign In", "New Player"])
    with tab_signin:
        with st.form("signin_form"):
            st.text_input("Nickname", max_chars=15, autocomplete="username", key="signin_nickname")
            st.text_input(
                "4-digit PIN",
                type="password",
                max_chars=4,
                autocomplete="current-password",
                key="signin_pin",
            )
            st.checkbox("Keep me signed in this season", value=True, key="signin_remember")
            st.form_submit_button(
                "Sign In",
                type="primary",
                use_container_width=True,
                on_click=_signin_submit,
            )
        if st.session_state.get("signin_error"):
            st.error(st.session_state.signin_error)

    with tab_new:
        st.caption("One nickname. One emoji. One PIN. That's it.")
        with st.form("signup_form"):
            st.text_input("Choose a nickname", max_chars=15, key="signup_nickname")
            st.text_input(
                "Choose one emoji",
                max_chars=8,
                placeholder="Tap here, then choose an emoji",
                autocomplete="off",
                key="signup_emoji",
            )
            st.text_input(
                "Create a 4-digit PIN",
                type="phone",
                max_chars=4,
                placeholder="4 digits",
                autocomplete="off",
                icon="",
                key="signup_pin",
            )
            st.text_input(
                "Confirm PIN",
                type="phone",
                max_chars=4,
                placeholder="4 digits",
                autocomplete="off",
                icon="",
                key="signup_pin_confirm",
            )
            st.checkbox("Keep me signed in this season", value=True, key="signup_remember")
            st.form_submit_button(
                "Create Player",
                type="primary",
                use_container_width=True,
                on_click=_signup_submit,
            )
        if st.session_state.get("signup_error"):
            st.error(st.session_state.signup_error)


def commish_login_ui() -> None:
    st.markdown("### Commissioner")
    st.caption("Separate admin access. This does not use a player PIN.")
    with st.form("commish_login"):
        username = st.text_input("Commissioner username")
        pin = st.text_input("6-digit admin PIN", type="password", max_chars=6)
        submit = st.form_submit_button("Enter Commissioner", type="primary", use_container_width=True)
    if submit:
        user_ok = safe_secret_match(username.strip().casefold(), secret("COMMISH_USERNAME").strip().casefold())
        pin_ok = safe_secret_match(pin, secret("COMMISH_PIN"))
        if user_ok and pin_ok:
            st.session_state.commish = True
            st.rerun()
        st.error("Commissioner login is incorrect.")


# -----------------------------
# Remembered-login restore
# -----------------------------
# A queued browser command comes from a deliberate auth action. Login writes
# may finish while the signed-in page renders; logout deletion completes before
# the login form returns. This keeps one-click behavior without ghosting forms.
_storage_sync_pending, _storage_sync_action = _sync_pending_storage_command()
if _storage_sync_pending and _storage_sync_action == "delete":
    st.caption("Signing out…")
    st.stop()

_storage_state = {"token": "", "ready": True}
if not st.session_state.player and not st.session_state.remember_restore_checked:
    _cookie_token = _browser_remember_cookie()
    _cookie_restored = _restore_remembered_cookie_fast_path(_cookie_token)
    if not _cookie_restored:
        _storage_state = render_remember_storage_bridge()
        # Cookie was already tried. Let localStorage choose the fallback so a
        # stale cookie cannot hide a newer valid browser token.
        _restore_remembered_player(_storage_state, cookie_token="")

        # If localStorage has not answered yet, avoid flashing a sign-in form
        # and—more importantly—avoid mounting clickable widgets that could
        # compete with the component's automatic rerun.
        if not st.session_state.player and not st.session_state.remember_restore_checked and not _storage_state.get("ready"):
            st.caption("Checking remembered sign-in…")
            st.stop()


if st.session_state.commish:
    # Gate 2's isolated lineup-builder test remains Commissioner-only in v1.0.2.
    # It can use a selected real account as the identity while all picks remain
    # confined to the synthetic Gate 2 Test Week.
    if st.session_state.get("gate2_demo"):
        demo_player_id = str(st.session_state.get("gate2_demo_player_id") or "")
        demo_player = store.get_player_by_id(demo_player_id) if demo_player_id else None
        if demo_player:
            st.info("Commissioner-only Gate 2 test week. These picks are isolated and never affect the real NFL week.")
            st.session_state.use_demo_week = True
            render_player_game(
                store,
                demo_player,
                allow_demo_week=True,
                skip_onboarding=True,
            )
        else:
            st.session_state.gate2_demo = False
            st.session_state.pop("gate2_demo_player_id", None)
            st.error("The selected Gate 2 demo player is no longer available.")
        st.stop()

    # Gate 4 demo remains an isolated Commissioner diagnostic. Gate 5 owns the
    # real admin dashboard and never requires a player login.
    if st.session_state.get("gate4_demo"):
        render_gate4_demo()
        st.stop()

    try:
        render_commissioner_dashboard(store, pin_pepper=secret("PIN_PEPPER"))
    except Exception as exc:
        _friendly_runtime_error("commissioner", exc)
    st.stop()

if st.session_state.player:
    # Public/player sessions may never remain inside the synthetic Gate 2 week.
    st.session_state.gate2_demo = False
    st.session_state.pop("gate2_demo_player_id", None)
    try:
        render_player_game(store, st.session_state.player, on_sign_out=_sign_out_submit)
    except Exception as exc:
        _friendly_runtime_error("player", exc)
    st.stop()

player_login_ui()
st.markdown("---")
with st.expander("Commissioner"):
    commish_login_ui()
