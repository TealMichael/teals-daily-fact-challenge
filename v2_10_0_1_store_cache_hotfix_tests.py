from pathlib import Path
from fact_engine import APP_VERSION

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
SUPABASE = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
TODAY = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")

checks = {
    "version bumped": APP_VERSION == "2.14.3",
    "store cache takes app version": "def load_store(app_version: str)" in APP,
    "store cache called with current version": "store = load_store(APP_VERSION)" in APP,
    "stale store interface is detected": 'required = ("get_warmup_set", "get_warmup_answers", "list_warmup_answers")' in APP,
    "stale store cache clears itself": "if not all(hasattr(store, name) for name in required):" in APP and "load_store.clear()" in APP,
    "supabase warmup method exists": "def get_warmup_set(" in SUPABASE,
    "supabase answer method exists": "def get_warmup_answers(" in SUPABASE,
    "teacher today isolates warmup failure": "warmup_error = None" in TODAY and "The rest of Today is still available" in TODAY,
    "refresh callback still clears store": "def _request_teacher_refresh()" in APP and "load_store.clear()" in APP,
}
failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
if failed:
    raise AssertionError("Failed: " + ", ".join(failed))
print(f"v2.10.0.1 store-cache hotfix: {len(checks)}/{len(checks)} checks passed")
