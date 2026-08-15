from pathlib import Path
from datetime import datetime, timezone

from adaptive_engine import (
    MasterySnapshot,
    build_focus_plan,
    STATUS_FLUENT,
)
from fact_store import InMemoryFactStore
from fact_coach import coach_plan


def run():
    checks = 0

    # New students learn without a placement test: early unknown exploration
    # deliberately favors the 2s/5s/10s anchor relationships.
    plan = build_focus_plan([], student_id="new-student", date_key="2026-08-13")
    target_positions = [plan[0], plan[1], plan[3]]
    assert all({2, 5, 10} & set(fact.key) for fact in target_positions)
    checks += 1

    # Once anchor relationships are known, unknown derived facts can move up in
    # the exploration order rather than following a rigid table sequence.
    now = datetime.now(timezone.utc)
    anchor_rows = []
    for a in range(2, 11):
        for b in range(a, 11):
            if {2, 5, 10} & {a, b}:
                anchor_rows.append(MasterySnapshot(
                    a=a, b=b, evidence_count=5, correct_count=5,
                    ema_accuracy=0.98, ema_seconds=2.0, correct_streak=5,
                    status=STATUS_FLUENT, last_practiced_at=now,
                ))
    derived_plan = build_focus_plan(anchor_rows, student_id="anchor-ready", date_key="2026-08-13")
    derived_targets = [derived_plan[0], derived_plan[1], derived_plan[3]]
    assert any(not ({2, 5, 10} & set(fact.key)) for fact in derived_targets)
    checks += 1

    # Teacher-visible classroom PINs persist while authentication still checks
    # the hashed PIN internally.
    store = InMemoryFactStore()
    cls = store.create_class("Period 1")
    student = store.create_student(cls.class_id, "Falcon", "2468")
    assert student.pin_code == "2468"
    assert store.list_students(cls.class_id)[0].pin_code == "2468"
    assert store.authenticate_student(cls.class_id, "Falcon", "2468") is not None
    checks += 1

    store.reset_student_pin(student.student_id, "1357")
    refreshed = store.get_student(student.student_id)
    assert refreshed.pin_code == "1357"
    assert store.authenticate_student(cls.class_id, "Falcon", "2468") is None
    assert store.authenticate_student(cls.class_id, "Falcon", "1357") is not None
    checks += 1

    app = Path("app.py").read_text(encoding="utf-8")
    schema = Path("SUPABASE_SCHEMA.sql").read_text(encoding="utf-8")
    migration = Path("RUN_THIS_ONCE_IN_SUPABASE_v2_1.sql").read_text(encoding="utf-8")
    assert "PIN {student.pin_code or 'reset once'}" in app
    assert '"PIN": student.pin_code or "Reset once"' in app
    assert "Generate visible PINs for older accounts" in app
    assert coach_plan(3, 7).strategy_id == "double_plus_one"
    assert "pin_code text" in schema and "pin_code_shape" in schema
    assert "add column if not exists pin_code text" in migration
    checks += 6

    adaptive = Path("adaptive_engine.py").read_text(encoding="utf-8")
    assert "FOUNDATION_FAMILIES = (2, 5, 10)" in adaptive
    assert "_derived_anchor_keys" in adaptive
    assert "relationship-aware growth without a placement test" in adaptive
    checks += 3

    print(f"v2_1_research_pin_tests: PASS ({checks}/13 research-alignment + PIN checks)")


if __name__ == "__main__":
    run()
