from datetime import date
from pathlib import Path

from fact_engine import APP_VERSION
from fact_store import FactStoreError, InMemoryFactStore
from warmup import answer_matches, prepare_question

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text()
SCHEMA = (ROOT / "SUPABASE_SCHEMA.sql").read_text()
MIGRATION = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_10.sql").read_text()
SUPABASE = (ROOT / "supabase_fact_store.py").read_text()


def run():
    checks = 0
    assert APP_VERSION == "2.10.0.1"; checks += 1

    # Matching is useful for decimals/fractions without fuzzy grading.
    assert answer_matches("14.40", "14.4"); checks += 1
    assert answer_matches("1/2", "0.5"); checks += 1
    assert answer_matches("  Equivalent  ", "equivalent"); checks += 1
    assert not answer_matches("48", "49"); checks += 1

    q1 = prepare_question(
        slot=1, prompt="3.6 × 4 = ?", question_type="Short answer",
        correct_answer="14.4", standard_code="TEST.STANDARD.1",
    )
    q2 = prepare_question(
        slot=2, prompt="Which expression is equivalent?", question_type="Multiple choice",
        correct_answer="A", standard_code="TEST.STANDARD.2", options=["A", "B", "C"],
    )
    assert q1["teacher_label"] == "Spiral Review" and q2["teacher_label"] == "Yesterday Check"; checks += 1

    store = InMemoryFactStore()
    klass = store.create_class("Block 1")
    student = store.create_student(klass.class_id, "Falcon", "1234")
    test_student = store.create_student(klass.class_id, "🧪 Test Student", "0000", is_test=True)
    day = date(2026, 8, 18)
    warmup = store.save_warmup_set(klass.class_id, day, q1, q2)
    assert store.get_warmup_set(klass.class_id, day) == warmup; checks += 1

    # Sandbox can use the exact same workflow, but does not lock the plan or export by default.
    store.record_warmup_answer(
        warmup_set_id=warmup.warmup_set_id, student_id=test_student.student_id,
        class_id=klass.class_id, warmup_date=day, question_slot=1,
        question_type=q1["question_type"], prompt=q1["prompt"], standard_code=q1["standard_code"],
        standard_description="", student_answer="14.4", correct_answer="14.4", correct=True,
    )
    assert not store.warmup_set_locked(warmup.warmup_set_id); checks += 1
    assert store.list_warmup_answers(day, day) == []; checks += 1
    assert len(store.list_warmup_answers(day, day, include_test=True)) == 1; checks += 1

    # Editing after sandbox testing clears sandbox answers and keeps trial testable.
    warmup2 = store.save_warmup_set(klass.class_id, day, q1, q2)
    assert warmup2.warmup_set_id == warmup.warmup_set_id; checks += 1
    assert store.get_warmup_answers(test_student.student_id, warmup.warmup_set_id) == []; checks += 1

    # Real response locks the exact question set and is retained for standards data.
    store.record_warmup_answer(
        warmup_set_id=warmup.warmup_set_id, student_id=student.student_id,
        class_id=klass.class_id, warmup_date=day, question_slot=1,
        question_type=q1["question_type"], prompt=q1["prompt"], standard_code=q1["standard_code"],
        standard_description="Decimal multiplication", student_answer="14", correct_answer="14.4", correct=False,
    )
    assert store.warmup_set_locked(warmup.warmup_set_id); checks += 1
    try:
        store.save_warmup_set(klass.class_id, day, q1, q2)
    except FactStoreError:
        pass
    else:
        raise AssertionError("Real response should lock the Warm-Up")
    checks += 1

    rows = store.list_warmup_answers(day, day, class_id=klass.class_id)
    assert len(rows) == 1 and rows[0].standard_code == "TEST.STANDARD.1" and not rows[0].correct; checks += 1

    # App contract.
    assert "def render_quick_warmup" in APP and "2 questions before today's challenge · untimed" in APP; checks += 1
    assert APP.index("if not render_quick_warmup(store, day):") < APP.index("day, facts, challenge = ensure_today(store)"); checks += 1
    assert '"🧠 Warm-Up"' in APP and "def render_teacher_warmup" in APP; checks += 1
    assert "Download weekly Warm-Up CSV" in APP and "Indiana Standard" in APP; checks += 1
    assert "Testing tonight?" in APP and "🧪 Test Student" in APP; checks += 1
    assert "Warm-Up accuracy is stored separately from multiplication mastery and Top 10" in APP; checks += 1

    # Schema/security contract.
    for text in (SCHEMA, MIGRATION):
        assert "create table if not exists public.warmup_sets" in text; checks += 1
        assert "create table if not exists public.warmup_answers" in text; checks += 1
        assert "alter table public.warmup_sets enable row level security" in text; checks += 1
        assert "alter table public.warmup_answers enable row level security" in text; checks += 1
    assert 'self.client.table("warmup_sets")' in SUPABASE and 'self.client.table("warmup_answers")' in SUPABASE; checks += 1

    print(f"v2.10 Quick Warm-Up trial: PASS ({checks} checks)")


if __name__ == "__main__":
    run()
