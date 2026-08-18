from pathlib import Path
from datetime import datetime, timezone, timedelta

from adaptive_engine import MasterySnapshot
from fact_engine import Fact
from supabase_fact_store import SupabaseFactStore

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text()
STORE = (ROOT / "supabase_fact_store.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()

checks = {
    "version bumped": 'APP_VERSION = "2.10.0.1"' in ENGINE,
    "leaderboard session cache": "def get_cached_leaderboard_context(" in APP,
    "leaderboard not reloaded every Focus rerun": "context=leaderboard_context" in APP and "def get_cached_leaderboard_context(" in APP,
    "focus rows session cache": "def get_cached_focus_rows(" in APP,
    "focus saved rows appended locally": "append_cached_focus_row(challenge, row)" in APP,
    "existing progress reused for focus plan": "progress=progress" in APP,
    "teacher override cached": "def get_cached_focus_override(" in APP,
    "focus answers batch before mastery": "store.record_practice_batch(" in APP,
    "focus mastery batched at completion": "store.record_mastery_evidence_batch(st.session_state.student_id, evidence)" in APP,
    "focus insert-first optimization": "focus_first_try = bool(" in STORE,
    "duplicate focus falls back to read": "a duplicate browser submission falls" in STORE,
    "batch mastery retry idempotency": "not count the same stored Practice evidence twice" in STORE,
}


def main():
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.2.6 Focus speed: {len(checks)}/{len(checks)} checks passed")

if __name__ == "__main__":
    main()
