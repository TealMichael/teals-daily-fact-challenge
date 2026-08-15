from pathlib import Path


def run():
    text = Path("app.py").read_text(encoding="utf-8")
    required = [
        "Teal's Daily Fact Challenge",
        "10 facts a day · accuracy first · speed breaks ties",
        "The clock starts the instant you submit Fact 1",
        "DAILY_SPRINT_COMPONENT",
        "standings may change as more classmates finish · accuracy ranks first, with time used privately as the tiebreaker",
        "Only the Top 10 is shown",
        "Choose your area of need",
        "See the multiplication",
        "array-grid",
        "Teacher Dashboard",
        "Create students + PINs",
        "Reset today's Daily attempt",
        "TEACHER_PASSWORD",
    ]
    for phrase in required:
        assert phrase in text, phrase

    # Classroom-only request: no student share-result feature.
    forbidden = ["Share result", "Copy score", "navigator.share", "Wordle"]
    for phrase in forbidden:
        assert phrase not in text, phrase

    # Outside-Top-10 students must never be shown their exact lower rank.
    assert "Your exact class rank stays private" in text

    print(f"ui_contract_tests: PASS ({len(required) + len(forbidden) + 1} UI/privacy checks)")


if __name__ == "__main__":
    run()
