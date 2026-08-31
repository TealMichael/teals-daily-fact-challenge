"""Regression protection for teacher-side helper boundaries and Igniter saves."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
TODAY = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")
WARMUP = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
RELEASE_GUARD = (ROOT / "release_guard.py").read_text(encoding="utf-8")


def _safe_recent_helper():
    tree = ast.parse(WARMUP)
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_remember_warmup_standards_safely"
    ]
    assert len(nodes) == 1
    ns = {"SupabaseFactStore": object}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "recent_standard_helper", "exec"), ns)
    return ns["_remember_warmup_standards_safely"], ns


def run():
    checks = {}

    # The foundation extraction moved these helpers into modules. app.py must import
    # the helpers it still invokes from Teacher Today and Student Support.
    checks["Today Warm-Up groups helper imported"] = "from teacher_warmup_ui import _render_warmup_groups_and_email" in TODAY
    checks["Student Support focus helpers imported"] = (
        "render_teacher_mastery_focus, _override_label, _override_value" in APP
    )
    checks["Today still calls Warm-Up groups"] = "_render_warmup_groups_and_email(" in TODAY
    checks["Student Support still calls focus helpers"] = (
        "_override_label(current_override)" in APP and "_override_value(personal_choice)" in APP
    )

    # Core Igniter saves happen first; recent-standard memory is best effort only.
    save_block_start = WARMUP.index("if save:")
    save_block_end = WARMUP.index("\n    if existing and not locked:", save_block_start)
    save_block = WARMUP[save_block_start:save_block_end]
    checks["core save precedes recent-standard convenience"] = (
        save_block.index("store.save_warmup_set") < save_block.index("_remember_warmup_standards_safely")
    )
    checks["successful save remains success after convenience attempt"] = (
        save_block.index("_remember_warmup_standards_safely") < save_block.index('st.success("Warm-Up saved"')
    )

    # Behavior check: a failure in remembering recent standards is swallowed.
    helper, ns = _safe_recent_helper()
    def boom(store, codes):
        raise RuntimeError("optional setting unavailable")
    ns["_remember_warmup_standards"] = boom
    # Re-exec with the dependency injected because function globals live in ns.
    helper, ns = _safe_recent_helper()
    ns["_remember_warmup_standards"] = boom
    checks["optional recent-standard failure is swallowed"] = helper(object(), ["5.NS.3"]) is False

    # Release guard permanently covers the blind spots found in this audit.
    checks["runtime-name guard is in release guard"] = '"runtime_name_guard_tests.py"' in RELEASE_GUARD
    checks["final Top 10 restore is in release guard"] = '"v2_11_2_final_top10_restore_tests.py"' in RELEASE_GUARD
    checks["teacher safety hotfix is in release guard"] = '"v2_11_2_teacher_safety_hotfix_tests.py"' in RELEASE_GUARD

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2_11_2_teacher_safety_hotfix_tests: PASS ({len(checks)}/{len(checks)})")


if __name__ == "__main__":
    run()
