from pathlib import Path


def run():
    html = Path("daily_sprint_component/index.html").read_text(encoding="utf-8")
    required = [
        "Fact ${state.index + 1} of 10",
        "Fact 1 untimed",
        "current.startedMs = Date.now()",
        "state.index === 9",
        "timed_seconds",
        "localStorage",
        "streamlit:setComponentValue",
        "inputmode=\"numeric\"",
        "No right/wrong feedback until all 10 are finished",
        "Accuracy ranks before speed",
        "← Back",
        "Your timer is still running while you revise Fact 1",
    ]
    for phrase in required:
        assert phrase in html, phrase
    # The Daily component must not contain teaching feedback before completion.
    forbidden = ["Correct!", "Wrong!", "correct answer", "Try again"]
    for phrase in forbidden:
        assert phrase not in html
    print(f"component_contract_tests: PASS ({len(required) + len(forbidden)} one-at-a-time timer/feedback checks)")


if __name__ == "__main__":
    run()
