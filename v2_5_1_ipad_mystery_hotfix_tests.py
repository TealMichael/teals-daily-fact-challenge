from pathlib import Path

from fact_engine import APP_VERSION
from weekly_mystery import MYSTERIES, LEARNING_PARAGRAPHS, learning_paragraph_for

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
PAD = (ROOT / "answer_pad_component" / "index.html").read_text(encoding="utf-8")
PIN = (ROOT / "pin_entry_component" / "index.html").read_text(encoding="utf-8")


def run():
    checks = {}
    checks["version 2.6"] = APP_VERSION == "2.13.1"

    # Shared Step 2/3/Practice keypad must size to its actual browser content.
    checks["answer pad no fixed 310 height"] = "setHeight(310)" not in PAD and "height=310" not in PAD
    checks["answer pad measures scroll height"] = "document.documentElement.scrollHeight" in PAD
    checks["answer pad observes resize"] = "ResizeObserver" in PAD
    checks["answer pad digit taps still local"] = "addDigit" in PAD and "setComponentValue" in PAD

    # Student PIN has no HTML password/input surface at all, so iPad password
    # generation/autofill cannot treat it as an account password field.
    checks["student pin custom component declared"] = "PIN_ENTRY_COMPONENT" in APP and "pin_entry_component" in APP
    checks["student login uses pin pad"] = 'pin, submitted = render_student_pin(key=f"student_login_pin_pad_' in APP
    checks["student password field removed"] = 'st.text_input("4-digit PIN", type="password"' not in APP
    checks["teacher password remains protected"] = 'st.text_input("Teacher password", type="password")' in APP
    checks["pin component contains no input field"] = "<input" not in PIN.lower()
    checks["pin component is four digits"] = "digits.length >= 4" in PIN and PIN.count("data-slot=\"") == 4
    checks["pin component touch keypad"] = all(token in PIN for token in ['data-digit="1"', 'data-digit="0"', '⌫'])
    checks["pin component supports hardware keys"] = "document.addEventListener('keydown'" in PIN
    checks["pin component only sends completed pin"] = "function submitPin()" in PIN and "if (submitted || digits.length !== 4) return;" in PIN

    # Mystery correct guesses now feel like a reward and every reveal teaches.
    checks["mystery balloons"] = "st.balloons()" in APP
    checks["mystery fanfare heading"] = "YOU SOLVED THE MYSTERY!" in APP
    checks["mystery learning heading"] = "📚 Meet" in APP
    checks["mystery fun fact"] = "🤯 **Fun fact:**" in APP
    checks["Thursday correct gets fanfare"] = "_render_mystery_win(mystery, existing, week_start)" in APP
    checks["Friday correct gets fanfare"] = "_render_mystery_win(mystery, solved_guess, week_start)" in APP
    checks["fanfare only once per solve session"] = "mystery_win_fanfare::" in APP

    checks["all mysteries have learning paragraphs"] = len(LEARNING_PARAGRAPHS) == len(MYSTERIES) == 80
    checks["all paragraphs substantial"] = all(len(learning_paragraph_for(m)) >= 150 for m in MYSTERIES)
    lincoln = next(m for m in MYSTERIES if m.key == "abraham-lincoln")
    lincoln_text = learning_paragraph_for(lincoln)
    checks["Lincoln teaches presidency"] = "16th president" in lincoln_text
    checks["Lincoln teaches birth date"] = "February 12, 1809" in lincoln_text
    checks["Lincoln teaches reading"] = "loved to read books" in lincoln_text
    checks["Lincoln teaches Honest Abe"] = '"Honest Abe"' in lincoln_text

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.6 iPad/Mystery hotfix: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
