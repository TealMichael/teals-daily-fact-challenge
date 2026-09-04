from __future__ import annotations

"""Run the highest-value release checks before packaging a deployment."""

from pathlib import Path
import py_compile
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CRITICAL_SUITES = [
    "package_smoke_tests.py",
    "security_schema_tests.py",
    "store_tests.py",
    "ui_contract_tests.py",
    "component_contract_tests.py",
    "teacher_workflow_tests.py",
    "v2_11_2_foundation_stability_tests.py",
    "v2_11_2_post_daily_flow_cleanup_tests.py",
    "v2_11_2_data_trust_tests.py",
    "v2_11_2_igniter_save_hotfix_tests.py",
    "v2_11_2_teacher_safety_hotfix_tests.py",
    "v2_11_2_teacher_today_api_resilience_tests.py",
    "v2_12_0_classroom_safety_audit_tests.py",
    "v2_13_0_weekly_daily10_igniter_tests.py",
    "v2_13_1_delayed_raffle_dashboard_tests.py",
    "v2_13_2_class_list_readerror_hotfix_tests.py",
    "v2_14_0_teacher_command_center_tests.py",
    "v2_14_1_teacher_followup_polish_tests.py",
    "v2_14_2_raffle_safety_tests.py",
    "v2_14_3_mystery_nav_polish_tests.py",
    "v2_15_0_instructional_intelligence_tests.py",
    "v2_16_0_planning_history_tests.py",
    "v2_16_1_ui_language_polish_tests.py",
    "v2_16_2_mystery_clue_reliability_tests.py",
    "v2_16_3_daily_touch_keypad_hotfix_tests.py",
    "v2_16_4_alternate_today_completion_hotfix_tests.py",
    "v2_17_0_followup_foundation_tests.py",
    "v2_18_0_teaching_models_tests.py",
    "v2_19_0_adaptive_focus_tests.py",
    "v2_19_1_student_morning_reliability_tests.py",
    "v2_19_2_model_rerender_hotfix_tests.py",
    "v2_19_3_component_cache_touch_hotfix_tests.py",
    "v2_19_4_classroom_hardening_tests.py",
    "runtime_name_guard_tests.py",
    "v2_11_2_final_top10_restore_tests.py",
    "v2_12_0_awtrix_top10_tests.py",
    "v2_12_0_awtrix_live_hotfix_tests.py",
    "v2_12_0_awtrix_top10_chime_tests.py",
    "v2_11_0_1_startup_resilience_tests.py",
    "v2_11_0_2_daily_load_resilience_hotfix_tests.py",
    "v2_11_0_3_supabase_2283_compatibility_tests.py",
    "v2_11_afterschool_teacher_data_tests.py",
    "v2_10_warmup_trial_tests.py",
    "v2_9_raffle_typo_test_student_tests.py",
    "v2_classroom_scale_tests.py",
]


def run() -> None:
    py_files = sorted(ROOT.glob("*.py"))
    for path in py_files:
        py_compile.compile(str(path), doraise=True)
    print(f"PASS: compiled {len(py_files)} Python files")

    for suite in CRITICAL_SUITES:
        result = subprocess.run([sys.executable, str(ROOT / suite)], cwd=ROOT)
        if result.returncode:
            raise SystemExit(result.returncode)
    print(f"release_guard: PASS ({len(CRITICAL_SUITES)} critical suites)")


if __name__ == "__main__":
    run()
