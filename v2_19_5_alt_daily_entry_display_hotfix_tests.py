from pathlib import Path
from fact_engine import APP_VERSION

ROOT = Path(__file__).resolve().parent
UI = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
DAILY = (ROOT / "daily_alt_component" / "index.html").read_text(encoding="utf-8")

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

check("v2.19.5 version", APP_VERSION == "2.19.9")
check("alternate Daily component cache-busted", 'tdfc_alt_daily_v2195' in UI)
check("answer display has stable entry id", 'id="entry" class="${digits?' in DAILY)
check("display updater targets entry id", "document.getElementById('entry')" in DAILY)
check("digit taps update visible answer", "function addDigit(d)" in DAILY and "updateEntry()" in DAILY)
check("minus tap updates visible answer", "function toggleMinus()" in DAILY and "updateEntry()" in DAILY)
check("delete tap updates visible answer", "function erase()" in DAILY and "updateEntry()" in DAILY)
check("entry text swaps placeholder for digits", "entry.textContent=digits||'Tap your answer'" in DAILY)
check("submit still reads browser-local digits", "const value=Number(digits)" in DAILY)
check("Fix component identity advanced for follow-up parity", 'tdfc_alt_fix_v2197' in UI)
check("Focus component identity advanced for follow-up parity", 'tdfc_alt_focus_v2197' in UI)

print(f"v2.19.5 Alternate Daily Entry Display Hotfix: PASS ({len(checks)}/{len(checks)} checks)")
