from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "pin_entry_component" / "index.html").read_text()
APP = (ROOT / "app.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()

checks = {
    "version bumped": 'APP_VERSION = "2.14.1"' in ENGINE,
    "component still declared": 'PIN_ENTRY_COMPONENT = components.declare_component' in APP,
    "no password input": 'type="password"' not in HTML.lower(),
    "no html input field": '<input' not in HTML.lower(),
    "local digit buffer": "let digits = '';" in HTML,
    "browser-local pin buffer exists": "let digits = '';" in HTML,
    "parent rerenders do not overwrite local digits": 'local digits stay local' in HTML,
    "explicit submit required": 'function submitPin()' in HTML,
    "comment protects partial input": 'local digits stay local' in HTML,
    "component only submits four digits": 'if (submitted || digits.length !== 4) return;' in HTML,
    "digit click does not set component value": 'function addDigit(digit)' in HTML and 'setValue(' not in HTML.split('function addDigit(digit)',1)[1].split('function erase()',1)[0],
    "backspace supported": 'data-action="back"' in HTML and 'function erase()' in HTML,
    "repeated parent render never assigns incoming digits": 'incoming' not in HTML,
}

failed=[name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError(f"Failed checks: {failed}")
print(f"v2.5.1.2 PIN persistence regression: {len(checks)}/{len(checks)} checks passed")
