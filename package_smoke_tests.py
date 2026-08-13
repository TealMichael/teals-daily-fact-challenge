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
        "fact_store.py",
        "supabase_fact_store.py",
        "SUPABASE_SCHEMA.sql",
        "RUN_THIS_ONCE_IN_SUPABASE_v2.sql",
        "RUN_THIS_ONCE_IN_SUPABASE_v2_1.sql",
        "RUN_THIS_ONCE_IN_SUPABASE_v2_2.sql",
        "weekly_mystery.py",
        "daily_sprint_component/index.html",
        "requirements.txt",
        "README.md",
        "DEPLOYMENT_STEPS.txt",
    ]
    for name in required:
        assert Path(name).exists(), name
    print(f"package_smoke_tests: PASS ({len(py_files)} Python files parsed; {len(required)} required app files)")


if __name__ == "__main__":
    run()
