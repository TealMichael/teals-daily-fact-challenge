"""Signed, password-revocable 30-day teacher browser sessions.

This module deliberately does not use the student token format. A verified
teacher token grants teacher access, so it must be signed by a server-only
secret and never contain a plaintext teacher password.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets

from persistent_login import REMEMBER_DAYS

TEACHER_TOKEN_VERSION = 1
_MAX_TOKEN_LENGTH = 4096


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _password_version(password: str, secret: str) -> str:
    """A keyed version check; changing the password invalidates old tokens."""
    return hmac.new(
        secret.encode("utf-8"),
        b"tdfc:teacher-password:v1:" + password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def issue_teacher_token(
    teacher_password: str,
    signing_secret: str,
    *,
    now: datetime | None = None,
) -> str:
    """Issue a teacher-only token, valid for 30 days on this browser."""
    if not teacher_password or not signing_secret:
        raise ValueError("Teacher password and server signing secret are required")
    now = now or datetime.now(timezone.utc)
    payload = {
        "v": TEACHER_TOKEN_VERSION,
        "kind": "teacher",
        "exp": int((now + timedelta(days=REMEMBER_DAYS)).timestamp()),
        "pv": _password_version(teacher_password, signing_secret),
        "nonce": secrets.token_urlsafe(16),
    }
    body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_key = hmac.new(
        signing_secret.encode("utf-8"), b"tdfc:teacher-token:v1", hashlib.sha256
    ).digest()
    signature = _encode(hmac.new(signing_key, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_teacher_token(
    token: str,
    current_teacher_password: str,
    signing_secret: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Reject expired, tampered, student, or old-password teacher tokens."""
    if not token or not current_teacher_password or not signing_secret or len(token) > _MAX_TOKEN_LENGTH:
        return False
    try:
        body, supplied_signature = token.split(".", 1)
        signing_key = hmac.new(
            signing_secret.encode("utf-8"), b"tdfc:teacher-token:v1", hashlib.sha256
        ).digest()
        expected_signature = _encode(hmac.new(signing_key, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return False
        payload = json.loads(_decode(body).decode("utf-8"))
        if not isinstance(payload, dict):
            return False
        if payload.get("v") != TEACHER_TOKEN_VERSION or payload.get("kind") != "teacher":
            return False
        now = now or datetime.now(timezone.utc)
        if int(payload.get("exp", 0)) <= int(now.timestamp()):
            return False
        version = str(payload.get("pv") or "")
        return hmac.compare_digest(version, _password_version(current_teacher_password, signing_secret))
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return False
    except Exception:
        # Bad browser data must never break the sign-in page.
        return False
