"""Safely copy one reviewed week to independently published classroom blocks.

No new database RPC is needed: every block retains its own draft, published
assignments, student responses, and per-day lock checks. A cross-block publish
is intentionally *not* atomic, so callers must show individual outcomes.
"""

from copy import deepcopy
from datetime import date
from uuid import uuid4

from fact_engine import current_daily_date
from weekly_planning import content, load_published_week, new_plan, validate_plan


def copy_for_class(source: dict, target_baseline: dict) -> dict:
    """Copy edited questions/settings, never another block's published IDs."""
    result = deepcopy(target_baseline)
    for field in ("grade", "quiz_grade", "standards", "quiz_standards"):
        result[field] = deepcopy(source[field])
    result["days"] = deepcopy(source["days"])
    return result


def _edited_payload(plan: dict) -> tuple:
    # Draft equality deliberately excludes class identity and assignment IDs.
    # Preserve independently edited draft content unless teacher opts in.
    from json import dumps
    return (plan["grade"], plan["quiz_grade"],
            dumps(plan["standards"], sort_keys=True),
            dumps(plan["quiz_standards"], sort_keys=True),
            dumps(plan["days"], sort_keys=True))


def _changed_days(plan: dict) -> list[int]:
    return [i for i, day in enumerate(plan["days"])
            if day.get("enabled", True) and (
                plan["baseline"][i] is None or
                content(day) != {k: v for k, v in plan["baseline"][i].items() if k != "id"})]


def preview_targets(store, repository, source: dict, class_ids: list[str],
                    *, source_revision: int | None = None) -> list[dict]:
    """Read-only preview; fail closed on stale assignments or lock-read errors."""
    if not class_ids or source["class_id"] != class_ids[0] or len(set(class_ids)) != len(class_ids):
        raise ValueError("Choose the editing block first, followed by any additional blocks.")
    validated = validate_plan(source)
    week = date.fromisoformat(validated["week_start"])
    today = current_daily_date()
    results = []
    for class_id in class_ids:
        record = repository.load(class_id, week)
        plan = (deepcopy(validated) if class_id == source["class_id"] else
                copy_for_class(validated, new_plan(store, class_id, week)))
        # The source's in-session draft has already been saved by the sheet.
        revision = record["revision"] if record else 0
        blocks = []
        if class_id == source["class_id"] and source_revision is not None and (
            not record or record["revision"] != source_revision or
            _edited_payload(record["plan"]) != _edited_payload(validated)
        ):
            blocks.append("The editing draft changed in another session. Reload this week before publishing.")
        changes = _changed_days(plan)
        live = load_published_week(store, class_id, week)
        for i in changes:
            day = plan["days"][i]
            if live[i] != plan["baseline"][i]:
                blocks.append(f"{day['date']}: published content changed since this draft was opened")
                continue
            if date.fromisoformat(day["date"]) < today:
                blocks.append(f"{day['date']}: past activities cannot be changed")
                continue
            if live[i] is not None:
                try:
                    locked = (store.warmup_set_locked(live[i]["id"]) if i < 4 else
                              store.weekly_quiz_locked(live[i]["id"]))
                except Exception:
                    blocks.append(f"{day['date']}: could not verify whether students started")
                    continue
                if locked:
                    blocks.append(f"{day['date']}: students have started this assignment")
        # A saved draft in another block belongs to that block, and is never
        # silently overwritten just because that block was checked.
        draft_conflict = bool(class_id != source["class_id"] and changes and record and
                              _edited_payload(record["plan"]) != _edited_payload(plan))
        needs_confirmation = any(live[i] is not None or
                                 plan["days"][i]["date"] == today.isoformat() for i in changes)
        results.append({"class_id": class_id, "plan": plan, "revision": revision,
                        "changes": changes, "blockers": blocks,
                        "draft_conflict": draft_conflict,
                        "needs_confirmation": needs_confirmation})
    return results


def publish_targets(repository, previews: list[dict], *, confirm_replacements: bool,
                    confirm_drafts: bool) -> list[dict]:
    """Publish class-by-class; return explicit partial success if any step fails."""
    if any(item["blockers"] for item in previews):
        raise ValueError("A selected block has locked or changed assignments. Nothing was published.")
    if any(item["draft_conflict"] for item in previews) and not confirm_drafts:
        raise ValueError("Confirm replacing existing saved drafts before publishing.")
    if any(item["needs_confirmation"] for item in previews) and not confirm_replacements:
        raise ValueError("Confirm changes to already published or today's activities.")
    results = []
    for index, item in enumerate(previews):
        class_id = item["class_id"]
        if not item["changes"]:
            results.append({"class_id": class_id, "status": "unchanged", "changed": 0})
            continue
        try:
            # Source is already an autosaved draft. Others are copied only at
            # publication time, after all selections passed read-only checks.
            if index == 0:
                revision = item["revision"]
            else:
                saved = repository.save(item["plan"], item["revision"])
                revision = saved["revision"]
            result = repository.publish(item["plan"], revision, str(uuid4()),
                                        confirm=confirm_replacements)
            results.append({"class_id": class_id, "status": "published",
                            "changed": result["changed"], "draft": result["draft"]})
        except Exception as exc:
            results.append({"class_id": class_id, "status": "failed", "error": str(exc)})
            # If the editing block failed, don't publish its plan elsewhere.
            if index == 0:
                results.extend({"class_id": rest["class_id"], "status": "not_attempted"}
                               for rest in previews[index+1:])
                break
    return results
