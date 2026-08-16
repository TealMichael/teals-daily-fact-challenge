from pathlib import Path

from fact_engine import APP_VERSION

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
STORE = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")


def section(name: str, next_name: str | None = None) -> str:
    start = APP.index(f"def {name}")
    end = APP.index(f"\ndef {next_name}", start) if next_name else len(APP)
    return APP[start:end]


def run():
    checks = {}
    checks["version 2.9.3"] = APP_VERSION == "2.9.3"

    teacher = section("render_teacher", "maybe_render_db_diagnostic")
    checks["teacher dashboard is lazy"] = "st.tabs(" not in teacher and 'section = st.radio(' in teacher
    checks["only chosen teacher section dispatches"] = all(x in teacher for x in [
        'if section == "📊 Today"', 'elif section == "👥 Classes & Rosters"',
        'elif section == "🎯 Mastery & Focus"', 'elif section == "🕵️ Weekly Mystery"',
        'elif section == "🛠️ Student Support"', 'render_teacher_test_student_launcher(store)'
    ])

    today = section("render_teacher_today", "_override_label")
    checks["today loads roster once"] = today.count("store.list_students(selected.class_id)") == 1
    checks["today reuses roster in status"] = "students=students" in today and "store.daily_status" in today
    checks["today reuses roster in progress"] = "store.class_learning_progress(selected.class_id, challenge.challenge_id, students=students)" in today
    checks["today reuses roster in streak stats"] = "store.class_learning_stats(selected.class_id, day, students=students)" in today
    checks["today derives leaderboard locally"] = "_leaderboard_from_status(status" in today and "store.leaderboard(" not in today
    checks["today avoids duplicate completed query"] = "completed_attempts_for_class" not in today

    projector = section("render_teacher_projector", "render_teacher_today")
    checks["projector derives leaderboard locally"] = "_leaderboard_from_status(status" in projector and "store.leaderboard(" not in projector

    mastery = section("render_teacher_mastery_focus", "render_teacher_classes")
    checks["mastery uses one detail dataset"] = "class_mastery_summary" not in mastery and "class_mastery_detail(selected.class_id, students=students)" in mastery
    checks["manual focus controls truly lazy"] = 'st.checkbox("Show advanced fact map & class-wide Focus controls"' in mastery and "if show_advanced:" in mastery

    practice = section("render_practice", "teacher_login")
    checks["practice lifetime summary query removed"] = "practice_summary(" not in practice
    checks["focus practice uses local queue"] = "practice_focus_queue" in practice and "queue.pop(0)" in practice
    checks["focus profile reload only when queue empty"] = "if not queue:" in practice and "store.get_mastery" in practice

    header = section("render_header", "render_db_setup_message")
    checks["student nav is Today and Practice"] = '["Today", "Practice"]' in header
    checks["teacher access is secondary button"] = 'st.button("🔒 Teacher"' in header
    checks["three-way student teacher radio removed"] = '["Daily Challenge", "Practice", "Teacher"]' not in header

    routine = section("render_routine_strip", "render_array")
    checks["mystery is reward not step four"] = '"mystery": "Mystery Reward"' in routine
    daily = section("render_daily", "reset_practice_question")
    checks["daily directions shortened"] = "Fact 1 is untimed." in daily and "hidden timer starts" in daily
    checks["old long timer paragraph removed"] = "The clock starts the instant you submit Fact 1" not in daily
    checks["student technology wording simplified"] = "If something goes wrong, show your teacher." in daily

    complete = section("render_day_complete", "_is_transient_classroom_error")
    checks["growth data is lazy"] = 'st.toggle("🌱 See My Growth"' in complete and "if show_growth:" in complete
    checks["growth mastery query not unconditional"] = complete.index("if show_growth:") < complete.index("render_mastery_card(store)")

    focus = section("render_focus_practice", "render_mastery_card")
    checks["focus wording is kid friendly"] = "8 facts picked just for you." in focus and "8 short retrievals" not in focus
    checks["technical focus save errors removed"] = all(x not in focus for x in [
        "did not finish cleanly", "could not verify the first attempt", "duplicated a first attempt"
    ])

    checks["store accepts preloaded students for status"] = "def daily_status(" in STORE and "students: Sequence[StudentRecord] | None = None" in STORE
    checks["store accepts preloaded students for mastery"] = "def class_mastery_detail(" in STORE and "students = list(students) if students is not None" in STORE
    checks["store accepts preloaded students for learning"] = "def class_learning_stats(" in STORE and "def class_learning_progress(" in STORE

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.9.3 performance + student clarity regression: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
