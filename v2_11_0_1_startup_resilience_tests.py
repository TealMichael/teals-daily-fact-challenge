from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text()
STORE = (ROOT / "supabase_fact_store.py").read_text()
ENGINE = (ROOT / "fact_engine.py").read_text()
REQ = (ROOT / "requirements.txt").read_text()

checks = {}
checks["version bumped"] = 'APP_VERSION = "2.13.0"' in ENGINE
checks["challenge version unchanged"] = 'CHALLENGE_VERSION = "TDFC-DAILY-v1"' in ENGINE

# Visible shell must be emitted before database/bootstrap work.
bottom = APP[APP.rfind("# Render the visible shell before any database-dependent startup work."):]
checks["header before store"] = bottom.index("mode = render_header()") < bottom.index("store = _timed_app_call")
checks["header before remembered login"] = bottom.index("mode = render_header()") < bottom.index('"remembered_login"')
checks["teacher skips remembered login"] = 'if mode != "Teacher":' in bottom

# Remembered login should be one lightweight student+class read, not whole-class loading.
checks["single login context method"] = "def get_student_login_context" in STORE
login_handler = APP[APP.index("def handle_persistent_student_login"):APP.index("def student_signed_in")]
checks["handler uses login context"] = "store.get_student_login_context(student_id)" in login_handler
checks["handler no class list"] = "store.list_classes()" not in login_handler
checks["embedded class read"] = 'classes(class_id,class_name,class_code,active,created_at)' in STORE

# Network failure must not destroy a still-valid browser token.
checks["transient restore preserved"] = "if _is_transient_classroom_error(exc):" in login_handler
transient_branch = login_handler[login_handler.index("if _is_transient_classroom_error(exc):"):]
checks["transient branch does not clear token"] = 'persistent_login_pending_action = {"action": "clear"}' not in transient_branch.split("st.session_state.persistent_login_restore_error = None", 1)[0]
checks["manual retry visible"] = 'Try saved sign-in again' in APP

# Bound network waits with a safe compatibility fallback.
checks["postgrest timeout"] = "POSTGREST_TIMEOUT_SECONDS = 12" in STORE
checks["client options"] = "postgrest_client_timeout=POSTGREST_TIMEOUT_SECONDS" in STORE
checks["client options fallback"] = "return create_client(url, key)" in STORE
checks["hard timeouts capped to one retry"] = "if isinstance(exc, timeout_types) and attempt >= 1" in STORE
checks["privacy safe slow timing"] = 'print(f"[TDFC timing] {label}: {elapsed:.2f}s", flush=True)' in APP

# Freeze dependency lines used for the resilience experiment. 2.28.3 predates
# supabase-py's automatic PostgREST retry layer, avoiding stacked retries with
# this app's existing short classroom retry helper.
checks["streamlit pinned"] = "streamlit==1.61.1" in REQ
checks["supabase pinned"] = "supabase==2.28.3" in REQ

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError("Failed resilience checks: " + ", ".join(failed))
print(f"v2.11.2 startup resilience regression: PASS ({len(checks)}/{len(checks)})")
