from __future__ import annotations

"""Short-lived, presentation-only launch grants for independent browser windows.

New Streamlit windows have separate sessions. A grant never authenticates the
teacher dashboard, student roster, or any other route: only the published slide
for one classroom/date. It expires after two minutes and is removed from the
window URL after acceptance.
"""

import base64
from datetime import date
from functools import lru_cache
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from uuid import uuid4

import streamlit as st


MAX_GRANT_AGE = 120


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decoded(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def launch_secret() -> str:
    """Domain-separate the grant from any student session-token format."""
    try:
        teacher = str(st.secrets.get("TEACHER_PASSWORD") or "")
        app_key = str(st.secrets.get("SUPABASE_SECRET_KEY") or "")
    except Exception:
        return ""
    if not teacher or not app_key:
        return ""
    return hashlib.sha256(("tdfc-igniter-window-v1|" + teacher + "|" + app_key).encode()).hexdigest()


def make_launch_grant(class_id: str, day: date, secret: str, *, now: int | None = None) -> str:
    if not secret:
        raise ValueError("A server-side launch secret is required.")
    issued = int(time.time() if now is None else now)
    payload = {
        "v": 1, "c": str(class_id), "d": day.isoformat(),
        "exp": issued + MAX_GRANT_AGE, "n": uuid4().hex,
    }
    body = _encoded(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _encoded(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return body + "." + signature


def verify_launch_grant(token: str, secret: str, *, now: int | None = None) -> dict | None:
    if not token or not secret or len(token) > 1000:
        return None
    try:
        body, signature = token.split(".")
        expected = _encoded(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_decoded(body))
        current = int(time.time() if now is None else now)
        expiry = int(payload["exp"])
        if (payload.get("v") != 1 or not current < expiry <= current + MAX_GRANT_AGE
                or not 0 < len(str(payload["c"])) <= 128
                or not isinstance(payload.get("n"), str) or len(payload["n"]) != 32):
            return None
        date.fromisoformat(payload["d"])
        return {"class_id": str(payload["c"]), "day": payload["d"]}
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
        return None


@lru_cache(maxsize=1)
def _launcher():
    return st.components.v2.component(
        "tdfc_igniter_popout_v226",
        html='<div class="igniter-launch"><button id="open-slide" type="button">🖥️ Display Igniter ↗</button>'
             '<a id="fallback-slide" target="_blank" rel="noopener noreferrer" hidden>Open presentation in a new tab</a>'
             '<span id="popup-message" role="status"></span></div>',
        css="""
        .igniter-launch {display:flex;align-items:center;flex-wrap:wrap;gap:12px;font:inherit}
        #open-slide {border:0;border-radius:9px;background:#087a70;color:white;
          font:650 16px system-ui;padding:12px 20px;min-height:46px;cursor:pointer}
        #open-slide:hover {background:#075c56}
        #open-slide:focus-visible {outline:3px solid #efa931;outline-offset:2px}
        #fallback-slide {font:14px system-ui;color:#087a70;text-decoration:underline}
        #fallback-slide[hidden] {display:none}
        #popup-message {font:13px system-ui;color:#5a6463}
        """,
        js="""
        export default function({parentElement,data}) {
          const button = parentElement.querySelector('#open-slide');
          const fallback = parentElement.querySelector('#fallback-slide');
          const message = parentElement.querySelector('#popup-message');
          fallback.href = data.url;
          button.onclick = () => {
            const popup = window.open(data.url,'tdfc_igniter_display',
              'popup=yes,width=1440,height=900,resizable=yes,scrollbars=yes');
            if (popup) {
              popup.focus();
              fallback.hidden = true;
              message.textContent = 'Move the new window to your second screen.';
            } else {
              fallback.hidden = false;
              message.textContent = 'The browser blocked the window. Use the link instead.';
            }
          };
        }
        """,
    )


def render_igniter_window_button(class_id: str, day: date) -> None:
    if not st.session_state.get("teacher_authed") or st.session_state.get("teacher_test_student_mode"):
        return
    secret = launch_secret()
    if not secret:
        st.warning("Presentation-window access is not ready. Check the app's existing teacher/server setup.")
        return
    base = str(st.context.url).split("?", 1)[0]
    token = make_launch_grant(str(class_id), day, secret)
    url = base + "?" + urlencode({"igniter_window": token})
    _launcher()(data={"url": url}, key="today_igniter_popout")
