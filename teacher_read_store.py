from __future__ import annotations

"""Teacher-only read reuse. Never pass this facade to a student workflow.

Metadata lives for one render only. Only explicitly requested, prior-day
standards evidence may survive a rerun, for at most 30 seconds in this session.
Assignments, locks, current answers and mastery snapshots always read through.
"""

from copy import deepcopy
from datetime import date
from functools import wraps
from inspect import signature
from time import monotonic

HISTORY_STATE_KEY = "_teacher_prior_evidence_v2271"
HISTORY_TTL = 30.0
MAX_HISTORY_ENTRIES = 24
MAX_HISTORY_ROWS = 20000

_RENDER_READS = frozenset({
    "list_classes", "list_students", "list_students_for_classes",
    "get_app_setting", "get_app_settings", "get_global_focus_override",
    "get_class_focus_override", "get_student_focus_override",
})
_OTHER_READS = frozenset({
    "class_mastery_detail", "class_mastery_summary", "class_learning_stats",
    "class_learning_progress", "class_alternate_learning_progress",
    "teacher_daily_history", "daily_status", "daily_status_for_classes",
    "weekly_quiz_locked", "warmup_set_locked", "weekly_mystery_locked",
    "weekly_mystery_correct_students", "weekly_mystery_teacher_stats",
    "completed_attempts_for_class", "leaderboard", "student_learning_stats",
    "mystery_student_stats", "completed_mystery_days",
    "alternate_learning_activity_rows", "learning_activity_rows",
})


def clear_teacher_read_cache(session) -> None:
    """Also invalidate any facade still referenced by a callback/repository."""
    state = session.pop(HISTORY_STATE_KEY, None)
    if state is not None:
        state["entries"].clear()
        state["generation"] += 1


def _freeze(value):
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _copy_evidence(rows, method):
    # Answer records are frozen dataclasses containing scalar fields/datetimes.
    # Only quiz sets contain editable nested question dictionaries. Avoid
    # copying thousands of immutable answer records on every standard selection.
    return deepcopy(rows) if method == "list_weekly_quiz_sets" else list(rows)


class TeacherReadStore:
    def __init__(self, source, session, *, today: date, clock=monotonic):
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_today", today)
        object.__setattr__(self, "_clock", clock)
        state = session.get(HISTORY_STATE_KEY)
        if state is None or state["source"] is not source or state["day"] != today:
            clear_teacher_read_cache(session)
            state = {"source": source, "day": today, "entries": {}, "generation": 0}
            session[HISTORY_STATE_KEY] = state
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_memo", {})
        object.__setattr__(self, "_generation", state["generation"])

    def invalidate(self):
        self._state["entries"].clear()
        self._state["generation"] += 1
        self._memo.clear()

    def __setattr__(self, name, value):
        # Preserve optional reference-backend repositories and rollback fields.
        self.invalidate()
        setattr(self._source, name, value)

    def __getattr__(self, name):
        target = getattr(self._source, name)
        if name == "client":
            # Planner RPCs and image/settings helpers can write through client.
            # Conservatively clear before handing out the unmodified client.
            self.invalidate()
            return target
        if not callable(target):
            return target

        @wraps(target)
        def call(*args, **kwargs):
            if self._generation != self._state["generation"]:
                self._memo.clear()
                object.__setattr__(self, "_generation", self._state["generation"])
            if name in _RENDER_READS:
                bound = signature(target).bind(*args, **kwargs)
                bound.apply_defaults()
                key = (name, _freeze(bound.arguments))
                if key not in self._memo:
                    # Failed reads never enter either cache.
                    self._memo[key] = deepcopy(target(*args, **kwargs))
                return deepcopy(self._memo[key])
            if (name.startswith(("list_", "get_")) and not name.startswith("get_or_create_")) or name in _OTHER_READS:
                return target(*args, **kwargs)
            # Known and future mutations fail safe, including partial failures.
            self.invalidate()
            try:
                return target(*args, **kwargs)
            finally:
                self.invalidate()
        return call

    def get_app_settings(self, setting_keys):
        if self._generation != self._state["generation"]:
            self._memo.clear()
            object.__setattr__(self, "_generation", self._state["generation"])
        keys = list(dict.fromkeys(str(key) for key in setting_keys if str(key)))
        missing = [key for key in keys if ("setting", key) not in self._memo]
        if missing:
            values = self._source.get_app_settings(missing)
            for key in missing:
                # Keep absence distinct from an explicitly stored null.
                self._memo[("setting", key)] = (key in values, deepcopy(values.get(key)))
        return {key: deepcopy(self._memo[("setting", key)][1]) for key in keys
                if self._memo[("setting", key)][0]}

    def get_app_setting(self, setting_key, default=None):
        value = self.get_app_settings([setting_key]).get(str(setting_key))
        return default if value is None else value

    def prior_evidence(self, method, start, end, *, class_id, roster_ids):
        """Cache only past evidence; filter with a fresh roster in the caller."""
        if method not in {"list_warmup_answers", "list_weekly_quiz_sets",
                           "list_weekly_quiz_answers_range", "list_standard_recovery_answers"}:
            raise ValueError("Unsupported evidence reader")
        if end >= self._today:
            raise ValueError("Current-day evidence must be read live")
        kwargs = {"class_id": str(class_id)}
        if method != "list_weekly_quiz_sets":
            kwargs["include_test"] = True
        key = (method, str(start), str(end), str(class_id), tuple(sorted(roster_ids)))
        entries = self._state["entries"]
        now = self._clock()
        for old_key, (stamp, _) in list(entries.items()):
            if now - stamp >= HISTORY_TTL:
                del entries[old_key]
        if key not in entries:
            rows = getattr(self._source, method)(start, end, **kwargs)
            if len(rows) > MAX_HISTORY_ROWS:
                return rows
            while entries and (len(entries) >= MAX_HISTORY_ENTRIES or
                               sum(len(item[1]) for item in entries.values()) + len(rows) > MAX_HISTORY_ROWS):
                del entries[next(iter(entries))]
            entries[key] = (now, _copy_evidence(rows, method))
        return _copy_evidence(entries[key][1], method)
