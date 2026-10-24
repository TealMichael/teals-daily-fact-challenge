"""Standards history reads using the caller's already-loaded non-test roster."""

from datetime import timedelta

from teacher_read_store import TeacherReadStore


def standard_rows(store, method, start, end, *, class_id, students):
    ids = {str(student.student_id) for student in students if not getattr(student, "is_test", False)}
    if not ids or start > end:
        return []
    kwargs = {"class_id": class_id}
    if method != "list_weekly_quiz_sets":
        # The fresh roster below is the authoritative filter. Avoid another
        # database request just to find test accounts among these answers.
        kwargs["include_test"] = True
    rows = []
    live_start = start
    if isinstance(store, TeacherReadStore) and start < store._today:
        past_end = min(end, store._today - timedelta(days=1))
        rows = store.prior_evidence(method, start, past_end, class_id=class_id, roster_ids=ids)
        live_start = past_end + timedelta(days=1)
    if live_start <= end:
        rows += getattr(store, method)(live_start, end, **kwargs)
    if method == "list_weekly_quiz_sets":
        return rows
    return [row for row in rows if str(row.student_id) in ids and str(row.class_id) == str(class_id)]
