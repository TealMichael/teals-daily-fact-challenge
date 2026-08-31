from __future__ import annotations

"""Pure teacher planning helpers for v2.16.

No Streamlit imports and no student-side writes. These helpers only copy or
store teacher planning records that already exist in the app's data model.
"""

from datetime import date, timedelta

from daily_modes import configured_daily_mode, daily_mode_setting_key
from fact_store import FactStoreError

WARMUP_TEMPLATES_KEY = "warmup_templates:v1"


def monday_for(value: date) -> date:
    return value - timedelta(days=value.weekday())


def school_days_for_week(week_start: date) -> list[date]:
    return [week_start + timedelta(days=offset) for offset in range(5)]


def next_school_day(value: date) -> date:
    result = value + timedelta(days=1)
    while result.weekday() >= 5:
        result += timedelta(days=1)
    return result


def previous_school_day(value: date) -> date:
    result = value - timedelta(days=1)
    while result.weekday() >= 5:
        result -= timedelta(days=1)
    return result


def set_daily_mode(store, class_id: str, day: date, mode: str) -> None:
    key = daily_mode_setting_key(day, class_id)
    if mode == "Multiplication":
        store.delete_app_setting(key)
    else:
        store.set_app_setting(key, mode)


def copy_daily_week(store, classes, source_week: date, target_week: date) -> None:
    for class_record in classes:
        for offset in range(5):
            source_day = source_week + timedelta(days=offset)
            target_day = target_week + timedelta(days=offset)
            set_daily_mode(store, class_record.class_id, target_day, configured_daily_mode(store, class_record.class_id, source_day))


def _app_setting(store, key: str, default=None):
    try:
        value = store.get_app_setting(key)
    except TypeError:
        value = store.get_app_setting(key, default)
    return default if value is None else value


def warmup_templates(store) -> list[dict]:
    value = _app_setting(store, WARMUP_TEMPLATES_KEY, [])
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split())
        if not name or not isinstance(item.get("question_one"), dict) or not isinstance(item.get("question_two"), dict):
            continue
        result.append({"name": name[:60], "question_one": dict(item["question_one"]), "question_two": dict(item["question_two"])})
    return result[:20]


def save_warmup_template(store, name: str, question_one: dict, question_two: dict) -> None:
    cleaned = " ".join(str(name or "").split())[:60]
    if not cleaned:
        raise ValueError("Give the template a short name first.")
    templates = [item for item in warmup_templates(store) if item["name"].casefold() != cleaned.casefold()]
    templates.insert(0, {"name": cleaned, "question_one": dict(question_one), "question_two": dict(question_two)})
    store.set_app_setting(WARMUP_TEMPLATES_KEY, templates[:20])


def copy_warmup_set(store, *, source, target_class_id: str, target_date: date) -> None:
    target = store.get_warmup_set(target_class_id, target_date)
    if target is not None and store.warmup_set_locked(target.warmup_set_id):
        raise FactStoreError("That destination Warm-Up is locked because a student already answered it.")
    store.save_warmup_set(target_class_id, target_date, source.question_one, source.question_two)
