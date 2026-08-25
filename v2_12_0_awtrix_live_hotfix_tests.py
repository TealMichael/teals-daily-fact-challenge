from pathlib import Path

ROOT = Path(__file__).resolve().parent
SQL = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_12.sql").read_text(encoding="utf-8").lower()
SCHEMA = (ROOT / "SUPABASE_SCHEMA.sql").read_text(encoding="utf-8").lower()
HOTFIX_SQL = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_12_HOTFIX1.sql").read_text(encoding="utf-8").lower()
CLOCK_UI = (ROOT / "teacher_clock_ui.py").read_text(encoding="utf-8")
SCRIPT = (ROOT / "AWTRIX_FactTop10.berry").read_text(encoding="utf-8")


def _function_header_has_extensions(text: str, signature: str) -> bool:
    start = text.find(f"create or replace function {signature}")
    if start < 0:
        return False
    end = text.find("as $$", start)
    if end < 0:
        return False
    return "set search_path = public, extensions, pg_temp" in text[start:end]


def run():
    checks = {}
    for source_name, text in (("migration", SQL), ("schema", SCHEMA)):
        checks[f"{source_name} top10 pgcrypto path"] = _function_header_has_extensions(text, "public.awtrix_top10(p_block integer)")
        checks[f"{source_name} poll pgcrypto path"] = _function_header_has_extensions(text, "public.awtrix_poll(p_after_id bigint default 0)")

    checks["payload helper remains narrow"] = _function_header_has_extensions(SQL, "public.awtrix_top10_payload_for_block(p_block integer)") is False
    checks["standalone hotfix alters top10"] = "alter function public.awtrix_top10(integer)" in HOTFIX_SQL and "public, extensions, pg_temp" in HOTFIX_SQL
    checks["standalone hotfix alters poll"] = "alter function public.awtrix_poll(bigint)" in HOTFIX_SQL and HOTFIX_SQL.count("public, extensions, pg_temp") >= 2
    checks["mapping flash state set"] = 'st.session_state["awtrix_mapping_saved"] = True' in CLOCK_UI
    checks["mapping flash shown after rerun"] = 'st.session_state.pop("awtrix_mapping_saved", False)' in CLOCK_UI
    checks["mapping success copy"] = 'st.success("Clock class mapping saved.")' in CLOCK_UI

    # Re-lock the exact live automatic windows while touching the integration.
    checks["MonThu Block1 auto"] = "now >= 635 && now < 640" in SCRIPT
    checks["MonThu Block2 auto"] = "now >= 785 && now < 790" in SCRIPT
    checks["MonThu Block3 auto"] = "now >= 925 && now < 930" in SCRIPT
    checks["Friday Block1 auto"] = "now >= 625 && now < 630" in SCRIPT
    checks["Friday Block2 auto"] = "now >= 775 && now < 780" in SCRIPT
    checks["Friday Block3 auto"] = "now >= 900 && now < 905" in SCRIPT
    checks["auto repeats twice"] = '"repeat":2' in SCRIPT
    checks["auto queues behind schedule"] = '"stack":true' in SCRIPT

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2_12_0_awtrix_live_hotfix_tests: PASS ({len(checks)}/{len(checks)})")


if __name__ == "__main__":
    run()
