import ast
from pathlib import Path


def run():
    py_files = [path for path in Path(".").glob("*.py")]
    for path in py_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    required = [
        "app.py",
        "fact_engine.py",
        "adaptive_engine.py",
        "fact_coach.py",
        "fact_store.py",
        "supabase_fact_store.py",
        "SUPABASE_SCHEMA.sql",
        "RUN_THIS_ONCE_IN_SUPABASE_v2.sql",
        "RUN_THIS_ONCE_IN_SUPABASE_v2_1.sql",
        "RUN_THIS_ONCE_IN_SUPABASE_v2_2.sql",
        "RUN_THIS_ONCE_IN_SUPABASE_v2_5.sql",
        "RUN_THIS_ONCE_IN_SUPABASE_v2_10.sql",
        "warmup.py",
        "student_igniter_ui.py",
        "teacher_warmup_ui.py",
        "teacher_learning_ui.py",
        "teacher_intelligence.py",
        "teacher_intelligence_ui.py",
        "teacher_clock_ui.py",
        "AWTRIX_FactTop10.berry",
        "RUN_THIS_ONCE_IN_SUPABASE_v2_12.sql",
        "RUN_THIS_ONCE_IN_SUPABASE_v2_13.sql",
        "daily_modes.py",
        "daily_alt_component/index.html",
        "student_alt_daily_ui.py",
        "teacher_daily_setup_ui.py",
        "teacher_command_center.py",
        "teacher_today_ui.py",
        "ui_helpers.py",
        "STABILITY_CONTRACT.md",
        "release_guard.py",
        "weekly_mystery.py",
        "persistent_login.py",
        "daily_sprint_component/index.html",
        "answer_pad_component/index.html",
        "guided_practice_component/index.html",
        "pin_entry_component/index.html",
        "persistent_login_component/index.html",
        "requirements.txt",
        "README.md",
        "DEPLOYMENT_STEPS.txt",
    ]
    for name in required:
        assert Path(name).exists(), name
    print(f"package_smoke_tests: PASS ({len(py_files)} Python files parsed; {len(required)} required app files)")


if __name__ == "__main__":
    run()
