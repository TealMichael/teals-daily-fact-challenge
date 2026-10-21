from __future__ import annotations

"""Weekly drafts and atomic publication; reuses the existing question validators.

Production persistence is a small additive RPC boundary. The in-memory backend
models the same contract for classroom regression tests without student data.
"""

from copy import deepcopy
from datetime import date, timedelta
import inspect
import random
from threading import RLock

from fact_engine import current_daily_date
from fact_store import FactStoreError
from indiana_question_bank import editor_question, questions_for_standard
from teacher_planning import monday_for
from warmup import prepare_question
from weekly_quiz import prepare_quiz_question


def assignment_snapshot(record, kind: str):
    if record is None:
        return None
    if kind == "igniter":
        return {"id": record.warmup_set_id,
                "questions": deepcopy([record.question_one, record.question_two])}
    return {"id": record.quiz_id, "questions": deepcopy(list(record.questions)),
            "assignment_name": record.assignment_name, "category_code": record.category_code,
            "max_score": float(record.max_score)}


def load_published_week(store, class_id: str, week: date) -> list:
    week = monday_for(week)
    return [assignment_snapshot(
        store.get_warmup_set(class_id, week + timedelta(days=i)) if i < 4 else
        store.get_weekly_quiz_set(class_id, week + timedelta(days=i)),
        "igniter" if i < 4 else "quiz") for i in range(5)]


def blank_question() -> dict:
    return {"question_type": "Number", "prompt": "", "correct_answer": "", "standard_code": ""}


def new_plan(store, class_id: str, week: date) -> dict:
    week = monday_for(week)
    snapshots = load_published_week(store, class_id, week)
    prior = load_published_week(store, class_id, week - timedelta(days=7))
    # Derive prior instruction from Mon–Thu published Igniters, never from the
    # current week's standards or the previous Friday's already-lagged quiz.
    prior_codes = list(dict.fromkeys(q.get("standard_code", "")
        for entry in prior[:4] if entry for q in entry["questions"] if q.get("standard_code")))
    current_codes = list(dict.fromkeys(q.get("standard_code", "")
        for entry in snapshots[:4] if entry for q in entry["questions"] if q.get("standard_code")))
    days = []
    for i, existing in enumerate(snapshots):
        d = week + timedelta(days=i)
        day = {"date": d.isoformat(), "kind": "igniter" if i < 4 else "quiz",
               "enabled": existing is not None or d >= current_daily_date(),
               "questions": deepcopy(existing["questions"]) if existing else
                            [blank_question() for _ in range(2 if i < 4 else 5)]}
        if i == 4:
            day.update({key: existing[key] for key in ("assignment_name", "category_code", "max_score")}
                       if existing else {"assignment_name": f"Quiz of the Week - {d:%b %d}",
                                         "category_code": "SUMM", "max_score": 5.0})
        days.append(day)
    def inferred_grade(codes):
        return next((int(code[0]) for code in codes if code and code[0] in '567'), 5)
    return {"schema": 1, "class_id": str(class_id), "week_start": week.isoformat(),
            "grade": inferred_grade(current_codes), "quiz_grade": inferred_grade(prior_codes), "standards": current_codes,
            "quiz_standards": prior_codes, "prior_week": (week-timedelta(days=7)).isoformat(),
            "days": days, "baseline": snapshots}


def content(item: dict) -> dict:
    result = {"questions": deepcopy(item["questions"])}
    if item["kind"] == "quiz":
        result.update({key: item[key] for key in ("assignment_name", "category_code", "max_score")})
    return result


def state_label(item: dict, published) -> str:
    if not item.get("enabled", True):
        return "Keep published assignment" if published else "No assignment"
    if published is None:
        return "Draft"
    return "Published" if content(item) == {k: v for k, v in published.items() if k != "id"} else "Modified after publishing"


def question_signature(q: dict) -> tuple:
    # Identify identical content even if copied manually or given another bank ID.
    return (str(q.get("prompt", "")).strip().casefold(), str(q.get("question_type", "")),
            str(q.get("compare_left", "")), str(q.get("compare_right", "")),
            tuple(q.get("order_items") or ()), tuple(q.get("options") or ()),
            str(q.get("image_path", "")), str(q.get("bank_image_path", "")))


def duplicate_slots(plan: dict) -> list[str]:
    seen, duplicates = set(), []
    for item in plan["days"]:
        if not item.get("enabled", True):
            continue
        for slot, question in enumerate(item["questions"], 1):
            if not str(question.get("prompt") or "").strip():
                continue
            signature = question_signature(question)
            if signature in seen:
                duplicates.append(f"{item['date']} · Q{slot}")
            seen.add(signature)
    return duplicates


def suggest_questions(plan: dict, *, replace_drafts: bool = False, rng=None) -> tuple[dict, list[str]]:
    result = deepcopy(plan)
    rng = rng or random.SystemRandom()
    warnings = []
    # Never replace published content as a side effect of generating suggestions.
    seen = {question_signature(q) for i, day in enumerate(result["days"])
            if result["baseline"][i] is not None or not replace_drafts
            for q in day["questions"] if q.get("prompt")}
    for i, day in enumerate(result["days"]):
        if not day.get("enabled", True) or result["baseline"][i] is not None:
            continue
        codes = result["standards"] if i < 4 else result["quiz_standards"]
        if not codes:
            warnings.append("Choose previously taught standards for Friday." if i == 4 else "Choose Igniter standards.")
            continue
        for slot in range(len(day["questions"])):
            if day["questions"][slot].get("prompt") and not replace_drafts:
                continue
            # Rotate standards across the week; fall back to other selected codes
            # when a small bank is exhausted. Never silently duplicate a question.
            start = (i * 2 + slot) % len(codes)
            code_order = codes[start:] + codes[:start]
            candidates = []
            for code in code_order:
                candidates = [editor_question(q) for q in questions_for_standard(code)
                              if question_signature(editor_question(q)) not in seen]
                if candidates:
                    break
            if not candidates:
                warnings.append("Not enough distinct bank questions. Write a question or select another standard.")
                if replace_drafts:
                    day["questions"][slot] = blank_question()
                continue
            chosen = rng.choice(candidates)
            day["questions"][slot] = normalize_question(chosen, day["kind"], slot+1)
            seen.add(question_signature(chosen))
    return result, list(dict.fromkeys(warnings))


def normalize_question(question: dict, kind: str, slot: int) -> dict:
    validator = prepare_question if kind == "igniter" else prepare_quiz_question
    allowed = inspect.signature(validator).parameters
    args = {key: value for key, value in question.items() if key in allowed and key != "slot"}
    return validator(slot=slot, **args)


def validate_plan(plan: dict) -> dict:
    result = deepcopy(plan)
    start = date.fromisoformat(result["week_start"])
    if start.weekday() != 0 or len(result["days"]) != 5 or len(result["baseline"]) != 5:
        raise ValueError("Select an instructional week beginning on Monday.")
    for i, day in enumerate(result["days"]):
        if day["date"] != (start + timedelta(days=i)).isoformat() or day["kind"] != ("igniter" if i < 4 else "quiz"):
            raise ValueError("The plan contains an incorrect activity date.")
        if not day.get("enabled", True):
            continue
        if len(day["questions"]) != (2 if i < 4 else 5):
            raise ValueError("Igniters need two questions; Friday needs five.")
        day["questions"] = [normalize_question(q, day["kind"], slot)
                            for slot, q in enumerate(day["questions"], 1)]
        if i == 4:
            if not 1 <= len(str(day["assignment_name"]).strip()) <= 120:
                raise ValueError("Friday needs an assignment name of 1–120 characters.")
            if day["category_code"] not in ("SUMM", "FORM") or not 0 < float(day["max_score"]) <= 100:
                raise ValueError("Choose SUMM/FORM and a maximum score greater than 0 and at most 100.")
    return result


class SupabasePlanRepository:
    def __init__(self, store):
        self.store = store

    def load(self, class_id, week):
        response = self.store.client.table("weekly_planning_drafts").select("*").eq(
            "class_id", str(class_id)).eq("week_start", str(week)).limit(1).execute()
        return deepcopy(response.data[0]) if response.data else None

    def save(self, plan, expected_revision):
        return self.store.client.rpc("tdfc_save_week_plan", {
            "p_class_id": plan["class_id"], "p_week_start": plan["week_start"],
            "p_expected_revision": expected_revision, "p_plan": plan}).execute().data

    def publish(self, plan, expected_revision, request_id, *, confirm=False):
        validate_plan(plan)
        return self.store.client.rpc("tdfc_publish_week_plan", {
            "p_class_id": plan["class_id"], "p_week_start": plan["week_start"],
            "p_expected_revision": expected_revision, "p_request_id": request_id,
            "p_confirm_replacements": confirm}).execute().data


class InMemoryPlanRepository:
    """Reference backend, never used when a Supabase client is present."""
    def __init__(self, store):
        self.store, self.drafts, self.publications, self.lock = store, {}, {}, RLock()

    def load(self, class_id, week):
        with self.lock:
            return deepcopy(self.drafts.get((str(class_id), str(week))))

    def save(self, plan, expected_revision):
        with self.lock:
            key = (plan["class_id"], plan["week_start"])
            existing = self.drafts.get(key)
            if (existing["revision"] if existing else 0) != expected_revision:
                raise FactStoreError("This draft changed in another session. Reload it before saving.")
            record = {"class_id": key[0], "week_start": key[1], "revision": expected_revision+1, "plan": deepcopy(plan)}
            self.drafts[key] = record
            return deepcopy(record)

    def publish(self, plan, expected_revision, request_id, *, confirm=False):
        with self.lock:
            if request_id in self.publications:
                pub = self.publications[request_id]
                if (pub["class_id"], pub["week_start"], pub["draft_revision"]) != (
                        plan["class_id"], plan["week_start"], expected_revision):
                    raise FactStoreError("Publication request conflict.")
                return deepcopy(pub["result"])
            key = (plan["class_id"], plan["week_start"])
            draft = self.drafts.get(key)
            if not draft or draft["revision"] != expected_revision:
                raise FactStoreError("This draft changed. Reload before publishing.")
            plan = validate_plan(draft["plan"])
            before = load_published_week(self.store, key[0], date.fromisoformat(key[1]))
            changes = []
            for i, item in enumerate(plan["days"]):
                old = before[i]
                if not item.get("enabled", True) or (old and content(item) == {k: v for k, v in old.items() if k != 'id'}):
                    continue
                if old != plan["baseline"][i]:
                    raise FactStoreError("Published content changed. Reload the published week.")
                day = date.fromisoformat(item["date"])
                if day < current_daily_date():
                    raise FactStoreError("Past assignments cannot be changed in the planner.")
                if (old or day == current_daily_date()) and not confirm:
                    raise FactStoreError("Confirm replacing published content or publishing for today.")
                locked = self.store.warmup_set_locked if i < 4 else self.store.weekly_quiz_locked
                if old and locked(old["id"]):
                    raise FactStoreError("Students have started this assignment. It cannot be replaced.")
                changes.append(i)
            fields = ("warmup_sets", "warmup_answers", "weekly_quiz_sets", "weekly_quiz_answers", "standard_recovery_answers")
            backup = {field: deepcopy(getattr(self.store, field)) for field in fields}
            try:
                for i in changes:
                    item = plan["days"][i]
                    if i < 4:
                        self.store.delete_warmup_set(key[0], item["date"])
                        self.store.save_warmup_set(key[0], item["date"], *item["questions"])
                    else:
                        self.store.delete_weekly_quiz_set(key[0], item["date"])
                        self.store.save_weekly_quiz_set(key[0], item["date"], **content(item))
            except Exception:
                for field, value in backup.items():
                    setattr(self.store, field, value)
                raise
            after = load_published_week(self.store, key[0], date.fromisoformat(key[1]))
            plan["baseline"] = after
            record = {"class_id": key[0], "week_start": key[1], "revision": expected_revision+1, "plan": plan}
            result = {"draft": deepcopy(record), "changed": len(changes), "request_id": request_id}
            self.drafts[key] = record
            self.publications[request_id] = {"class_id": key[0], "week_start": key[1], "draft_revision": expected_revision,
                "before_assignments": before, "after_assignments": after, "result": deepcopy(result)}
            return result


def plan_repository(store):
    if hasattr(store, "client"):
        return SupabasePlanRepository(store)
    if not hasattr(store, "_weekly_plan_repository"):
        store._weekly_plan_repository = InMemoryPlanRepository(store)
    return store._weekly_plan_repository
