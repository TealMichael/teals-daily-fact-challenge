from pathlib import Path

ROOT = Path(__file__).resolve().parent
migration = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_24_2.sql").read_text()
schema = (ROOT / "SUPABASE_SCHEMA.sql").read_text()
fact_engine = (ROOT / "fact_engine.py").read_text()

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

check("release version", 'APP_VERSION = "2.24.2"' in fact_engine)
for table_constraint in (
    "warmup_question_type_allowed",
    "weekly_quiz_type_allowed",
    "standard_recovery_type_allowed",
):
    check(f"migration drops {table_constraint}", f"drop constraint if exists {table_constraint}" in migration)
    check(f"migration adds {table_constraint}", f"add constraint {table_constraint}" in migration)

for question_type in ("Compare Values", "Order Tiles"):
    check(f"migration allows {question_type}", migration.count(f"'{question_type}'") >= 3)
    check(f"schema allows {question_type}", schema.count(f"'{question_type}'") >= 3)

for legacy_type in ("Short answer", "Number", "Fraction", "Multiple choice", "Number + Label", "Expanded Form", "Equivalent Number", "Multi-Part — 2 answers"):
    check(f"warmup preserves {legacy_type}", f"'{legacy_type}'" in migration)

print(f"v2_24_2_interactive_db_constraint_hotfix_tests: PASS ({len(checks)}/{len(checks)})")
