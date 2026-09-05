from pathlib import Path

from fact_engine import APP_VERSION, Fact
from fact_store import InMemoryFactStore
from weekly_mystery import MYSTERIES, learning_paragraph_for

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
STORE = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
GUIDED = (ROOT / "guided_practice_component" / "index.html").read_text(encoding="utf-8")
SQL = (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_6.sql").read_text(encoding="utf-8")


def run():
    checks = {}
    checks["version 2.6"] = APP_VERSION == "2.19.7"
    checks["guided component declared"] = "GUIDED_PRACTICE_COMPONENT" in APP and "guided_practice_component" in APP
    checks["fix uses guided component"] = 'mode="fix"' in APP and 'step_label="Step 2 · Fix Your Misses"' in APP
    checks["focus uses guided component"] = 'mode="focus"' in APP and 'step_label="Step 3 · Your Focus Practice"' in APP
    checks["one batch save path"] = "def record_practice_batch(" in STORE and ".upsert(payloads, on_conflict=\"client_event_id\")" in STORE
    checks["migration adds event id"] = "client_event_id" in SQL and "practice_client_event_id_unique" in SQL
    checks["component stores local session"] = "sessionStorage.setItem" in GUIDED and "sessionStorage.getItem" in GUIDED
    checks["component keeps array teaching"] = "coachArrayMarkup" in GUIDED and "coach-cell" in GUIDED
    checks["component keeps strategy teaching"] = "SEE IT · CONNECT IT · SOLVE IT" in GUIDED.upper() and "relationship" in GUIDED
    checks["component requires correct retry"] = "if (correct)" in GUIDED and "phase='coach'" in GUIDED and "phase='retry'" in GUIDED
    checks["component records response time"] = "response_seconds" in GUIDED and "itemStartedAt" in GUIDED
    checks["component submits only at session end"] = "function submitSession()" in GUIDED and "setValue({submitted:true" in GUIDED
    # The only setComponentValue transport is the helper; answer taps never call it directly.
    answer_slice = GUIDED[GUIDED.index("function submitAnswer()"):GUIDED.index("function submitSession()")]
    checks["answer submit stays browser local"] = "setValue(" not in answer_slice
    checks["dynamic component sizing"] = "ResizeObserver" in GUIDED and "document.documentElement.scrollHeight" in GUIDED
    checks["physical keyboard supported"] = "document.addEventListener('keydown'" in GUIDED

    # Teacher evidence/data integrity: one first try plus retry rows, all item-level.
    store = InMemoryFactStore()
    classroom = store.create_class("Block 1")
    student = store.create_student(classroom.class_id, "TestFox", "1234")
    events = [
        {"client_event_id":"evt-1", "activity_index":0, "a":7, "b":8, "student_answer":54, "response_seconds":3.2, "is_retry":False},
        {"client_event_id":"evt-2", "activity_index":0, "a":7, "b":8, "student_answer":56, "response_seconds":2.1, "is_retry":True},
        {"client_event_id":"evt-3", "activity_index":1, "a":6, "b":7, "student_answer":42, "response_seconds":1.8, "is_retry":False},
    ]
    saved = store.record_practice_batch(student.student_id, "My Focus Facts", "challenge-1", "focus", events)
    rows = store.learning_activity_rows(student.student_id, "challenge-1", "focus")
    checks["batch preserves all teacher evidence"] = len(saved) == 3 and len(rows) == 3
    checks["first miss stays wrong"] = rows[0].student_answer == 54 and not rows[0].correct and not rows[0].is_retry
    checks["corrected retry stays teaching evidence"] = rows[1].student_answer == 56 and rows[1].correct and rows[1].is_retry
    checks["response timing preserved"] = abs((rows[2].response_seconds or 0) - 1.8) < 1e-9
    replay = store.record_practice_batch(student.student_id, "My Focus Facts", "challenge-1", "focus", events)
    checks["batch replay idempotent"] = replay == [] and len(store.learning_activity_rows(student.student_id, "challenge-1", "focus")) == 3

    # User-requested Lincoln wording is exact.
    lincoln = next(m for m in MYSTERIES if m.key == "abraham-lincoln")
    expected = ('Abraham Lincoln was the 16th president of the United States. He was born in a small log cabin on February 12, 1809. '
                'He grew up very poor and went to school for only about one year, but he loved to read books! People called him "Honest Abe" because he was fair and trustworthy.')
    checks["Lincoln paragraph exact"] = learning_paragraph_for(lincoln) == expected

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.6 Guided Practice regression: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
