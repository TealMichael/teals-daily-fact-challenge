from pathlib import Path

from fact_engine import APP_VERSION
from fact_store import InMemoryFactStore, FactStoreError

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TODAY_UI = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")
CLOCK_UI = (ROOT / "teacher_clock_ui.py").read_text(encoding="utf-8")
SQL = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_12.sql").read_text(encoding="utf-8")
SCRIPT = (ROOT / "AWTRIX_FactTop10.berry").read_text(encoding="utf-8")
GUARD = (ROOT / "release_guard.py").read_text(encoding="utf-8")


def run():
    checks = {}

    checks["release version"] = APP_VERSION == "2.14.0"
    checks["teacher clock section"] = '"🖥️ Clock"' in APP and "render_teacher_clock(store)" in APP
    checks["manual Today button"] = '📟 Send Top 10 to Clock Now' in TODAY_UI
    checks["manual queue is class-mapped"] = "queue_clock_top10_for_class(store, selected.class_id)" in TODAY_UI
    checks["teacher UI protects secret key"] = "SUPABASE_SECRET_KEY" not in CLOCK_UI
    checks["teacher UI accepts public key only"] = "SUPABASE_PUBLISHABLE_KEY" in CLOCK_UI and "SUPABASE_ANON_KEY" in CLOCK_UI
    checks["mapping confirmation survives rerun"] = "awtrix_mapping_saved" in CLOCK_UI and 'st.session_state["awtrix_mapping_saved"] = True' in CLOCK_UI

    # SQL security boundary: the underlying tables stay private; only the two
    # narrow RPCs are granted to anonymous/public-key callers.
    checks["clock config RLS"] = "alter table public.awtrix_clock_config enable row level security" in SQL.lower()
    checks["clock commands RLS"] = "alter table public.awtrix_clock_commands enable row level security" in SQL.lower()
    checks["no table browser policy"] = "create policy" not in SQL.lower()
    checks["separate token header"] = "x-awtrix-token" in SQL.lower()
    checks["token stored hashed"] = "digest(v_token, 'sha256')" in SQL.lower() and "token_hash" in SQL.lower()
    checks["pgcrypto visible to clock auth RPCs"] = SQL.lower().count("set search_path = public, extensions, pg_temp") >= 2
    checks["only public RPCs granted"] = (
        "grant execute on function public.awtrix_top10(integer) to anon, authenticated" in SQL.lower()
        and "grant execute on function public.awtrix_poll(bigint) to anon, authenticated" in SQL.lower()
        and "revoke all on function public.awtrix_top10_payload_for_block(integer) from anon" in SQL.lower()
    )
    checks["ranking remains accuracy first"] = (
        "order by da.correct_count desc, da.timed_seconds asc, da.completed_at asc" in SQL.lower()
    )
    checks["test students excluded"] = "coalesce(s.is_test, false) = false" in SQL.lower()
    checks["clock payload is rank nickname text"] = "'#' || rank::text || ' ' || nickname" in SQL
    checks["clock payload does not return scores"] = "'correct_count'" not in SQL and "'timed_seconds'" not in SQL

    # AWTRIX script keeps existing schedule script independent, uses HTTPS pull,
    # repeats the full string twice, and contains the exact last-five-minute windows.
    checks["headless clock script"] = "# @headless true" in SCRIPT
    checks["public key config"] = "apiKey" in SCRIPT and "Supabase publishable key" in SCRIPT
    checks["revocable token config"] = "clockToken" in SCRIPT
    checks["outbound HTTPS poll"] = "/rpc/awtrix_poll" in SCRIPT and "/rpc/awtrix_top10" in SCRIPT
    checks["full leaderboard repeats twice"] = '"repeat":2' in SCRIPT
    checks["queues behind schedule banners"] = '"stack":true' in SCRIPT
    checks["Mon-Thu Block 1 last five"] = "now >= 635 && now < 640" in SCRIPT
    checks["Mon-Thu Block 2 last five"] = "now >= 785 && now < 790" in SCRIPT
    checks["Mon-Thu Block 3 last five"] = "now >= 925 && now < 930" in SCRIPT
    checks["Friday Block 1 last five"] = "now >= 625 && now < 630" in SCRIPT
    checks["Friday Block 2 last five"] = "now >= 775 && now < 780" in SCRIPT
    checks["Friday Block 3 last five"] = "now >= 900 && now < 905" in SCRIPT
    checks["script never contains server secret"] = "SUPABASE_SECRET_KEY" not in SCRIPT and "sb_secret_" not in SCRIPT
    checks["release guard includes AWTRIX suite"] = '"v2_12_0_awtrix_top10_tests.py"' in GUARD

    # Reference-backend behavior protects the mapping/token/queue contract.
    store = InMemoryFactStore()
    classes = [store.create_class(name) for name in ("Block One", "Block Two", "Block Three")]
    store.save_awtrix_clock_mapping(*(item.class_id for item in classes))
    cfg = store.get_awtrix_clock_config()
    checks["reference mapping"] = [cfg[f"block{i}_class_id"] for i in (1, 2, 3)] == [item.class_id for item in classes]
    token = store.rotate_awtrix_clock_token()
    cfg = store.get_awtrix_clock_config()
    checks["reference token is one-way"] = bool(token) and cfg["has_token"] and "token_hash" not in cfg and cfg["token_hint"] == token[-6:]
    checks["reference class resolves block"] = store.awtrix_block_for_class(classes[1].class_id) == 2
    checks["reference manual queue"] = store.queue_awtrix_top10(2) == 1 and store.awtrix_clock_commands[-1]["block_number"] == 2
    try:
        store.save_awtrix_clock_mapping(classes[0].class_id, classes[0].class_id, classes[2].class_id)
        duplicate_rejected = False
    except ValueError:
        duplicate_rejected = True
    checks["duplicate class mapping rejected"] = duplicate_rejected

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2_12_0_awtrix_top10_tests: PASS ({len(checks)}/{len(checks)})")


if __name__ == "__main__":
    run()
