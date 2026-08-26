from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
ENGINE = (ROOT / "fact_engine.py").read_text(encoding="utf-8")

checks = {
    "version bumped": 'APP_VERSION = "2.13.0"' in ENGINE,
    "growth renderer restored": "def render_mastery_card" in APP,
    "growth uses mastery summary": "store.mastery_summary(st.session_state.student_id)" in APP,
    "growth remains optional": 'st.toggle("🌱 See My Growth"' in APP and 'if show_growth:' in APP,
    "transient classifier exists": "def _is_transient_classroom_error" in APP,
    "http read error classified": "httpx.ReadError" in APP,
    "busy copy still exists for real transport errors": "The classroom connection is busy for a moment" in APP,
    "unexpected display copy exists": "unexpected display error" in APP,
    "debug exception remains hidden behind dbcheck": 'st.query_params.get("dbcheck", "0")' in APP,
}

for label, ok in checks.items():
    assert ok, label
print(f"v2.6.1 finished-screen hotfix: {len(checks)}/{len(checks)} checks passed")
