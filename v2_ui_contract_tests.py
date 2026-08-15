from pathlib import Path


def run():
    app = Path("app.py").read_text(encoding="utf-8")
    engine = Path("adaptive_engine.py").read_text(encoding="utf-8")
    migration = Path("RUN_THIS_ONCE_IN_SUPABASE_v2.sql").read_text(encoding="utf-8").lower()

    required_app = [
        "Daily 10 complete",
        "Learning Step 2 of 3 · Fix Your Misses",
        "Learning Step 3 of 3 · 🎯 Your Focus Practice",
        "YOU'RE DONE FOR TODAY!",
        "Learning Streak",
        "total Daily Stars",
        "My Growth",
        "there is no placement test",
        "🎯 My Focus Facts",
        "Mastery & Focus",
        "Full Class Fact Map",
        "Personal Focus override",
        "runs quietly in the background",
        "count_for_mastery=False",
        "record_mastery_evidence_batch",
    ]
    for phrase in required_app:
        assert phrase in app, phrase

    required_engine = [
        "New students begin with an unknown",
        "FOCUS_SESSION_LENGTH = 8",
        "STATUS_UNKNOWN",
        "recent_daily_misses",
        "override_family",
        "maintenance fact",
    ]
    for phrase in required_engine:
        assert phrase in engine, phrase

    required_schema = [
        "student_fact_mastery",
        "daily_learning_progress",
        "response_seconds",
        "activity_type",
        "is_retry",
        "focus_override",
        "app_settings",
    ]
    for phrase in required_schema:
        assert phrase in migration, phrase

    # No student-facing placement/pretest flow should be introduced.
    forbidden = ["Take placement test", "Placement Test", "diagnostic test", "50-fact test"]
    for phrase in forbidden:
        assert phrase not in app

    print(f"v2_ui_contract_tests: PASS ({len(required_app)+len(required_engine)+len(required_schema)+len(forbidden)} v2 learning/UI checks)")


if __name__ == "__main__":
    run()
