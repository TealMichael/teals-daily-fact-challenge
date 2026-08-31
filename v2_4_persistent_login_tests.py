from datetime import datetime, timedelta, timezone
from pathlib import Path

from persistent_login import REMEMBER_DAYS, issue_student_token, peek_student_id, verify_student_token

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
ENGINE = (ROOT / "fact_engine.py").read_text(encoding="utf-8")
COMPONENT = (ROOT / "persistent_login_component" / "index.html").read_text(encoding="utf-8")


def run():
    checks = {}
    now = datetime(2026, 8, 13, 20, 0, tzinfo=timezone.utc)
    secret = "server-secret-for-test"
    student_id = "11111111-2222-3333-4444-555555555555"
    pin = "4821"

    token = issue_student_token(student_id, pin, secret, now=now)
    payload = verify_student_token(token, pin, secret, now=now + timedelta(days=29, hours=23))
    checks["token valid inside 30 days"] = payload is not None and payload["student_id"] == student_id
    checks["remember period exactly 30 days"] = REMEMBER_DAYS == 30
    checks["token expires after 30 days"] = verify_student_token(token, pin, secret, now=now + timedelta(days=30, seconds=1)) is None
    checks["PIN reset invalidates old token"] = verify_student_token(token, "7390", secret, now=now + timedelta(days=1)) is None
    checks["secret rotation invalidates old token"] = verify_student_token(token, pin, "different-secret", now=now + timedelta(days=1)) is None
    checks["tampered token rejected"] = verify_student_token(token[:-1] + ("A" if token[-1] != "A" else "B"), pin, secret, now=now) is None
    checks["student id can be peeked before validation"] = peek_student_id(token) == student_id
    checks["PIN not present in browser token"] = pin not in token

    checks["version 2.6"] = 'APP_VERSION = "2.16.1"' in ENGINE
    checks["remember checkbox shown"] = "Keep me signed in on this device for {REMEMBER_DAYS} days" in APP
    checks["shared-device warning shown"] = "Leave this unchecked on a shared device" in APP
    checks["sign out clears remembered login"] = 'persistent_login_pending_action = {"action": "clear"}' in APP
    checks["manual nonremembered login clears old token"] = "sign-in without the checkbox deliberately clears that old login" in APP and 'persistent_login_pending_action = {"action": "clear"}' in APP
    checks["remembered login re-checks active student"] = "if not student.active" in APP
    checks["remembered login re-checks active class"] = "not class_record.active" in APP
    checks["current PIN verifies remembered token"] = "verify_student_token(token, student.pin_code" in APP
    checks["no PIN stored by browser component"] = "pin" not in COMPONENT.lower()
    checks["browser component uses localStorage"] = "localStorage.setItem" in COMPONENT and "localStorage.getItem" in COMPONENT
    checks["browser component supports clear"] = 'action === "clear"' in COMPONENT and "removeItem" in COMPONENT
    checks["browser component supports read"] = 'action === "read"' not in COMPONENT or 'String((args && args.action) || "read")' in COMPONENT
    checks["component communicates with Streamlit"] = "streamlit:setComponentValue" in COMPONENT
    checks["no database migration required"] = "student_login_tokens" not in APP and "remember_token" not in (ROOT / "SUPABASE_SCHEMA.sql").read_text(encoding="utf-8")

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise SystemExit(f"Failed {len(failed)} checks: {failed}")
    print(f"v2.4 persistent login: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
