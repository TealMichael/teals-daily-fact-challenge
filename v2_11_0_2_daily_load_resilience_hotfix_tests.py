from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text()
STORE = (ROOT / "supabase_fact_store.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()

checks = {}
checks["version bumped"] = 'APP_VERSION = "2.19.0"' in ENGINE
checks["challenge version unchanged"] = 'CHALLENGE_VERSION = "TDFC-DAILY-v1"' in ENGINE
checks["timeout raised to 12"] = "POSTGREST_TIMEOUT_SECONDS = 12" in STORE
checks["storage timeout raised to 12"] = "STORAGE_TIMEOUT_SECONDS = 12" in STORE
checks["hard timeout still one retry"] = "if isinstance(exc, timeout_types) and attempt >= 1" in STORE
checks["daily retry helper exists"] = "def render_daily_load_retry(exc: Exception)" in APP
checks["friendly daily warning"] = "Having trouble reaching today's Daily 10." in APP
checks["preserves sign in and igniter"] = "Your sign-in and any completed Igniter work are safe." in APP
checks["retry button"] = 'st.button("🔄 Try Again"' in APP
checks["daily loader uses retry helper"] = "except Exception as exc:\n        render_daily_load_retry(exc)\n        return" in APP
checks["old dead end removed"] = "Today's challenge could not be loaded. Your teacher can check the hidden database diagnostic if needed." not in APP
checks["private failure logger"] = "def _log_private_connection_failure" in APP
checks["daily failure logged privately"] = '_log_private_connection_failure("daily_load", exc)' in APP
checks["coarse log only"] = '[TDFC connection] {label}: {kind} ({type(exc).__name__})' in APP
checks["timeout classification"] = 'return "timeout"' in APP
checks["dbcheck still available"] = 'if str(st.query_params.get("dbcheck", "0")) == "1":' in APP

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError("Failed v2.11.2 hotfix checks: " + ", ".join(failed))
print(f"v2.11.2 Daily-load resilience hotfix: PASS ({len(checks)}/{len(checks)})")
