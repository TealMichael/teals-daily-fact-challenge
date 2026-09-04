from pathlib import Path

from fact_engine import APP_VERSION

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
STORE = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
LEARNING_UI = (ROOT / "teacher_learning_ui.py").read_text(encoding="utf-8")
TODAY_UI = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")


def section(name: str, next_name: str | None = None, source: str = APP) -> str:
    start = source.index(f"def {name}")
    end = source.index(f"\ndef {next_name}", start) if next_name else len(source)
    return source[start:end]


def run():
    checks = {}
    checks["version 2.9.3"] = APP_VERSION == "2.19.3"

    teacher = section("render_teacher", "maybe_render_db_diagnostic")
    checks["teacher dashboard is lazy"] = "st.tabs(" not in teacher and 'primary = st.radio(' in teacher
    checks["only chosen teacher section dispatches"] = all(x in teacher for x in [
        'if primary == "📊 Today"', 'elif primary == "🧠 Warm-Up"', 'elif primary == "📈 Learning"',
        'elif primary == "🕵️ Weekly Mystery"', 'manage_section == "👥 Classes & Rosters"',
        'learning_section == "📈 Learning Data"', 'render_teacher_test_student_launcher(store)'
    ])

    today = section("render_teacher_today_command_center", source=TODAY_UI)
    checks["today loads each class roster once"] = "store.list_students(class_record.class_id)" in today and "store.list_students(selected.class_id)" not in today
    checks["today reuses roster in status"] = "students=roster" in today and "store.daily_status" in today
    checks["today reuses selected snapshot in progress"] = "students = list(selected_snapshot.get(\"students\") or [])" in today and "store.class_learning_progress(selected.class_id, challenge.challenge_id, students=students)" in today
    checks["today reuses selected snapshot in streak stats"] = "store.class_learning_stats(selected.class_id, day, students=students)" in today
    checks["today derives leaderboard locally"] = "leaderboard_from_status(present_status" in today and "store.leaderboard(" not in today
    checks["today avoids duplicate completed query"] = "completed_attempts_for_class" not in today

    projector = section("render_teacher_projector", "render_teacher_today")
    checks["projector derives leaderboard locally"] = "_leaderboard_from_status(status" in projector and "store.leaderboard(" not in projector

    mastery = section("render_teacher_mastery_focus", source=LEARNING_UI)
    fluency = section("_render_teacher_fact_fluency", "_render_teacher_standards_tracker", LEARNING_UI)
    checks["learning views are lazy"] = "_render_teacher_fact_fluency(store, selected, students)" in mastery and "_render_teacher_standards_tracker(store, selected, students)" in mastery
    checks["fact fluency uses one detail dataset"] = "class_mastery_summary" not in fluency and fluency.count("class_mastery_detail(selected.class_id, students=students)") == 1
    checks["advanced controls visually collapsed"] = 'with st.expander("⚙️ Detailed Fact Map & Focus Settings", expanded=False):' in fluency

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
    completed = section("render_completed_daily", "render_daily")
    checks["focus wording is kid friendly"] = "8 facts picked just for you." in completed and "8 short retrievals" not in focus
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
