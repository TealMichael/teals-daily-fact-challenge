from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json

REMEMBER_DAYS = 30
TOKEN_VERSION = 1


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _pin_fingerprint(student_id: str, pin: str, secret: str) -> str:
    message = f"tdfc-pin:{student_id}:{pin}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()[:24]


def issue_student_token(student_id: str, pin: str, secret: str, *, now: datetime | None = None) -> str:
    """Create a signed 30-day browser token without storing the student's PIN in the browser."""
    now = now or datetime.now(timezone.utc)
    expires = now + timedelta(days=REMEMBER_DAYS)
    payload = {
        "v": TOKEN_VERSION,
        "student_id": str(student_id),
        "exp": int(expires.timestamp()),
        "pv": _pin_fingerprint(str(student_id), str(pin), str(secret)),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = _b64encode(body)
    signature = _b64encode(hmac.new(str(secret).encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"



def peek_student_id(token: str) -> str | None:
    """Read only the untrusted student id so the current record can be fetched.

    Callers must still run verify_student_token before trusting the token.
    """
    try:
        encoded = token.split(".", 1)[0]
        payload = json.loads(_b64decode(encoded).decode("utf-8"))
        student_id = str(payload.get("student_id") or "")
        return student_id or None
    except Exception:
        return None

def verify_student_token(
    token: str,
    current_pin: str | None,
    secret: str,
    *,
    now: datetime | None = None,
) -> dict | None:
    """Validate signature, expiry, and the student's current PIN version.

    Returning None means the browser token should be discarded. Changing a PIN
    invalidates the prior token because the fingerprint no longer matches.
    """
    if not token or not current_pin or not secret:
        return None
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _b64encode(
            hmac.new(str(secret).encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_b64decode(encoded).decode("utf-8"))
        if int(payload.get("v", 0)) != TOKEN_VERSION:
            return None
        student_id = str(payload.get("student_id") or "")
        if not student_id:
            return None
        now = now or datetime.now(timezone.utc)
        if int(payload.get("exp", 0)) <= int(now.timestamp()):
            return None
        expected_pin_version = _pin_fingerprint(student_id, str(current_pin), str(secret))
        if not hmac.compare_digest(str(payload.get("pv") or ""), expected_pin_version):
            return None
        return payload
    except Exception:
        return None
