from __future__ import annotations

"""Teacher Mystery raffle data helpers.

v2.20 batches the saved-winner app_settings reads so a four-class raffle does
not perform one settings request per class on every render.
"""


def mystery_raffle_setting_key(week_start, class_id: str) -> str:
    return f"weekly_mystery_raffle::{week_start.isoformat()}::{class_id}"


def mystery_raffle_snapshot(store, week_start) -> dict:
    """Load eligible solvers, classes, and all saved raffle winners once."""
    eligible = store.weekly_mystery_correct_students(week_start)
    classes = store.list_classes()
    eligible_by_class = {}
    for item in eligible:
        eligible_by_class.setdefault(str(item.get("class_id") or ""), []).append(item)
    keys = [
        mystery_raffle_setting_key(week_start, str(class_record.class_id))
        for class_record in classes
    ]
    bulk_reader = getattr(store, "get_app_settings", None)
    if callable(bulk_reader):
        saved_values = bulk_reader(keys)
    else:
        saved_values = {}
        for key in keys:
            value = store.get_app_setting(key)
            if value is not None:
                saved_values[key] = value
    saved_by_class = {
        str(class_record.class_id): saved_values.get(
            mystery_raffle_setting_key(week_start, str(class_record.class_id))
        )
        for class_record in classes
    }
    return {
        "classes": classes,
        "eligible_by_class": eligible_by_class,
        "saved_by_class": saved_by_class,
    }


def mystery_raffle_has_pending_draw(store, week_start, *, snapshot: dict | None = None) -> bool:
    """Return True when a class has eligible solvers but no valid saved winner."""
    try:
        snapshot = snapshot or mystery_raffle_snapshot(store, week_start)
    except Exception:
        return False

    for class_record in snapshot.get("classes", []):
        class_id = str(class_record.class_id)
        pool = list(snapshot.get("eligible_by_class", {}).get(class_id, []))
        if not pool:
            continue
        saved = snapshot.get("saved_by_class", {}).get(class_id)
        eligible_ids = {str(item.get("student_id") or "") for item in pool}
        winner_is_valid = isinstance(saved, dict) and str(saved.get("student_id") or "") in eligible_ids
        if not winner_is_valid:
            return True
    return False


def mystery_raffle_saved_winners(store, week_start, *, snapshot: dict | None = None) -> list[dict]:
    """Return saved raffle results for active classes, even after every draw is complete."""
    try:
        snapshot = snapshot or mystery_raffle_snapshot(store, week_start)
    except Exception:
        return []
    results = []
    for class_record in snapshot.get("classes", []):
        class_id = str(class_record.class_id)
        saved = snapshot.get("saved_by_class", {}).get(class_id)
        if not isinstance(saved, dict) or not str(saved.get("student_id") or ""):
            continue
        result = dict(saved)
        result.setdefault("class_id", class_id)
        result.setdefault("class_name", class_record.class_name)
        results.append(result)
    return results


def mystery_raffle_has_saved_winner(store, week_start, *, snapshot: dict | None = None) -> bool:
    return bool(mystery_raffle_saved_winners(store, week_start, snapshot=snapshot))
