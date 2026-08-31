from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / 'pin_entry_component' / 'index.html').read_text()
APP = (ROOT / 'app.py').read_text()
ENGINE = (ROOT / 'fact_engine.py').read_text()

checks = {
    'version bumped': 'APP_VERSION = "2.14.2"' in ENGINE,
    'pin component declared': 'tdfc_student_pin' in APP,
    'no input element': '<input' not in HTML.lower(),
    'no password field': 'type="password"' not in HTML.lower(),
    'permanent pad dom': 'id="pad"' in HTML,
    'delegated click handler': "pad.addEventListener('click'" in HTML,
    'uses closest button': "event.target.closest('button')" in HTML,
    'digits are not rerendering DOM': 'innerHTML' not in HTML,
    'masked dots': "slot.textContent = filled ? '●' : ''" in HTML,
    'four digit completion': "digits.length !== 4" in HTML,
    'backspace supported': "data-action=\"back\"" in HTML and 'function erase()' in HTML,
    'physical keyboard supported': "document.addEventListener('keydown'" in HTML,
    'streamlit value only on explicit complete submit': 'submitPin()' in HTML and "setValue({pin:digits, submitted:true, nonce:Date.now()});" in HTML,
}

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError(f'Failed: {failed}')
print(f"v2.5.1.2 PIN tap hotfix: {len(checks)}/{len(checks)} checks passed")
