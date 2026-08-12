import ast
from pathlib import Path


def run():
    py_files = [path for path in Path(".").glob("*.py")]
    for path in py_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    required = [
        "app.py",
        "fact_engine.py",
        "fact_store.py",
        "supabase_fact_store.py",
        "SUPABASE_SCHEMA.sql",
        "requirements.txt",
        "README.md",
        "DEPLOYMENT_STEPS.txt",
        "daily_sprint_component/index.html",
    ]
    for name in required:
        assert Path(name).exists(), name
    print(f"package_smoke_tests: PASS ({len(py_files)} Python files parsed; {len(required)} required app files)")


if __name__ == "__main__":
    run()
