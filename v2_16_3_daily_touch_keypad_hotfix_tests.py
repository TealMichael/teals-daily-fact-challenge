from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fact_engine import APP_VERSION, CHALLENGE_VERSION

ROOT = Path(__file__).resolve().parent
DAILY_PATH = ROOT / "daily_sprint_component" / "index.html"
DAILY = DAILY_PATH.read_text(encoding="utf-8")


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def function_body(name: str) -> str:
    match = re.search(rf"function\s+{re.escape(name)}\([^)]*\)\{{([^}}]*)\}}", DAILY, flags=re.S)
    assert match, f"missing {name}"
    return match.group(1)


def run() -> None:
    checks: dict[str, bool] = {}

    checks["version bumped"] = APP_VERSION == "2.19.6"
    checks["challenge version untouched"] = CHALLENGE_VERSION == "TDFC-DAILY-v1"

    # Freeze the intentionally changed Daily component after the touch-input repair.
    checks["daily component hotfix hash"] = sha("daily_sprint_component/index.html") == "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad"

    # The keypad must stay mounted while digits are entered. Rebuilding the keypad
    # after every tap can lose a rapid second touch on touch devices.
    add_digit = function_body("addDigit")
    erase = function_body("erase")
    checks["digit tap updates display without rerender"] = "updateDigitDisplay()" in add_digit and "render()" not in add_digit
    checks["erase updates display without rerender"] = "updateDigitDisplay()" in erase and "render()" not in erase
    checks["stable display helper exists"] = "function updateDigitDisplay()" in DAILY
    checks["display helper preserves aria-live node"] = "entry.textContent=digits||'Tap your answer'" in DAILY
    checks["display helper clears stale validation"] = "error.textContent=''" in DAILY

    # Preserve the existing number-pad and Daily contracts.
    checks["zero button remains present"] = 'data-digit="0">0</button>' in DAILY
    checks["three digit cap retained"] = "digits.length>=3" in add_digit
    checks["leading-zero normalization retained"] = "digits.replace(/^0+/,'')||'0'" in add_digit
    checks["question transition still rerenders"] = "current.index+=1; current.shownMs=Date.now(); saveState(current); digits=''; render();" in DAILY
    checks["back navigation still rerenders"] = "current.index-=1" in DAILY and "digits=current.answers[current.index]===null?'':String(current.answers[current.index]);render();" in DAILY
    checks["hardware keyboard retained"] = "document.addEventListener('keydown'" in DAILY
    checks["no mobile text input introduced"] = "<input" not in DAILY.lower()
    checks["first-answer evidence retained"] = "current.firstAnswers[current.index]=value" in DAILY
    checks["response timing retained"] = "current.responseSeconds[current.index]" in DAILY
    checks["official completion payload retained"] = "setValue(payload)" in DAILY and "timed_seconds" in DAILY
    checks["Daily progress retained"] = "Fact ${state.index+1} of 10" in DAILY and "progressHtml(state)" in DAILY

    # Everything adjacent to the Daily sprint remains exactly as v2.16.2.
    protected = {
        "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
        "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
        "pin_entry_component/index.html": "18a89b45481f83f33fd93746bdf854ba0e4b216c0c1f0904e035f871d5d8c2b7",
        "persistent_login_component/index.html": "fae94c44f25512d2c017b24e17e3be2d987f21604072ed4c061fbae1cc9f9585",
        "daily_alt_component/index.html": "332ee7265c450b00d4848a059f000439dba2089c4ec765bf18f41e2bed734c4d",
        "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
        "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
        "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
        "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
        "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
    }
    for relative, expected in protected.items():
        checks[f"unchanged: {relative}"] = sha(relative) == expected

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.17.0 Daily touch keypad hotfix: PASS ({len(checks)}/{len(checks)} checks)")


if __name__ == "__main__":
    run()
