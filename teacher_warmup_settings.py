from __future__ import annotations

"""Small persistence helpers for teacher Warm-Up email settings."""


def warmup_email_setting_key(class_id: str) -> str:
    return f"warmup_email_secondary::{class_id}"


def warmup_email_recipients(store, class_id: str) -> tuple[str, str]:
    primary_key = "warmup_email_primary"
    secondary_key = warmup_email_setting_key(class_id)
    bulk_reader = getattr(store, "get_app_settings", None)
    if callable(bulk_reader):
        values = bulk_reader([primary_key, secondary_key])
        primary = str(values.get(primary_key, "") or "").strip()
        secondary = str(values.get(secondary_key, "") or "").strip()
    else:
        try:
            primary_value = store.get_app_setting(primary_key, "")
            secondary_value = store.get_app_setting(secondary_key, "")
        except TypeError:
            primary_value = store.get_app_setting(primary_key)
            secondary_value = store.get_app_setting(secondary_key)
        primary = str(primary_value or "").strip()
        secondary = str(secondary_value or "").strip()
    return primary, secondary


def save_warmup_email_recipients(store, class_id: str, primary: str, secondary: str) -> None:
    secondary_key = warmup_email_setting_key(class_id)
    bulk_writer = getattr(store, "set_app_settings", None)
    bulk_deleter = getattr(store, "delete_app_settings", None)
    if callable(bulk_writer):
        values = {"warmup_email_primary": primary}
        if secondary:
            values[secondary_key] = secondary
        bulk_writer(values)
        if not secondary:
            if callable(bulk_deleter):
                bulk_deleter([secondary_key])
            else:
                store.delete_app_setting(secondary_key)
        return
    store.set_app_setting("warmup_email_primary", primary)
    if secondary:
        store.set_app_setting(secondary_key, secondary)
    else:
        store.delete_app_setting(secondary_key)
