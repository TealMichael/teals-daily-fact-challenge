from pathlib import Path


def run():
    html = Path("daily_sprint_component/index.html").read_text(encoding="utf-8")
    required = [
        "Fact ${state.index+1} of 10",
        "Fact 1 starts the timer",
        "Timer running quietly",
        "current.startedMs=Date.now()",
        "current.index===9",
        "timed_seconds",
        "response_seconds",
        "current.responseSeconds[0]=null",
        "firstSubmission",
        "localStorage",
        "streamlit:setComponentValue",
        'data-digit="1"',
        'data-digit="0"',
        "⌫",
        "✓",
        "No right/wrong feedback until all 10 are finished",
        "← Back to previous fact",
        "document.addEventListener('keydown'",
    ]
    for phrase in required:
        assert phrase in html, phrase

    # Taps stay inside the browser. The component sends a value only once the
    # student submits a complete answer / Daily.
    assert "setValue(payload)" in html
    assert "data-digit" in html and "addDigit" in html
    assert '<input' not in html.lower()  # no mobile software keyboard required

    # Competition clock is recorded but never visibly counts up.
    assert "⏱" not in html
    assert "setInterval" not in html

    # No teaching feedback during the competitive Daily.
    for phrase in ["Correct!", "Wrong!", "correct answer", "Try again"]:
        assert phrase not in html
    print(f"component_contract_tests: PASS ({len(required)+8} keypad/hidden-timer checks)")


if __name__ == "__main__":
    run()
