from pathlib import Path

from fact_store import hash_pin


def run():
    schema = Path("SUPABASE_SCHEMA.sql").read_text(encoding="utf-8").lower()
    backend = Path("supabase_fact_store.py").read_text(encoding="utf-8")
    tables = ["classes", "students", "daily_challenges", "daily_attempts", "daily_answers", "practice_answers"]
    for table in tables:
        assert f"alter table public.{table} enable row level security" in schema
    assert "create policy" not in schema
    assert "unique (student_id, challenge_id)" in schema
    assert "unique (attempt_id, question_number)" in schema
    assert "unique (class_id, nickname_key)" in schema
    assert "correct_answer = a * b" in schema
    assert "correct = (student_answer = correct_answer)" in schema

    encoded = hash_pin("2468")
    assert "2468" not in encoded and encoded.startswith("scrypt$")
    assert "def normalize_supabase_url" in backend and '"/rest/v1"' in backend
    assert "SUPABASE_SECRET_KEY" in backend

    print(f"security_schema_tests: PASS ({len(tables) + 8} security/data-integrity checks)")


if __name__ == "__main__":
    run()
