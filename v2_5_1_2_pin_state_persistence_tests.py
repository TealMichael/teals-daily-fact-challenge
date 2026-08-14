from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "pin_entry_component" / "index.html").read_text()
APP = (ROOT / "app.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()

checks = {
    "version bumped": 'APP_VERSION = "2.5.1.2"' in ENGINE,
    "component still declared": 'PIN_ENTRY_COMPONENT = components.declare_component' in APP,
    "no password input": 'type="password"' not in HTML.lower(),
    "no html input field": '<input' not in HTML.lower(),
    "local digit buffer": "let digits = '';" in HTML,
    "hydration guard exists": 'let hydrated = false;' in HTML,
    "first render only guard": 'if (!hydrated)' in HTML,
    "hydrate becomes true": 'hydrated = true;' in HTML,
    "comment protects partial input": 'must never overwrite partially-entered local digits' in HTML,
    "component only sends completed pin": 'if (digits.length !== 4 || digits === lastSent) return;' in HTML,
    "digit click does not set component value": 'function addDigit(digit)' in HTML and 'sendIfComplete();' in HTML,
    "backspace supported": 'data-action="back"' in HTML and 'function erase()' in HTML,
    "repeated parent render no longer assigns incoming after hydration": "if (incoming !== digits)" not in HTML,
}

failed=[name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError(f"Failed checks: {failed}")
print(f"v2.5.1.2 PIN persistence regression: {len(checks)}/{len(checks)} checks passed")
