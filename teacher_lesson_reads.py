"""Batch the read-only Today/Results assignment lookup, with per-class fallback."""

from supabase_fact_store import SupabaseFactStore, _retry_transient, _rows, _warmup_set, _weekly_quiz_set
from teacher_read_store import TeacherReadStore
from weekly_quiz import quiz_is_friday


def _assignments(store, ids, day, *, quiz):
    source = store._source if isinstance(store, TeacherReadStore) else store
    method = store.get_weekly_quiz_set if quiz else store.get_warmup_set
    if len(ids) > 1 and isinstance(source, SupabaseFactStore):
        table, day_column, convert = ("weekly_quiz_sets", "quiz_date", _weekly_quiz_set) if quiz else (
            "warmup_sets", "warmup_date", _warmup_set)
        try:
            rows = []
            for start in range(0, len(ids), 100):
                batch = ids[start:start + 100]
                response = _retry_transient(lambda: source.client.table(table).select("*")
                                           .in_("class_id", batch).eq(day_column, day.isoformat()).execute())
                rows.extend(_rows(response))
            return {str(row["class_id"]): convert(row) for row in rows}, set()
        except Exception:
            # A failed batch is not evidence that no activity exists. Retry the
            # proven per-class path so unaffected class cards remain usable.
            pass
    found, errors = {}, set()
    for cid in ids:
        try:
            item = method(cid, day)
            if item is not None:
                found[cid] = item
        except Exception:
            errors.add(cid)
    return found, errors


def lesson_assignments(store, day, class_ids):
    ids = list(dict.fromkeys(str(cid) for cid in class_ids))
    found, errors = {}, set()
    if quiz_is_friday(day):
        quizzes, errors = _assignments(store, ids, day, quiz=True)
        found = {cid: ("Quiz", item) for cid, item in quizzes.items()}
    remaining = [cid for cid in ids if cid not in found and cid not in errors]
    warmups, warmup_errors = _assignments(store, remaining, day, quiz=False)
    found.update({cid: ("Igniter", item) for cid, item in warmups.items()})
    return found, errors | warmup_errors
