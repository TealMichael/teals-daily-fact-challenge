from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "pin_entry_component" / "index.html").read_text()
APP = (ROOT / "app.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()

checks = {
    "version bumped": 'APP_VERSION = "2.11.0"' in ENGINE,
    "pin component remains custom": 'PIN_ENTRY_COMPONENT = components.declare_component' in APP,
    "no html input": '<input' not in HTML.lower(),
    "no password field": 'type="password"' not in HTML.lower(),
    "check is real button": 'id="submit"' in HTML and 'class="submit"' in HTML,
    "check enables only at four digits": 'submit.disabled = submitted || digits.length !== 4;' in HTML,
    "check has submit handler": "button.id === 'submit'" in HTML and 'submitPin();' in HTML,
    "component submits structured pin": "setValue({pin:digits, submitted:true, nonce:Date.now()});" in HTML,
    "digits do not submit automatically": 'function addDigit(digit)' in HTML and 'setValue(' not in HTML.split('function addDigit(digit)',1)[1].split('function erase()',1)[0],
    "enter key submits": "event.key === 'Enter'" in HTML and 'submitPin();' in HTML,
    "python consumes dict submit": 'result.get("submitted")' in APP and 'result.get("pin")' in APP,
    "login is triggered by pin submit": 'pin, submitted = render_student_pin' in APP and 'if submitted:' in APP,
    "old streamlit sign-in button removed": 'key="student_login_submit"' not in APP,
    "remember choice occurs before pin": APP.index('student_login_remember') < APP.index('pin, submitted = render_student_pin'),
    "wrong pin resets keypad": 'student_pin_reset_counter = pin_reset + 1' in APP,
    "wrong pin message survives rerun": 'student_login_error' in APP,
    "successful remembered login still issues token": 'issue_student_token(student.student_id, pin, _persistent_login_secret())' in APP,
}
failed=[name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError(f"Failed checks: {failed}")
print(f"v2.6 PIN submit/login regression: {len(checks)}/{len(checks)} checks passed")
