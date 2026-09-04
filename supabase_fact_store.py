from __future__ import annotations

"""Supabase production backend for Teal's Daily Fact Challenge.

All calls are made server-side from Streamlit with SUPABASE_SECRET_KEY. RLS is
enabled with no public policies in the supplied schema, so student browsers never
receive direct database credentials.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Callable, Mapping, Sequence, TypeVar
import hashlib
import random
import secrets
import time

import httpx

try:
    from supabase import Client, create_client
    try:
        from supabase.client import ClientOptions
    except ImportError:  # Compatibility with older supabase-py package layouts.
        from supabase.lib.client_options import ClientOptions
except ImportError:  # Local/offline Practice can still load before dependencies are installed.
    Client = object  # type: ignore[assignment]
    ClientOptions = None  # type: ignore[assignment]

    def create_client(*_args, **_kwargs):
        raise RuntimeError("The supabase package is not installed. Install requirements.txt for Daily accounts.")

from fact_engine import Fact, canonical_pair
from adaptive_engine import MasterySnapshot, update_snapshot, mastery_counts
from alternate_followup import ALT_MODES, daily_evidence_rows, missed_question_items, skill_identity_for_question
from alternate_focus import ALT_FOCUS_SESSION_LENGTH
from fact_store import (
    AnswerRecord,
    AttemptComplete,
    AttemptNotStarted,
    AttemptRecord,
    ChallengeRecord,
    ClassRecord,
    FactStoreError,
    NameTaken,
    NotFound,
    PracticeRecord,
    LearningProgressRecord,
    AlternateLearningProgressRecord,
    AlternateLearningEventRecord,
    WeeklyMysteryRecord,
    MysteryUnlockRecord,
    MysteryGuessRecord,
    StudentRecord,
    WarmupSetRecord,
    WarmupAnswerRecord,
    generate_class_code,
    hash_pin,
    normalize_name,
    utc_now,
    verify_pin,
    validate_pin,
)


# Classroom pages should fail visibly instead of sitting behind a spinner for an
# unbounded network wait. Normal Supabase reads are far below this threshold;
# a request that reaches it is already an infrastructure problem.
POSTGREST_TIMEOUT_SECONDS = 12
STORAGE_TIMEOUT_SECONDS = 12


def _create_supabase_client(url: str, key: str):
    """Create a server-side client with bounded request waits when supported.

    ClientOptions has moved between supabase-py releases and had a historical
    regression in one release line. Keep a safe fallback so resilience settings
    can never make the app fail to boot.
    """
    if ClientOptions is not None:
        try:
            options = ClientOptions(
                postgrest_client_timeout=POSTGREST_TIMEOUT_SECONDS,
                storage_client_timeout=STORAGE_TIMEOUT_SECONDS,
                schema="public",
                auto_refresh_token=False,
                persist_session=False,
            )
            return create_client(url, key, options=options)
        except (TypeError, AttributeError):
            pass
    return create_client(url, key)


def normalize_supabase_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    for suffix in ("/rest/v1", "/rest/v1/"):
        if url.lower().endswith(suffix.rstrip("/")):
            url = url[: -len(suffix.rstrip("/"))]
            break
    return url.rstrip("/")


def _rows(response) -> list[dict]:
    data = getattr(response, "data", None)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _first(response) -> dict | None:
    rows = _rows(response)
    return rows[0] if rows else None


def _execute_returning(builder, columns: str = "*"):
    """Execute a mutation and return its row representation across supabase-py versions.

    Newer PostgREST builders expose ``.select()`` after insert/update/upsert,
    while the pinned classroom-safe supabase-py 2.28.3 mutation builder does
    not. Version 2.28.3 returns inserted/updated rows by default, so falling
    back to ``execute()`` preserves the same behavior without crashing.
    """
    select_method = getattr(builder, "select", None)
    if callable(select_method):
        return select_method(columns).execute()
    return builder.execute()


def _dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _error_text(exc: Exception) -> str:
    parts = [str(exc)]
    for attr in ("code", "message", "details", "hint"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(str(value))
    return " | ".join(parts).lower()


def _is_unique(exc: Exception) -> bool:
    text = _error_text(exc)
    return "23505" in text or "duplicate key" in text or "unique constraint" in text


_T = TypeVar("_T")


def _is_transient_http_error(exc: Exception) -> bool:
    """Return True for short-lived network/transport failures worth retrying."""
    transient_types = (
        httpx.ReadError,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        httpx.ReadTimeout,
        httpx.ConnectTimeout,
        httpx.PoolTimeout,
    )
    if isinstance(exc, transient_types):
        return True
    text = _error_text(exc)
    return any(token in text for token in (
        "readerror", "connection reset", "server disconnected",
        "remoteprotocolerror", "read timeout", "connect timeout", "pool timeout",
    ))


def _retry_transient(operation: Callable[[], _T], *, attempts: int = 4) -> _T:
    """Retry short-lived HTTP read/connection failures with tiny classroom-safe backoff."""
    last_exc: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            if not _is_transient_http_error(exc) or attempt >= attempts - 1:
                raise
            # A hard timeout already consumed several seconds. Give it only one
            # retry so a degraded backend cannot hold a classroom page behind a
            # spinner for four full timeout windows. Immediate connection/read
            # resets can still use the existing short retry sequence.
            timeout_types = (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout)
            if isinstance(exc, timeout_types) and attempt >= 1:
                raise
            delay = (0.12 * (2 ** attempt)) + random.uniform(0.0, 0.06)
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _class(row: Mapping) -> ClassRecord:
    return ClassRecord(
        class_id=str(row["class_id"]),
        class_name=str(row["class_name"]),
        class_code=str(row["class_code"]),
        active=bool(row.get("active", True)),
        created_at=_dt(row.get("created_at")) or utc_now(),
    )


def _student(row: Mapping) -> StudentRecord:
    return StudentRecord(
        student_id=str(row["student_id"]),
        class_id=str(row["class_id"]),
        nickname=str(row["nickname"]),
        active=bool(row.get("active", True)),
        created_at=_dt(row.get("created_at")) or utc_now(),
        pin_code=None if row.get("pin_code") is None else str(row.get("pin_code")),
        is_test=bool(row.get("is_test", False)),
    )


def _challenge(row: Mapping) -> ChallengeRecord:
    facts = tuple(Fact.from_dict(item) for item in (row.get("facts") or []))
    return ChallengeRecord(
        challenge_id=str(row["challenge_id"]),
        challenge_date=str(row["challenge_date"]),
        challenge_version=str(row["challenge_version"]),
        facts=facts,
        created_at=_dt(row.get("created_at")) or utc_now(),
    )


def _attempt(row: Mapping) -> AttemptRecord:
    return AttemptRecord(
        attempt_id=str(row["attempt_id"]),
        student_id=str(row["student_id"]),
        challenge_id=str(row["challenge_id"]),
        created_at=_dt(row.get("created_at")) or utc_now(),
        timed_started_at=_dt(row.get("timed_started_at")),
        completed_at=_dt(row.get("completed_at")),
        correct_count=None if row.get("correct_count") is None else int(row["correct_count"]),
        timed_seconds=None if row.get("timed_seconds") is None else float(row["timed_seconds"]),
        learning_evidence_applied_at=_dt(row.get("learning_evidence_applied_at")),
        daily_mode=str(row.get("daily_mode") or "Multiplication"),
        custom_questions=tuple(dict(item) for item in (row.get("custom_questions") or [])),
        custom_answers=tuple(int(value) for value in (row.get("custom_answers") or [])),
    )


def _answer(row: Mapping) -> AnswerRecord:
    return AnswerRecord(
        attempt_id=str(row["attempt_id"]),
        question_number=int(row["question_number"]),
        a=int(row["a"]),
        b=int(row["b"]),
        student_answer=int(row["student_answer"]),
        correct_answer=int(row["correct_answer"]),
        correct=bool(row["correct"]),
        submitted_at=_dt(row.get("submitted_at")) or utc_now(),
        response_seconds=None if row.get("response_seconds") is None else float(row["response_seconds"]),
        first_student_answer=(
            int(row["first_student_answer"])
            if row.get("first_student_answer") is not None
            else int(row["student_answer"])
        ),
        first_correct=(
            bool(row["first_correct"])
            if row.get("first_correct") is not None
            else bool(row["correct"])
        ),
    )


def _practice(row: Mapping) -> PracticeRecord:
    return PracticeRecord(
        student_id=None if row.get("student_id") is None else str(row["student_id"]),
        focus=str(row.get("focus") or "Practice"),
        a=int(row["a"]),
        b=int(row["b"]),
        student_answer=int(row["student_answer"]),
        correct_answer=int(row["correct_answer"]),
        correct=bool(row["correct"]),
        created_at=_dt(row.get("created_at")) or utc_now(),
        response_seconds=None if row.get("response_seconds") is None else float(row["response_seconds"]),
        challenge_id=None if row.get("challenge_id") is None else str(row["challenge_id"]),
        activity_type=str(row.get("activity_type") or "free_practice"),
        activity_index=None if row.get("activity_index") is None else int(row["activity_index"]),
        is_retry=bool(row.get("is_retry", False)),
    )


def _mastery(row: Mapping) -> MasterySnapshot:
    return MasterySnapshot(
        a=int(row["a"]),
        b=int(row["b"]),
        evidence_count=int(row.get("evidence_count") or 0),
        correct_count=int(row.get("correct_count") or 0),
        ema_accuracy=None if row.get("ema_accuracy") is None else float(row["ema_accuracy"]),
        ema_seconds=None if row.get("ema_seconds") is None else float(row["ema_seconds"]),
        correct_streak=int(row.get("correct_streak") or 0),
        status=str(row.get("mastery_status") or "Unknown"),
        last_practiced_at=_dt(row.get("last_practiced_at")),
    )


def _weekly_mystery(row: Mapping) -> WeeklyMysteryRecord:
    return WeeklyMysteryRecord(
        week_start=str(row["week_start"]),
        mystery_key=str(row["mystery_key"]),
        created_at=_dt(row.get("created_at")) or utc_now(),
        updated_at=_dt(row.get("updated_at")) or utc_now(),
    )


def _mystery_unlock(row: Mapping) -> MysteryUnlockRecord:
    return MysteryUnlockRecord(
        student_id=str(row["student_id"]),
        week_start=str(row["week_start"]),
        day_number=int(row["day_number"]),
        challenge_id=str(row["challenge_id"]),
        unlocked_at=_dt(row.get("unlocked_at")) or utc_now(),
    )


def _mystery_guess(row: Mapping) -> MysteryGuessRecord:
    return MysteryGuessRecord(
        student_id=str(row["student_id"]),
        week_start=str(row["week_start"]),
        guess_text=str(row.get("guess_text") or ""),
        correct=bool(row.get("correct")),
        clue_count=int(row.get("clue_count") or 0),
        guessed_at=_dt(row.get("guessed_at")) or utc_now(),
        guess_day=int(row.get("guess_day") or 4),
    )


def _warmup_set(row: Mapping) -> WarmupSetRecord:
    return WarmupSetRecord(
        warmup_set_id=str(row["warmup_set_id"]),
        class_id=str(row["class_id"]),
        warmup_date=str(row["warmup_date"]),
        question_one=dict(row.get("question_one") or {}),
        question_two=dict(row.get("question_two") or {}),
        created_at=_dt(row.get("created_at")) or utc_now(),
        updated_at=_dt(row.get("updated_at")) or utc_now(),
    )


def _warmup_answer(row: Mapping) -> WarmupAnswerRecord:
    return WarmupAnswerRecord(
        warmup_answer_id=str(row["warmup_answer_id"]),
        warmup_set_id=str(row["warmup_set_id"]),
        student_id=str(row["student_id"]),
        class_id=str(row["class_id"]),
        warmup_date=str(row["warmup_date"]),
        question_slot=int(row["question_slot"]),
        question_type=str(row.get("question_type") or "Short answer"),
        prompt=str(row.get("prompt") or ""),
        standard_code=str(row.get("standard_code") or ""),
        standard_description=str(row.get("standard_description") or ""),
        student_answer=str(row.get("student_answer") or ""),
        correct_answer=str(row.get("correct_answer") or ""),
        correct=bool(row.get("correct", False)),
        answered_at=_dt(row.get("answered_at")) or utc_now(),
    )


def _learning(row: Mapping) -> LearningProgressRecord:
    plan = tuple(Fact.from_dict(item) for item in (row.get("focus_plan") or []))
    return LearningProgressRecord(
        student_id=str(row["student_id"]),
        challenge_id=str(row["challenge_id"]),
        focus_plan=plan,
        fix_completed_at=_dt(row.get("fix_completed_at")),
        focus_completed_at=_dt(row.get("focus_completed_at")),
        completed_at=_dt(row.get("completed_at")),
    )


def _alternate_learning(row: Mapping) -> AlternateLearningProgressRecord:
    return AlternateLearningProgressRecord(
        student_id=str(row["student_id"]),
        challenge_id=str(row["challenge_id"]),
        daily_mode=str(row.get("daily_mode") or "Mixed"),
        focus_plan=tuple(dict(item) for item in (row.get("focus_plan") or [])),
        fix_completed_at=_dt(row.get("fix_completed_at")),
        focus_completed_at=_dt(row.get("focus_completed_at")),
        completed_at=_dt(row.get("completed_at")),
    )


def _alternate_event(row: Mapping) -> AlternateLearningEventRecord:
    return AlternateLearningEventRecord(
        event_id=str(row["event_id"]), student_id=str(row["student_id"]),
        challenge_id=str(row["challenge_id"]), attempt_id=str(row["attempt_id"]),
        daily_mode=str(row.get("daily_mode") or "Mixed"), activity_type=str(row.get("activity_type") or "daily"),
        activity_index=int(row.get("activity_index") or 0), domain=str(row.get("domain") or ""),
        skill_key=str(row.get("skill_key") or ""), skill_label=str(row.get("skill_label") or ""),
        item_key=str(row.get("item_key") or ""), prompt=str(row.get("prompt") or ""),
        student_answer=int(row.get("student_answer") or 0), correct_answer=int(row.get("correct_answer") or 0),
        correct=bool(row.get("correct")), is_retry=bool(row.get("is_retry")),
        created_at=_dt(row.get("created_at")) or utc_now(),
        response_seconds=None if row.get("response_seconds") is None else float(row["response_seconds"]),
        client_event_id=None if row.get("client_event_id") is None else str(row.get("client_event_id")),
    )


class SupabaseFactStore:
    def __init__(self, supabase_url: str, supabase_secret_key: str, *, client: Client | None = None):
        url = normalize_supabase_url(supabase_url)
        key = str(supabase_secret_key or "").strip()
        if not url:
            raise ValueError("SUPABASE_URL is missing.")
        if not key:
            raise ValueError("SUPABASE_SECRET_KEY is missing.")
        self.url_was_normalized = url != str(supabase_url or "").strip().rstrip("/")
        self.client: Client = client or _create_supabase_client(url, key)

    @classmethod
    def from_secrets(cls, secrets: Mapping[str, str]) -> "SupabaseFactStore":
        return cls(str(secrets["SUPABASE_URL"]), str(secrets["SUPABASE_SECRET_KEY"]))

    def health_check(self) -> bool:
        self.client.table("classes").select("class_id").limit(1).execute()
        self.client.table("daily_attempts").select("attempt_id,learning_evidence_applied_at,daily_mode,custom_questions,custom_answers").limit(1).execute()
        self.client.table("daily_answers").select("answer_id,first_student_answer,first_correct").limit(1).execute()
        self.client.table("student_fact_mastery").select("student_id").limit(1).execute()
        self.client.table("daily_learning_progress").select("student_id").limit(1).execute()
        self.client.table("alternate_learning_progress").select("student_id").limit(1).execute()
        self.client.table("alternate_learning_events").select("event_id").limit(1).execute()
        self.client.table("weekly_mysteries").select("week_start").limit(1).execute()
        self.client.table("weekly_mystery_unlocks").select("student_id").limit(1).execute()
        self.client.table("weekly_mystery_guesses").select("student_id").limit(1).execute()
        return True

    # ----- Classes -----
    def create_class(self, class_name: str, class_code: str | None = None) -> ClassRecord:
        name, key = normalize_name(class_name, label="Class name")
        attempts = 1 if class_code else 8
        last_exc: Exception | None = None
        for _ in range(attempts):
            code = str(class_code or generate_class_code()).strip().upper()
            try:
                response = _execute_returning(
                    self.client.table("classes")
                    .insert({"class_name": name, "class_name_key": key, "class_code": code})
                )
                row = _first(response)
                if row is None:
                    raise FactStoreError("Supabase did not return the created class.")
                return _class(row)
            except Exception as exc:
                last_exc = exc
                if _is_unique(exc) and not class_code:
                    # Could be either name or random code. Check whether name is
                    # already taken before trying another code.
                    existing = (
                        self.client.table("classes")
                        .select("class_id")
                        .eq("class_name_key", key)
                        .limit(1)
                        .execute()
                    )
                    if _first(existing):
                        raise NameTaken("That class name already exists.") from exc
                    continue
                if _is_unique(exc):
                    raise NameTaken("That class name or class code already exists.") from exc
                raise
        raise FactStoreError("Could not generate a unique class code.") from last_exc

    def list_classes(self, *, include_inactive: bool = False) -> list[ClassRecord]:
        # Class lists sit at the top of several teacher workflows. A brief
        # Supabase transport reset should not crash the entire dashboard; rebuild
        # the query for each retry so a failed PostgREST builder is never reused.
        def fetch_classes():
            query = self.client.table("classes").select("*")
            if not include_inactive:
                query = query.eq("active", True)
            return query.order("class_name").execute()

        rows = _rows(_retry_transient(fetch_classes, attempts=4))
        return [_class(row) for row in rows]

    def get_class(self, class_id: str) -> ClassRecord:
        row = _first(_retry_transient(lambda: (
            self.client.table("classes")
            .select("class_id,class_name,class_code,active,created_at")
            .eq("class_id", str(class_id))
            .limit(1)
            .execute()
        ), attempts=2))
        if row is None:
            raise NotFound("Class not found.")
        return _class(row)

    def set_class_active(self, class_id: str, active: bool) -> ClassRecord:
        row = _first(_execute_returning(
            self.client.table("classes")
            .update({"active": bool(active)})
            .eq("class_id", str(class_id))
        ))
        if row is None:
            raise NotFound("Class not found.")
        return _class(row)

    # ----- Students -----
    def create_student(self, class_id: str, nickname: str, pin: str, *, is_test: bool = False) -> StudentRecord:
        name, key = normalize_name(nickname, label="Nickname", max_length=28)
        pin = validate_pin(pin)
        payload = {
            "class_id": str(class_id),
            "nickname": name,
            "nickname_key": key,
            "pin_hash": hash_pin(pin),
            "pin_code": pin,
            "is_test": bool(is_test),
        }
        try:
            row = _first(_execute_returning(self.client.table("students").insert(payload)))
        except Exception as exc:
            if _is_unique(exc):
                raise NameTaken(f"{name} already exists in this class.") from exc
            raise
        if row is None:
            raise FactStoreError("Supabase did not return the created student.")
        return _student(row)

    def authenticate_student(self, class_id: str, nickname: str, pin: str) -> StudentRecord | None:
        try:
            _, key = normalize_name(nickname, label="Nickname", max_length=28)
        except ValueError:
            return None
        row = _first(_retry_transient(lambda: (
            self.client.table("students")
            .select("student_id,class_id,nickname,pin_hash,active,created_at,is_test")
            .eq("class_id", str(class_id))
            .eq("is_test", False)
            .eq("nickname_key", key)
            .eq("active", True)
            .limit(1)
            .execute()
        )))
        if row is None or not verify_pin(pin, str(row.get("pin_hash") or "")):
            return None
        return _student(row)

    def list_students(self, class_id: str, *, include_inactive: bool = False, include_test: bool = False) -> list[StudentRecord]:
        def fetch_students():
            query = self.client.table("students").select("student_id,class_id,nickname,pin_code,active,created_at,is_test").eq("class_id", str(class_id))
            if not include_inactive:
                query = query.eq("active", True)
            if not include_test:
                query = query.eq("is_test", False)
            return query.order("nickname").execute()
        return [_student(row) for row in _rows(_retry_transient(fetch_students))]

    def get_student(self, student_id: str) -> StudentRecord:
        row = _first(_retry_transient(lambda: (
            self.client.table("students")
            .select("student_id,class_id,nickname,pin_code,active,created_at,is_test")
            .eq("student_id", str(student_id))
            .limit(1)
            .execute()
        )))
        if row is None:
            raise NotFound("Student not found.")
        return _student(row)

    def get_student_login_context(self, student_id: str) -> tuple[StudentRecord, ClassRecord]:
        """Load the remembered student and their class in one lightweight read.

        This is intentionally separate from get_student(): startup should not fetch
        the whole active class list just to restore one student's 30-day login.
        """
        try:
            row = _first(_retry_transient(lambda: (
                self.client.table("students")
                .select(
                    "student_id,class_id,nickname,pin_code,active,created_at,is_test,"
                    "classes(class_id,class_name,class_code,active,created_at)"
                )
                .eq("student_id", str(student_id))
                .limit(1)
                .execute()
            ), attempts=2))
            if row is None:
                raise NotFound("Student not found.")
            student = _student(row)
            class_row = row.get("classes")
            if isinstance(class_row, list):
                class_row = class_row[0] if class_row else None
            if isinstance(class_row, Mapping):
                return student, _class(class_row)
        except NotFound:
            raise
        except Exception as exc:
            if _is_transient_http_error(exc):
                raise
            # If a deployment happens against an unusual PostgREST relationship
            # configuration, preserve login compatibility rather than failing hard.
        student = self.get_student(student_id)
        return student, self.get_class(student.class_id)

    def get_test_student(self, class_id: str | None = None) -> StudentRecord | None:
        def fetch_test_student():
            query = self.client.table("students").select("student_id,class_id,nickname,pin_code,active,created_at,is_test").eq("is_test", True)
            if class_id is not None:
                query = query.eq("class_id", str(class_id))
            return query.order("created_at").limit(1).execute()
        row = _first(_retry_transient(fetch_test_student))
        return None if row is None else _student(row)

    def reset_test_student(self, class_id: str) -> StudentRecord:
        test_rows = _rows(_retry_transient(lambda: self.client.table("students").select("student_id").eq("is_test", True).execute()))
        test_ids = [str(row["student_id"]) for row in test_rows]
        if test_ids:
            # practice_answers uses ON DELETE SET NULL, so remove sandbox practice rows explicitly.
            _retry_transient(lambda: self.client.table("practice_answers").delete().in_("student_id", test_ids).execute())
            _retry_transient(lambda: self.client.table("students").delete().in_("student_id", test_ids).execute())
        return self.create_student(str(class_id), "🧪 Test Student", "0000", is_test=True)

    def rename_student(self, student_id: str, nickname: str) -> StudentRecord:
        student = self.get_student(student_id)
        name, key = normalize_name(nickname, label="Nickname", max_length=28)
        try:
            row = _first(_execute_returning(
                self.client.table("students")
                .update({"nickname": name, "nickname_key": key})
                .eq("student_id", student.student_id),
                "student_id,class_id,nickname,pin_code,active,created_at,is_test",
            ))
        except Exception as exc:
            if _is_unique(exc):
                raise NameTaken("That nickname is already used in this class.") from exc
            raise
        if row is None:
            raise NotFound("Student not found.")
        return _student(row)

    def reset_student_pin(self, student_id: str, pin: str) -> None:
        pin = validate_pin(pin)
        response = _execute_returning(
            self.client.table("students")
            .update({"pin_hash": hash_pin(pin), "pin_code": pin})
            .eq("student_id", str(student_id)),
            "student_id",
        )
        if _first(response) is None:
            raise NotFound("Student not found.")

    def set_student_active(self, student_id: str, active: bool) -> StudentRecord:
        row = _first(_execute_returning(
            self.client.table("students")
            .update({"active": bool(active)})
            .eq("student_id", str(student_id)),
            "student_id,class_id,nickname,pin_code,active,created_at,is_test",
        ))
        if row is None:
            raise NotFound("Student not found.")
        return _student(row)

    def move_student(self, student_id: str, new_class_id: str) -> StudentRecord:
        student = self.get_student(student_id)
        if student.class_id == str(new_class_id):
            return student
        if not any(item.class_id == str(new_class_id) for item in self.list_classes(include_inactive=True)):
            raise NotFound("Class not found.")
        try:
            row = _first(_execute_returning(
                self.client.table("students")
                .update({"class_id": str(new_class_id)})
                .eq("student_id", student.student_id),
                "student_id,class_id,nickname,pin_code,active,created_at,is_test",
            ))
        except Exception as exc:
            if _is_unique(exc):
                raise NameTaken("That nickname is already used in the destination class.") from exc
            raise
        if row is None:
            raise NotFound("Student not found.")
        return _student(row)

    def delete_student(self, student_id: str) -> None:
        # One database request. Child rows are removed by ON DELETE CASCADE.
        self.client.table("students").delete().eq("student_id", str(student_id)).execute()

    def delete_students(self, student_ids: Sequence[str]) -> int:
        """Delete many student accounts in one PostgREST request.

        Student-linked Daily, practice, mastery, focus, and mystery rows are
        removed by the database's ON DELETE CASCADE foreign keys.
        """
        ids = list(dict.fromkeys(str(student_id) for student_id in student_ids if str(student_id)))
        if not ids:
            return 0
        self.client.table("students").delete().in_("student_id", ids).execute()
        return len(ids)

    def delete_class_students(self, class_id: str) -> int:
        """Clear an entire class roster in one database request, leaving the class itself intact."""
        # Count first only so the teacher can receive an accurate confirmation.
        rows = _rows(
            self.client.table("students")
            .select("student_id")
            .eq("class_id", str(class_id))
            .execute()
        )
        count = len(rows)
        if count:
            self.client.table("students").delete().eq("class_id", str(class_id)).execute()
        return count

    # ----- Challenge -----
    def get_challenge(self, challenge_date: date | str) -> ChallengeRecord | None:
        key = challenge_date.isoformat() if isinstance(challenge_date, date) else str(challenge_date)
        row = _first(_retry_transient(lambda: (
            self.client.table("daily_challenges")
            .select("*")
            .eq("challenge_date", key)
            .limit(1)
            .execute()
        )))
        return _challenge(row) if row else None

    def get_or_create_challenge(
        self, challenge_date: date | str, challenge_version: str, facts: Sequence[Fact]
    ) -> ChallengeRecord:
        key = challenge_date.isoformat() if isinstance(challenge_date, date) else str(challenge_date)

        # The first challenge stored for a date is the classroom source of truth.
        # This protects an in-progress Daily from later UI/teaching deployments
        # that may regenerate a different local copy for the same date.
        existing = self.get_challenge(key)
        if existing is not None:
            return existing

        payload = {
            "challenge_date": key,
            "challenge_version": str(challenge_version),
            "facts": [fact.as_dict() for fact in facts],
        }
        try:
            self.client.table("daily_challenges").insert(payload).execute()
        except Exception as exc:
            if not _is_unique(exc):
                raise

        # If another request won the insert race, its stored challenge still wins.
        record = self.get_challenge(key)
        if record is None:
            raise FactStoreError("Could not load today's challenge after registration.")
        return record

    # ----- Attempts / answers -----
    def get_or_create_attempt(
        self, student_id: str, challenge_id: str, *, daily_mode: str = "Multiplication",
        custom_questions: Sequence[Mapping] | None = None,
    ) -> AttemptRecord:
        existing = self.get_attempt_for_student(student_id, challenge_id)
        if existing:
            return existing
        mode = str(daily_mode or "Multiplication")
        questions = [dict(item) for item in (custom_questions or ())]
        if mode != "Multiplication" and len(questions) != 10:
            raise ValueError("Alternate Daily 10 attempts require exactly 10 stored questions.")
        payload = {"student_id": str(student_id), "challenge_id": str(challenge_id), "daily_mode": mode}
        if mode != "Multiplication":
            payload["custom_questions"] = questions
        try:
            row = _first(_execute_returning(self.client.table("daily_attempts").insert(payload)))
        except Exception as exc:
            if _is_unique(exc):
                existing = self.get_attempt_for_student(student_id, challenge_id)
                if existing:
                    return existing
            raise
        if row is None:
            raise FactStoreError("Supabase did not return the created attempt.")
        return _attempt(row)

    def get_attempt(self, attempt_id: str) -> AttemptRecord:
        row = _first(_retry_transient(lambda: (
            self.client.table("daily_attempts")
            .select("*")
            .eq("attempt_id", str(attempt_id))
            .limit(1)
            .execute()
        )))
        if row is None:
            raise NotFound("Attempt not found.")
        return _attempt(row)

    def get_attempt_for_student(self, student_id: str, challenge_id: str) -> AttemptRecord | None:
        row = _first(_retry_transient(lambda: (
            self.client.table("daily_attempts")
            .select("*")
            .eq("student_id", str(student_id))
            .eq("challenge_id", str(challenge_id))
            .limit(1)
            .execute()
        )))
        return _attempt(row) if row else None

    def get_answers(self, attempt_id: str) -> list[AnswerRecord]:
        return [
            _answer(row)
            for row in _rows(
                _retry_transient(lambda: (
                    self.client.table("daily_answers")
                    .select("*")
                    .eq("attempt_id", str(attempt_id))
                    .order("question_number")
                    .execute()
                ))
            )
        ]

    def submit_first_answer(
        self, attempt_id: str, fact: Fact, student_answer: int, *, submitted_at: datetime | None = None
    ) -> AttemptRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.completed_at is not None:
            raise AttemptComplete("Today's Daily is already complete.")
        existing = self.get_answers(attempt_id)
        if existing:
            if attempt.timed_started_at is None:
                first = min(existing, key=lambda item: item.question_number)
                self.client.table("daily_attempts").update({"timed_started_at": first.submitted_at.isoformat()}).eq(
                    "attempt_id", str(attempt_id)
                ).execute()
                return self.get_attempt(attempt_id)
            return attempt
        when = submitted_at or utc_now()
        payload = {
            "attempt_id": str(attempt_id),
            "question_number": 1,
            "a": fact.a,
            "b": fact.b,
            "student_answer": int(student_answer),
            "correct_answer": fact.product,
            "correct": int(student_answer) == fact.product,
            "first_student_answer": int(student_answer),
            "first_correct": int(student_answer) == fact.product,
            "submitted_at": when.isoformat(),
        }
        try:
            self.client.table("daily_answers").insert(payload).execute()
        except Exception as exc:
            if not _is_unique(exc):
                raise
        self.client.table("daily_attempts").update({"timed_started_at": when.isoformat()}).eq(
            "attempt_id", str(attempt_id)
        ).is_("timed_started_at", "null").execute()
        return self.get_attempt(attempt_id)

    def complete_attempt(
        self,
        attempt_id: str,
        remaining_answers: Sequence[tuple[Fact, int]],
        *,
        completed_at: datetime | None = None,
    ) -> AttemptRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.completed_at is not None:
            return attempt
        existing = self.get_answers(attempt_id)
        if attempt.timed_started_at is None or not any(a.question_number == 1 for a in existing):
            raise AttemptNotStarted("Submit Fact 1 before completing the timed sprint.")
        if len(remaining_answers) != 9:
            raise ValueError("The timed sprint must contain Facts 2-10.")
        when = completed_at or utc_now()

        payloads = []
        for question_number, (fact, value) in enumerate(remaining_answers, start=2):
            payloads.append({
                "attempt_id": str(attempt_id),
                "question_number": question_number,
                "a": fact.a,
                "b": fact.b,
                "student_answer": int(value),
                "correct_answer": fact.product,
                "correct": int(value) == fact.product,
                "first_student_answer": int(value),
                "first_correct": int(value) == fact.product,
                "submitted_at": when.isoformat(),
            })
        # Upsert makes completion retry-safe if a network hiccup lands between
        # the answer write and the attempt summary update.
        _retry_transient(lambda: self.client.table("daily_answers").upsert(
            payloads, on_conflict="attempt_id,question_number"
        ).execute())
        answers = self.get_answers(attempt_id)
        if len(answers) != 10:
            raise FactStoreError("Daily completion did not save all 10 answers.")
        correct_count = sum(answer.correct for answer in answers)
        seconds = max(0.0, (when - attempt.timed_started_at).total_seconds())
        self.client.table("daily_attempts").update({
            "completed_at": when.isoformat(),
            "correct_count": correct_count,
            "timed_seconds": round(seconds, 3),
        }).eq("attempt_id", str(attempt_id)).execute()
        return self.get_attempt(attempt_id)

    def complete_full_attempt(
        self,
        attempt_id: str,
        answers: Sequence[tuple[Fact, int]],
        timed_seconds: float,
        *,
        response_seconds: Sequence[float | None] | None = None,
        first_answers: Sequence[tuple[Fact, int]] | None = None,
        completed_at: datetime | None = None,
    ) -> AttemptRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.completed_at is not None:
            return self.ensure_daily_learning_evidence(attempt_id)
        if len(answers) != 10:
            raise ValueError("A Daily completion must contain exactly 10 answers.")
        evidence_answers = list(first_answers or answers)
        if len(evidence_answers) != 10:
            raise ValueError("Daily first-answer evidence must contain exactly 10 answers.")
        seconds = float(timed_seconds)
        if not 0.1 <= seconds <= 3600:
            raise ValueError("Timed sprint duration is outside the allowed range.")
        latencies = list(response_seconds or [None] * 10)
        if len(latencies) != 10:
            raise ValueError("Daily response timing must contain exactly 10 values.")
        when = completed_at or utc_now()
        started = when - timedelta(seconds=seconds)
        payloads = []
        for question_number, (((fact, value), (evidence_fact, first_value)), latency) in enumerate(
            zip(zip(answers, evidence_answers), latencies), start=1
        ):
            if fact.key != evidence_fact.key:
                raise ValueError("Daily first-answer evidence does not match the Daily fact order.")
            payloads.append({
                "attempt_id": str(attempt_id),
                "question_number": question_number,
                "a": fact.a,
                "b": fact.b,
                "student_answer": int(value),
                "correct_answer": fact.product,
                "correct": int(value) == fact.product,
                "first_student_answer": int(first_value),
                "first_correct": int(first_value) == fact.product,
                "submitted_at": when.isoformat(),
                "response_seconds": None if latency is None else round(float(latency), 3),
            })
        _retry_transient(lambda: self.client.table("daily_answers").upsert(
            payloads, on_conflict="attempt_id,question_number"
        ).execute())
        saved = self.get_answers(attempt_id)
        if len(saved) != 10:
            raise FactStoreError("Daily completion did not save all 10 answers.")
        correct_count = sum(answer.correct for answer in saved)
        _retry_transient(lambda: self.client.table("daily_attempts").update({
            "timed_started_at": started.isoformat(),
            "completed_at": when.isoformat(),
            "correct_count": correct_count,
            "timed_seconds": round(seconds, 3),
            "learning_evidence_applied_at": None,
        }).eq("attempt_id", str(attempt_id)).execute())
        return self.ensure_daily_learning_evidence(attempt_id)

    def complete_custom_attempt(
        self, attempt_id: str, answers: Sequence[int], timed_seconds: float, *,
        completed_at: datetime | None = None,
    ) -> AttemptRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.daily_mode == "Multiplication":
            raise ValueError("Multiplication Daily attempts must use complete_full_attempt().")
        if attempt.completed_at is not None:
            return self.ensure_daily_learning_evidence(attempt_id)
        questions = list(attempt.custom_questions)
        values = [int(value) for value in answers]
        if len(questions) != 10 or len(values) != 10:
            raise ValueError("An alternate Daily completion must contain exactly 10 questions and answers.")
        seconds = float(timed_seconds)
        if not 0.1 <= seconds <= 3600:
            raise ValueError("Timed sprint duration is outside the allowed range.")
        when = completed_at or utc_now()
        started = when - timedelta(seconds=seconds)
        correct_count = sum(
            int(value) == int(question.get("correct_answer"))
            for question, value in zip(questions, values)
        )
        _retry_transient(lambda: self.client.table("daily_attempts").update({
            "timed_started_at": started.isoformat(),
            "completed_at": when.isoformat(),
            "correct_count": correct_count,
            "timed_seconds": round(seconds, 3),
            "custom_answers": values,
            "learning_evidence_applied_at": None,
        }).eq("attempt_id", str(attempt_id)).execute())
        return self.ensure_daily_learning_evidence(attempt_id)

    def ensure_daily_learning_evidence(self, attempt_id: str) -> AttemptRecord:
        """Apply or repair Daily mastery/progress evidence exactly once in effect.

        The official Daily score continues to use the student's final answers.
        Teacher mastery evidence uses the first submitted answer for each fact.
        A completion marker is written only after mastery/progress succeeds, so a
        network interruption after the official attempt save can repair itself.
        """
        attempt = self.get_attempt(attempt_id)
        if attempt.completed_at is None or attempt.learning_evidence_applied_at is not None:
            return attempt
        if attempt.daily_mode != "Multiplication":
            self.ensure_alternate_followup_state(attempt_id)
            _retry_transient(lambda: self.client.table("daily_attempts").update({
                "learning_evidence_applied_at": utc_now().isoformat(),
            }).eq("attempt_id", str(attempt_id)).is_("learning_evidence_applied_at", "null").execute())
            return self.get_attempt(attempt_id)
        saved = self.get_answers(attempt_id)
        if len(saved) != 10:
            raise FactStoreError("Daily evidence repair requires all 10 saved answers.")
        when = attempt.completed_at
        # Batch all ten facts so a class finishing together does not create
        # ~20 mastery database calls per student. The batch updater is also
        # timestamp-idempotent, which makes this repair path safe to retry.
        self.record_mastery_evidence_batch(
            attempt.student_id,
            [
                (
                    Fact(a=answer.a, b=answer.b, tier="core"),
                    bool(answer.first_correct if answer.first_correct is not None else answer.correct),
                    answer.response_seconds,
                    when,
                )
                for answer in saved
            ],
        )
        self.get_or_create_learning_progress(attempt.student_id, attempt.challenge_id)
        if int(attempt.correct_count or 0) == 10:
            self.mark_fix_complete(attempt.student_id, attempt.challenge_id)
        _retry_transient(lambda: self.client.table("daily_attempts").update({
            "learning_evidence_applied_at": utc_now().isoformat(),
        }).eq("attempt_id", str(attempt_id)).is_("learning_evidence_applied_at", "null").execute())
        return self.get_attempt(attempt_id)

    # ----- Alternate Daily follow-up foundation (v2.17) -----
    def get_or_create_alternate_learning_progress(
        self, student_id: str, challenge_id: str, daily_mode: str
    ) -> AlternateLearningProgressRecord:
        mode = str(daily_mode or "")
        if mode not in ALT_MODES:
            raise ValueError("Alternate learning progress requires an alternate Daily 10 mode.")
        def _load_progress_row():
            return self.client.table("alternate_learning_progress").select("*") \
                .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).limit(1).execute()

        row = _first(_retry_transient(_load_progress_row))
        if row is None:
            payload = {
                "student_id": str(student_id), "challenge_id": str(challenge_id),
                "daily_mode": mode, "focus_plan": [],
            }
            # Inserts need special retry handling: if the response is lost after
            # Supabase commits, a blind retry can hit the primary-key constraint.
            # Re-read after either a transient or duplicate response, and retry the
            # insert once only when the row genuinely never arrived.
            for create_try in range(2):
                try:
                    row = _first(_execute_returning(
                        self.client.table("alternate_learning_progress").insert(payload)
                    ))
                except Exception as exc:
                    if not (_is_unique(exc) or _is_transient_http_error(exc)):
                        raise
                    row = _first(_retry_transient(_load_progress_row))
                    if row is not None:
                        break
                    if _is_unique(exc) or create_try >= 1:
                        break
                    continue
                if row is None:
                    row = _first(_retry_transient(_load_progress_row))
                if row is not None:
                    break
        if row is None:
            raise FactStoreError("Could not create today's follow-up progress.")
        record = _alternate_learning(row)
        if record.daily_mode != mode:
            raise FactStoreError("Stored follow-up mode does not match the student's Daily attempt.")
        return record

    def get_alternate_learning_progress(
        self, student_id: str, challenge_id: str, daily_mode: str | None = None
    ) -> AlternateLearningProgressRecord | None:
        row = _first(_retry_transient(lambda: (
            self.client.table("alternate_learning_progress").select("*")
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).limit(1).execute()
        )))
        if row is None:
            return None if daily_mode is None else self.get_or_create_alternate_learning_progress(
                student_id, challenge_id, daily_mode
            )
        return _alternate_learning(row)

    def class_alternate_learning_progress(
        self, class_id: str, challenge_id: str, *, students: Sequence[StudentRecord] | None = None
    ) -> dict[str, AlternateLearningProgressRecord]:
        students = list(students) if students is not None else self.list_students(class_id)
        ids = [student.student_id for student in students]
        if not ids:
            return {}
        rows = _rows(_retry_transient(lambda: (
            self.client.table("alternate_learning_progress").select("*")
            .eq("challenge_id", str(challenge_id)).in_("student_id", ids).execute()
        )))
        return {str(row["student_id"]): _alternate_learning(row) for row in rows}

    def alternate_learning_activity_rows(
        self, student_id: str, challenge_id: str, activity_type: str | None = None
    ) -> list[AlternateLearningEventRecord]:
        def _load_activity_rows():
            query = (
                self.client.table("alternate_learning_events").select("*")
                .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id))
            )
            if activity_type is not None:
                query = query.eq("activity_type", str(activity_type))
            return query.order("created_at").order("activity_index").execute()

        rows = _rows(_retry_transient(_load_activity_rows))
        return [_alternate_event(row) for row in rows]

    def _upsert_alternate_events(self, payloads: Sequence[Mapping]) -> list[AlternateLearningEventRecord]:
        if not payloads:
            return []
        rows = _rows(_retry_transient(lambda: _execute_returning(
            self.client.table("alternate_learning_events")
            .upsert([dict(item) for item in payloads], on_conflict="client_event_id")
        )))
        return [_alternate_event(row) for row in rows]

    def mark_alternate_fix_complete(
        self, student_id: str, challenge_id: str, daily_mode: str
    ) -> AlternateLearningProgressRecord:
        progress = self.get_or_create_alternate_learning_progress(student_id, challenge_id, daily_mode)
        if progress.fix_completed_at is None:
            now = utc_now().isoformat()
            _retry_transient(lambda: (
                self.client.table("alternate_learning_progress")
                .update({"fix_completed_at": now, "updated_at": now})
                .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).execute()
            ))
        return self.get_or_create_alternate_learning_progress(student_id, challenge_id, daily_mode)

    def set_alternate_focus_plan(
        self, student_id: str, challenge_id: str, daily_mode: str, plan: Sequence[Mapping]
    ) -> AlternateLearningProgressRecord:
        progress = self.get_or_create_alternate_learning_progress(student_id, challenge_id, daily_mode)
        if progress.focus_plan:
            return progress
        items = [dict(item) for item in plan]
        if len(items) != ALT_FOCUS_SESSION_LENGTH:
            raise ValueError("Alternate Focus Practice needs exactly 8 questions.")
        for item in items:
            identity = skill_identity_for_question(item, None if daily_mode == "Mixed" else daily_mode)
            if daily_mode != "Mixed" and identity.domain != daily_mode:
                raise ValueError("Alternate Focus plan contains a question from the wrong domain.")
            int(item.get("correct_answer"))
        now = utc_now().isoformat()
        _retry_transient(lambda: (
            self.client.table("alternate_learning_progress")
            .update({"focus_plan": items, "updated_at": now})
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).execute()
        ))
        return self.get_or_create_alternate_learning_progress(student_id, challenge_id, daily_mode)

    def recent_alternate_learning_events(
        self, student_id: str, *, limit: int = 500
    ) -> list[AlternateLearningEventRecord]:
        count = max(1, min(2000, int(limit)))
        rows = _rows(_retry_transient(lambda: (
            self.client.table("alternate_learning_events").select("*")
            .eq("student_id", str(student_id)).order("created_at", desc=True).range(0, count - 1).execute()
        )))
        return [_alternate_event(row) for row in rows]

    def mark_alternate_focus_complete(
        self, student_id: str, challenge_id: str, daily_mode: str
    ) -> AlternateLearningProgressRecord:
        progress = self.get_or_create_alternate_learning_progress(student_id, challenge_id, daily_mode)
        if progress.fix_completed_at is None:
            raise ValueError("Finish Fix Your Misses before Focus Practice.")
        if progress.completed_at is None:
            now = utc_now().isoformat()
            _retry_transient(lambda: (
                self.client.table("alternate_learning_progress")
                .update({"focus_completed_at": now, "completed_at": now, "updated_at": now})
                .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).execute()
            ))
        return self.get_or_create_alternate_learning_progress(student_id, challenge_id, daily_mode)

    def ensure_alternate_followup_state(self, attempt_id: str) -> AlternateLearningProgressRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.daily_mode == "Multiplication" or attempt.daily_mode not in ALT_MODES:
            raise ValueError("Alternate follow-up is only available for alternate Daily 10 modes.")
        if attempt.completed_at is None:
            raise AttemptNotStarted("Complete the Daily 10 before follow-up practice.")
        questions = list(attempt.custom_questions or ())
        answers = list(attempt.custom_answers or ())
        if len(questions) != 10 or len(answers) != 10:
            raise FactStoreError("Alternate follow-up requires all 10 saved Daily questions and answers.")

        payloads = []
        for row in daily_evidence_rows(questions, answers, default_domain=None if attempt.daily_mode == "Mixed" else attempt.daily_mode):
            index = int(row["question_number"])
            payloads.append({
                "student_id": attempt.student_id, "challenge_id": attempt.challenge_id,
                "attempt_id": attempt.attempt_id, "daily_mode": attempt.daily_mode,
                "activity_type": "daily", "activity_index": index, "domain": row["domain"],
                "skill_key": row["skill_key"], "skill_label": row["skill_label"],
                "item_key": row["item_key"], "prompt": row["prompt"],
                "student_answer": int(row["student_answer"]), "correct_answer": int(row["correct_answer"]),
                "correct": bool(row["correct"]), "is_retry": False, "response_seconds": None,
                "created_at": attempt.completed_at.isoformat(),
                "client_event_id": f"alt-daily:{attempt.attempt_id}:{index}",
            })
        self._upsert_alternate_events(payloads)
        progress = self.get_or_create_alternate_learning_progress(
            attempt.student_id, attempt.challenge_id, attempt.daily_mode
        )
        missed = missed_question_items(questions, answers, default_domain=None if attempt.daily_mode == "Mixed" else attempt.daily_mode)
        if not missed:
            return self.mark_alternate_fix_complete(attempt.student_id, attempt.challenge_id, attempt.daily_mode)
        fixed_rows = self.alternate_learning_activity_rows(attempt.student_id, attempt.challenge_id, "fix_miss")
        corrected = {int(row.activity_index) for row in fixed_rows if row.correct}
        if {int(item["question_number"]) for item in missed}.issubset(corrected):
            return self.mark_alternate_fix_complete(attempt.student_id, attempt.challenge_id, attempt.daily_mode)
        return progress

    def record_alternate_fix_batch(
        self, attempt_id: str, corrections: Sequence[Mapping]
    ) -> AlternateLearningProgressRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.daily_mode == "Multiplication" or attempt.daily_mode not in ALT_MODES:
            raise ValueError("Alternate Fix Your Misses cannot write to a Multiplication Daily.")
        if attempt.completed_at is None:
            raise AttemptNotStarted("Complete the Daily 10 before Fix Your Misses.")
        questions = list(attempt.custom_questions or ())
        answers = list(attempt.custom_answers or ())
        missed = {int(item["question_number"]): item for item in missed_question_items(
            questions, answers, default_domain=None if attempt.daily_mode == "Mixed" else attempt.daily_mode
        )}
        submitted: dict[int, int] = {}
        for item in corrections:
            index = int(item.get("question_number"))
            if index in submitted:
                raise ValueError("Each missed question may be corrected once in a saved Fix batch.")
            submitted[index] = int(item.get("student_answer"))
        if set(submitted) != set(missed):
            raise ValueError("Fix Your Misses must correct every missed Daily question.")
        payloads = []
        for index, value in submitted.items():
            item = missed[index]
            expected = int(item["correct_answer"])
            if value != expected:
                raise ValueError("Fix Your Misses can only complete after every missed question is corrected.")
            payloads.append({
                "student_id": attempt.student_id, "challenge_id": attempt.challenge_id,
                "attempt_id": attempt.attempt_id, "daily_mode": attempt.daily_mode,
                "activity_type": "fix_miss", "activity_index": index, "domain": item["domain"],
                "skill_key": item["skill_key"], "skill_label": item["skill_label"],
                "item_key": item["item_key"], "prompt": item["prompt"],
                "student_answer": value, "correct_answer": expected, "correct": True,
                "is_retry": True, "response_seconds": None, "created_at": utc_now().isoformat(),
                "client_event_id": f"alt-fix:{attempt.attempt_id}:{index}",
            })
        self._upsert_alternate_events(payloads)
        return self.ensure_alternate_followup_state(attempt_id)

    def record_alternate_focus_batch(
        self, attempt_id: str, events: Sequence[Mapping]
    ) -> AlternateLearningProgressRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.daily_mode == "Multiplication" or attempt.daily_mode not in ALT_MODES:
            raise ValueError("Alternate Focus Practice cannot write to a Multiplication Daily.")
        progress = self.get_or_create_alternate_learning_progress(
            attempt.student_id, attempt.challenge_id, attempt.daily_mode
        )
        if progress.fix_completed_at is None:
            raise AttemptNotStarted("Finish Fix Your Misses before Focus Practice.")
        plan = list(progress.focus_plan or ())
        if len(plan) != ALT_FOCUS_SESSION_LENGTH:
            raise FactStoreError("Alternate Focus Practice plan is missing or incomplete.")

        existing = self.alternate_learning_activity_rows(attempt.student_id, attempt.challenge_id, "focus")
        existing_ids = {str(row.client_event_id) for row in existing if row.client_event_id}
        has_first = {int(row.activity_index) for row in existing if not row.is_retry}
        submitted_by_index: dict[int, list[Mapping]] = {}
        for raw in events:
            client_id = str(raw.get("client_event_id") or "").strip()
            if not client_id:
                raise ValueError("Focus Practice event is missing its save id.")
            if client_id in existing_ids:
                continue
            index = int(raw.get("activity_index"))
            if not 1 <= index <= ALT_FOCUS_SESSION_LENGTH:
                raise ValueError("Focus Practice question number is outside the plan.")
            submitted_by_index.setdefault(index, []).append(raw)

        payloads = []
        for index, batch in submitted_by_index.items():
            item = plan[index - 1]
            identity = skill_identity_for_question(item, None if attempt.daily_mode == "Mixed" else attempt.daily_mode)
            expected = int(item.get("correct_answer"))
            first_exists = index in has_first
            for position, raw in enumerate(batch):
                is_retry = bool(raw.get("is_retry"))
                if not first_exists and position == 0 and is_retry:
                    raise ValueError("Focus Practice must save the first try before a retry.")
                if first_exists and not is_retry:
                    raise ValueError("Focus Practice cannot save a second first try for one question.")
                if position > 0 and not is_retry:
                    raise ValueError("Only the first Focus attempt may be a first try.")
                value = int(raw.get("student_answer"))
                seconds = raw.get("response_seconds")
                seconds = None if seconds is None else max(0.0, float(seconds))
                payloads.append({
                    "student_id": attempt.student_id, "challenge_id": attempt.challenge_id,
                    "attempt_id": attempt.attempt_id, "daily_mode": attempt.daily_mode,
                    "activity_type": "focus", "activity_index": index, "domain": identity.domain,
                    "skill_key": identity.skill_key, "skill_label": identity.skill_label,
                    "item_key": identity.item_key, "prompt": str(item.get("prompt") or ""),
                    "student_answer": value, "correct_answer": expected, "correct": value == expected,
                    "is_retry": is_retry, "response_seconds": seconds, "created_at": utc_now().isoformat(),
                    "client_event_id": str(raw.get("client_event_id")),
                })
        self._upsert_alternate_events(payloads)

        rows = self.alternate_learning_activity_rows(attempt.student_id, attempt.challenge_id, "focus")
        complete = True
        for index in range(1, ALT_FOCUS_SESSION_LENGTH + 1):
            slot = [row for row in rows if int(row.activity_index) == index]
            first = next((row for row in slot if not row.is_retry), None)
            if first is None or (not first.correct and not any(row.is_retry and row.correct for row in slot)):
                complete = False
                break
        if complete:
            return self.mark_alternate_focus_complete(attempt.student_id, attempt.challenge_id, attempt.daily_mode)
        return self.get_or_create_alternate_learning_progress(attempt.student_id, attempt.challenge_id, attempt.daily_mode)

    def rebuild_mastery(self, student_id: str) -> list[MasterySnapshot]:
        attempt_rows = _rows(
            self.client.table("daily_attempts").select("attempt_id,completed_at,daily_mode")
            .eq("student_id", str(student_id)).eq("daily_mode", "Multiplication")
            .not_.is_("completed_at", "null").range(0, 4999).execute()
        )
        attempt_ids = [str(row["attempt_id"]) for row in attempt_rows]
        daily_rows = []
        if attempt_ids:
            daily_rows = _rows(
                self.client.table("daily_answers").select("a,b,correct,first_correct,response_seconds,submitted_at")
                .in_("attempt_id", attempt_ids).range(0, 9999).execute()
            )
        focus_rows = _rows(
            self.client.table("practice_answers").select("a,b,correct,response_seconds,created_at")
            .eq("student_id", str(student_id)).eq("activity_type", "focus")
            .eq("is_retry", False).range(0, 9999).execute()
        )
        events = []
        for row in daily_rows:
            a, b = int(row["a"]), int(row["b"])
            if max(a, b) <= 10:
                events.append((
                    _dt(row.get("submitted_at")) or utc_now(), a, b,
                    bool(row.get("first_correct") if row.get("first_correct") is not None else row["correct"]),
                    None if row.get("response_seconds") is None else float(row["response_seconds"]),
                ))
        for row in focus_rows:
            a, b = int(row["a"]), int(row["b"])
            if max(a, b) <= 10:
                events.append((_dt(row.get("created_at")) or utc_now(), a, b, bool(row["correct"]), None if row.get("response_seconds") is None else float(row["response_seconds"])))
        events.sort(key=lambda item: item[0])
        snapshots: dict[tuple[int, int], MasterySnapshot] = {}
        for when, a, b, correct, seconds in events:
            key = canonical_pair(a, b)
            snapshots[key] = update_snapshot(
                snapshots.get(key), a=key[0], b=key[1], correct=correct,
                response_seconds=seconds, practiced_at=when,
            )
        self.client.table("student_fact_mastery").delete().eq("student_id", str(student_id)).execute()
        if snapshots:
            payloads = []
            for row in snapshots.values():
                payloads.append({
                    "student_id": str(student_id), "a": row.a, "b": row.b,
                    "evidence_count": row.evidence_count, "correct_count": row.correct_count,
                    "ema_accuracy": row.ema_accuracy, "ema_seconds": row.ema_seconds,
                    "correct_streak": row.correct_streak, "mastery_status": row.status,
                    "last_practiced_at": row.last_practiced_at.isoformat() if row.last_practiced_at else None,
                    "updated_at": utc_now().isoformat(),
                })
            self.client.table("student_fact_mastery").insert(payloads).execute()
        return list(snapshots.values())

    def reset_daily_attempt(self, student_id: str, challenge_id: str) -> bool:
        attempt = self.get_attempt_for_student(student_id, challenge_id)
        if attempt is None:
            return False
        (
            self.client.table("practice_answers").delete()
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id))
            .in_("activity_type", ["fix_miss", "focus"]).execute()
        )
        (
            self.client.table("daily_learning_progress").delete()
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).execute()
        )
        _retry_transient(lambda: (
            self.client.table("alternate_learning_events").delete()
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).execute()
        ))
        _retry_transient(lambda: (
            self.client.table("alternate_learning_progress").delete()
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).execute()
        ))
        self.client.table("daily_attempts").delete().eq("attempt_id", attempt.attempt_id).execute()
        self.rebuild_mastery(student_id)
        return True

    def completed_attempts_for_class(
        self, class_id: str, challenge_id: str, *, students: Sequence[StudentRecord] | None = None
    ) -> list[dict]:
        students = list(students) if students is not None else self.list_students(class_id, include_inactive=True)
        if not students:
            return []
        student_map = {student.student_id: student for student in students}
        student_ids = list(student_map)
        rows = _rows(_retry_transient(lambda: (
            self.client.table("daily_attempts")
            .select("attempt_id,student_id,correct_count,timed_seconds,completed_at")
            .eq("challenge_id", str(challenge_id))
            .in_("student_id", student_ids)
            .not_.is_("completed_at", "null")
            .execute()
        )))
        result = []
        for row in rows:
            student = student_map.get(str(row["student_id"]))
            if student is None:
                continue
            result.append({
                "student_id": student.student_id,
                "nickname": student.nickname,
                "correct_count": int(row.get("correct_count") or 0),
                "timed_seconds": float(row.get("timed_seconds") or 0.0),
                "completed_at": _dt(row.get("completed_at")) or utc_now(),
                "attempt_id": str(row["attempt_id"]),
            })
        result.sort(key=lambda row: (-row["correct_count"], row["timed_seconds"], row["completed_at"]))
        return result

    def leaderboard(self, class_id: str, challenge_id: str, *, limit: int = 10) -> list[dict]:
        rows = self.completed_attempts_for_class(class_id, challenge_id)[:limit]
        return [dict(row, rank=index) for index, row in enumerate(rows, start=1)]

    def daily_status(
        self, class_id: str, challenge_id: str, *, students: Sequence[StudentRecord] | None = None
    ) -> list[dict]:
        students = list(students) if students is not None else self.list_students(class_id)
        if not students:
            return []
        student_map = {student.student_id: student for student in students}
        rows = _rows(
            self.client.table("daily_attempts")
            .select("attempt_id,student_id,timed_started_at,completed_at,correct_count,timed_seconds")
            .eq("challenge_id", str(challenge_id))
            .in_("student_id", list(student_map))
            .execute()
        )
        attempt_map = {str(row["student_id"]): row for row in rows}
        result = []
        for student in students:
            row = attempt_map.get(student.student_id)
            result.append({
                "student_id": student.student_id,
                "nickname": student.nickname,
                "status": (
                    "Complete" if row and row.get("completed_at") else
                    "In progress" if row else
                    "Not started"
                ),
                "correct_count": None if not row or row.get("correct_count") is None else int(row["correct_count"]),
                "timed_seconds": None if not row or row.get("timed_seconds") is None else float(row["timed_seconds"]),
                "attempt_id": str(row["attempt_id"]) if row else None,
                "completed_at": _dt(row.get("completed_at")) if row else None,
            })
        return result


    # ----- Adaptive learning / Practice -----
    def record_mastery_evidence(
        self, student_id: str, fact: Fact, correct: bool, *,
        response_seconds: float | None = None, practiced_at: datetime | None = None,
    ) -> MasterySnapshot:
        a, b = canonical_pair(fact.a, fact.b)
        if not (2 <= a <= b <= 10):
            raise ValueError("The persistent mastery map covers core 2s-10s facts only.")
        existing = _first(
            self.client.table("student_fact_mastery").select("*")
            .eq("student_id", str(student_id)).eq("a", a).eq("b", b).limit(1).execute()
        )
        old = _mastery(existing) if existing else None
        updated = update_snapshot(
            old, a=a, b=b, correct=bool(correct), response_seconds=response_seconds,
            practiced_at=practiced_at or utc_now(),
        )
        payload = {
            "student_id": str(student_id), "a": a, "b": b,
            "evidence_count": updated.evidence_count,
            "correct_count": updated.correct_count,
            "ema_accuracy": updated.ema_accuracy,
            "ema_seconds": updated.ema_seconds,
            "correct_streak": updated.correct_streak,
            "mastery_status": updated.status,
            "last_practiced_at": updated.last_practiced_at.isoformat() if updated.last_practiced_at else None,
            "updated_at": utc_now().isoformat(),
        }
        self.client.table("student_fact_mastery").upsert(
            payload, on_conflict="student_id,a,b"
        ).execute()
        return updated

    def record_mastery_evidence_batch(
        self, student_id: str, evidence: Sequence[tuple[Fact, bool, float | None, datetime]]
    ) -> list[MasterySnapshot]:
        """Update a Daily's mastery evidence in two requests instead of ~20.

        This matters in a classroom because many students finish the Daily within
        the same minute. The calculation is identical to record_mastery_evidence;
        only the database round-trips are batched.
        """
        usable = [item for item in evidence if max(item[0].key) <= 10]
        if not usable:
            return []
        existing_rows = _rows(_retry_transient(lambda: (
            self.client.table("student_fact_mastery").select("*")
            .eq("student_id", str(student_id)).execute()
        )))
        current = {(int(row["a"]), int(row["b"])): _mastery(row) for row in existing_rows}
        changed: dict[tuple[int, int], MasterySnapshot] = {}
        for fact, correct, response_seconds, practiced_at in usable:
            a, b = canonical_pair(fact.a, fact.b)
            old = changed.get((a, b)) or current.get((a, b))
            # Focus mastery is applied as one batch when the 8-item session ends.
            # If the completion response is interrupted and Streamlit retries, do
            # not count the same stored Practice evidence twice.
            if old is not None and old.last_practiced_at is not None and practiced_at <= old.last_practiced_at:
                continue
            updated = update_snapshot(
                old, a=a, b=b, correct=bool(correct), response_seconds=response_seconds,
                practiced_at=practiced_at,
            )
            changed[(a, b)] = updated
        if not changed:
            return []
        payloads = []
        for (a, b), updated in changed.items():
            payloads.append({
                "student_id": str(student_id), "a": a, "b": b,
                "evidence_count": updated.evidence_count,
                "correct_count": updated.correct_count,
                "ema_accuracy": updated.ema_accuracy,
                "ema_seconds": updated.ema_seconds,
                "correct_streak": updated.correct_streak,
                "mastery_status": updated.status,
                "last_practiced_at": updated.last_practiced_at.isoformat() if updated.last_practiced_at else None,
                "updated_at": utc_now().isoformat(),
            })
        _retry_transient(lambda: self.client.table("student_fact_mastery").upsert(
            payloads, on_conflict="student_id,a,b"
        ).execute())
        return list(changed.values())

    def get_mastery(self, student_id: str) -> list[MasterySnapshot]:
        rows = _rows(
            _retry_transient(lambda: self.client.table("student_fact_mastery").select("*")
            .eq("student_id", str(student_id)).execute())
        )
        if rows:
            return [_mastery(row) for row in rows]
        # Existing v1 Daily history can seed v2 automatically; there is still
        # no placement test and no invented evidence.
        prior_daily = _first(_retry_transient(lambda: (
            self.client.table("daily_attempts").select("attempt_id")
            .eq("student_id", str(student_id)).eq("daily_mode", "Multiplication")
            .not_.is_("completed_at", "null").limit(1).execute()
        )))
        prior_focus = _first(_retry_transient(lambda: (
            self.client.table("practice_answers").select("practice_answer_id")
            .eq("student_id", str(student_id)).eq("activity_type", "focus")
            .eq("is_retry", False).limit(1).execute()
        )))
        if prior_daily or prior_focus:
            return self.rebuild_mastery(student_id)
        return []

    def mastery_summary(self, student_id: str) -> dict[str, int]:
        return mastery_counts(self.get_mastery(student_id))

    def class_mastery_summary(self, class_id: str) -> list[dict]:
        students = self.list_students(class_id)
        student_ids = [student.student_id for student in students]
        rows = []
        if student_ids:
            rows = _rows(
                self.client.table("student_fact_mastery")
                .select("student_id,a,b,mastery_status")
                .in_("student_id", student_ids).range(0, 4999).execute()
            )
        by_key = {(str(row["student_id"]), int(row["a"]), int(row["b"])): str(row.get("mastery_status") or "Unknown") for row in rows}
        result = []
        for a in range(2, 11):
            for b in range(a, 11):
                counts = {"Fluent": 0, "Building": 0, "Focus": 0, "Unknown": 0}
                for student in students:
                    counts[by_key.get((student.student_id, a, b), "Unknown")] += 1
                result.append({"a": a, "b": b, "fact": f"{a} × {b}", **counts, "students": len(students)})
        return result

    def class_mastery_detail(
        self, class_id: str, *, students: Sequence[StudentRecord] | None = None
    ) -> dict[str, list[MasterySnapshot]]:
        """Return all persisted mastery rows for a class in one database read."""
        students = list(students) if students is not None else self.list_students(class_id)
        student_ids = [student.student_id for student in students]
        result: dict[str, list[MasterySnapshot]] = {student_id: [] for student_id in student_ids}
        if not student_ids:
            return result
        rows = _rows(_retry_transient(lambda: self.client.table("student_fact_mastery")
            .select("*").in_("student_id", student_ids).range(0, 4999).execute()))
        for row in rows:
            sid = str(row.get("student_id"))
            if sid in result:
                result[sid].append(_mastery(row))
        return result

    def get_or_create_learning_progress(self, student_id: str, challenge_id: str) -> LearningProgressRecord:
        row = _first(_retry_transient(lambda: (
            self.client.table("daily_learning_progress").select("*")
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).limit(1).execute()
        )))
        if row is None:
            try:
                row = _first(
                    _execute_returning(self.client.table("daily_learning_progress").insert({
                        "student_id": str(student_id), "challenge_id": str(challenge_id), "focus_plan": []
                    }))
                )
            except Exception as exc:
                # If the insert landed but its response was lost—or another rerun created it—re-read safely.
                if not (_is_unique(exc) or _is_transient_http_error(exc)):
                    raise
                row = _first(_retry_transient(lambda: (
                    self.client.table("daily_learning_progress").select("*")
                    .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).limit(1).execute()
                )))
        if row is None:
            raise FactStoreError("Could not create today's learning progress.")
        return _learning(row)

    def get_learning_progress(self, student_id: str, challenge_id: str) -> LearningProgressRecord:
        return self.get_or_create_learning_progress(student_id, challenge_id)

    def set_focus_plan(self, student_id: str, challenge_id: str, facts: Sequence[Fact]) -> LearningProgressRecord:
        progress = self.get_or_create_learning_progress(student_id, challenge_id)
        if progress.focus_plan:
            return progress
        payload = {
            "focus_plan": [fact.as_dict() for fact in facts],
            "updated_at": utc_now().isoformat(),
        }
        row = _first(_retry_transient(lambda: (
            _execute_returning(self.client.table("daily_learning_progress").update(payload)
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)))
        )))
        return _learning(row) if row else self.get_or_create_learning_progress(student_id, challenge_id)

    def mark_fix_complete(self, student_id: str, challenge_id: str) -> LearningProgressRecord:
        progress = self.get_or_create_learning_progress(student_id, challenge_id)
        if progress.fix_completed_at is None:
            now = utc_now().isoformat()
            (
                self.client.table("daily_learning_progress")
                .update({"fix_completed_at": now, "updated_at": now})
                .eq("student_id", str(student_id))
                .eq("challenge_id", str(challenge_id))
                .execute()
            )
        return self.get_or_create_learning_progress(student_id, challenge_id)

    def mark_focus_complete(self, student_id: str, challenge_id: str) -> LearningProgressRecord:
        progress = self.get_or_create_learning_progress(student_id, challenge_id)
        if progress.completed_at is None:
            now = utc_now().isoformat()
            self.client.table("daily_learning_progress").update({
                "focus_completed_at": now, "completed_at": now, "updated_at": now
            }).eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).execute()
        return self.get_or_create_learning_progress(student_id, challenge_id)

    def record_practice(
        self, student_id: str | None, focus: str, fact: Fact, student_answer: int, *,
        response_seconds: float | None = None, challenge_id: str | None = None,
        activity_type: str = "free_practice", activity_index: int | None = None,
        is_retry: bool = False, count_for_mastery: bool = False,
    ) -> PracticeRecord:
        focus_first_try = bool(
            student_id is not None and challenge_id is not None and activity_type == "focus"
            and activity_index is not None and not is_retry
        )
        payload = {
            "student_id": str(student_id) if student_id else None,
            "focus": str(focus),
            "a": fact.a, "b": fact.b,
            "student_answer": int(student_answer),
            "correct_answer": fact.product,
            "correct": int(student_answer) == fact.product,
            "response_seconds": None if response_seconds is None else round(float(response_seconds), 3),
            "challenge_id": str(challenge_id) if challenge_id else None,
            "activity_type": str(activity_type),
            "activity_index": activity_index,
            "is_retry": bool(is_retry),
        }
        try:
            row = _first(_execute_returning(self.client.table("practice_answers").insert(payload)))
        except Exception as exc:
            # v2 created a unique index for first-try Focus slots. Normal submissions
            # therefore need only one INSERT; a duplicate browser submission falls
            # back to a read instead of pre-reading every answer.
            if not (focus_first_try and (_is_unique(exc) or _is_transient_http_error(exc))):
                raise
            row = _first(_retry_transient(lambda: (
                self.client.table("practice_answers").select("*")
                .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id))
                .eq("activity_type", "focus").eq("activity_index", int(activity_index))
                .eq("is_retry", False).limit(1).execute()
            )))
            if row is None:
                raise
        if row is None:
            raise FactStoreError("Could not save Practice answer.")
        record = _practice(row)
        if count_for_mastery and student_id is not None and not is_retry and max(fact.key) <= 10:
            self.record_mastery_evidence(
                student_id, fact, record.correct, response_seconds=response_seconds, practiced_at=record.created_at
            )
        return record

    def record_practice_batch(
        self, student_id: str, focus: str, challenge_id: str, activity_type: str, events: Sequence[Mapping]
    ) -> list[PracticeRecord]:
        """Save one browser-local guided session in a single idempotent request.

        Each browser event carries a deterministic client_event_id. The unique
        database key lets a retried network request safely upsert the same batch
        without duplicating teacher evidence or mastery inputs.
        """
        payloads = []
        for event in events:
            fact = Fact(int(event["a"]), int(event["b"]), "guided")
            answer = int(event["student_answer"])
            event_id = str(event.get("client_event_id") or "").strip()
            if not event_id:
                raise ValueError("Guided Practice event is missing its client event ID.")
            payloads.append({
                "student_id": str(student_id),
                "focus": str(focus),
                "a": fact.a, "b": fact.b,
                "student_answer": answer,
                "correct_answer": fact.product,
                "correct": answer == fact.product,
                "response_seconds": round(max(0.0, float(event.get("response_seconds") or 0.0)), 3),
                "challenge_id": str(challenge_id),
                "activity_type": str(activity_type),
                "activity_index": int(event["activity_index"]),
                "is_retry": bool(event.get("is_retry")),
                "client_event_id": event_id[:180],
            })
        if not payloads:
            return []
        response = _retry_transient(lambda: _execute_returning(
            self.client.table("practice_answers")
            .upsert(payloads, on_conflict="client_event_id")
        ))
        return [_practice(row) for row in _rows(response)]

    def learning_activity_rows(self, student_id: str, challenge_id: str, activity_type: str) -> list[PracticeRecord]:
        rows = _rows(
            _retry_transient(lambda: self.client.table("practice_answers").select("*")
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id))
            .eq("activity_type", str(activity_type)).order("activity_index").order("created_at").execute())
        )
        return [_practice(row) for row in rows]

    def practice_summary(self, student_id: str) -> dict[str, int]:
        rows = _rows(
            self.client.table("practice_answers").select("correct")
            .eq("student_id", str(student_id)).execute()
        )
        return {"attempts": len(rows), "correct": sum(bool(row.get("correct")) for row in rows)}

    @staticmethod
    def _normalize_override(family: int | None) -> int | None:
        if family is None:
            return None
        value = int(family)
        if not 2 <= value <= 10:
            raise ValueError("Focus override must be 2 through 10 or Automatic.")
        return value

    # ----- Quick Warm-Up -----
    def get_warmup_set(self, class_id: str, warmup_date: date | str) -> WarmupSetRecord | None:
        date_key = warmup_date.isoformat() if isinstance(warmup_date, date) else str(warmup_date)
        row = _first(_retry_transient(lambda: self.client.table("warmup_sets")
            .select("*").eq("class_id", str(class_id)).eq("warmup_date", date_key).limit(1).execute()))
        return None if row is None else _warmup_set(row)

    def warmup_set_locked(self, warmup_set_id: str) -> bool:
        rows = _rows(_retry_transient(lambda: self.client.table("warmup_answers")
            .select("student_id").eq("warmup_set_id", str(warmup_set_id)).execute()))
        if not rows:
            return False
        student_ids = sorted({str(row["student_id"]) for row in rows})
        real_rows = _rows(_retry_transient(lambda: self.client.table("students")
            .select("student_id").in_("student_id", student_ids).eq("is_test", False).limit(1).execute()))
        return bool(real_rows)

    def save_warmup_set(self, class_id: str, warmup_date: date | str, question_one: Mapping, question_two: Mapping) -> WarmupSetRecord:
        date_key = warmup_date.isoformat() if isinstance(warmup_date, date) else str(warmup_date)
        existing = self.get_warmup_set(class_id, date_key)
        if existing is not None and self.warmup_set_locked(existing.warmup_set_id):
            raise FactStoreError("This Warm-Up is locked because a student has already answered it.")
        if existing is not None:
            # Only sandbox responses can exist when the set is not locked. Clear
            # them so an edited trial can be tested from the beginning.
            _retry_transient(lambda: self.client.table("warmup_answers").delete()
                .eq("warmup_set_id", existing.warmup_set_id).execute())
        payload = {
            "class_id": str(class_id), "warmup_date": date_key,
            "question_one": dict(question_one), "question_two": dict(question_two),
            "updated_at": utc_now().isoformat(),
        }
        _retry_transient(lambda: self.client.table("warmup_sets").upsert(
            payload, on_conflict="class_id,warmup_date"
        ).execute())
        record = self.get_warmup_set(class_id, date_key)
        if record is None:
            raise FactStoreError("Could not load the saved Warm-Up.")
        return record

    def delete_warmup_set(self, class_id: str, warmup_date: date | str) -> None:
        date_key = warmup_date.isoformat() if isinstance(warmup_date, date) else str(warmup_date)
        existing = self.get_warmup_set(class_id, date_key)
        if existing is None:
            return
        if self.warmup_set_locked(existing.warmup_set_id):
            raise FactStoreError("This Warm-Up is locked because a student has already answered it.")
        _retry_transient(lambda: self.client.table("warmup_sets").delete()
            .eq("warmup_set_id", existing.warmup_set_id).execute())

    def get_warmup_answers(self, student_id: str, warmup_set_id: str) -> list[WarmupAnswerRecord]:
        rows = _rows(_retry_transient(lambda: self.client.table("warmup_answers").select("*")
            .eq("student_id", str(student_id)).eq("warmup_set_id", str(warmup_set_id))
            .order("question_slot").execute()))
        return [_warmup_answer(row) for row in rows]

    def record_warmup_answer(
        self, *, warmup_set_id: str, student_id: str, class_id: str, warmup_date: date | str,
        question_slot: int, question_type: str, prompt: str, standard_code: str,
        standard_description: str, student_answer: str, correct_answer: str, correct: bool,
    ) -> WarmupAnswerRecord:
        date_key = warmup_date.isoformat() if isinstance(warmup_date, date) else str(warmup_date)
        if getattr(self, "_warmup_retention_date", None) != date_key:
            try:
                self.clear_old_warmup_response_text(date_key)
                self._warmup_retention_date = date_key
            except Exception as exc:
                print(f"[TDFC data] warmup_response_retention_failed type={type(exc).__name__}")
        payload = {
            "warmup_set_id": str(warmup_set_id), "student_id": str(student_id),
            "class_id": str(class_id), "warmup_date": date_key, "question_slot": int(question_slot),
            "question_type": str(question_type), "prompt": str(prompt), "standard_code": str(standard_code),
            "standard_description": str(standard_description), "student_answer": str(student_answer),
            "correct_answer": str(correct_answer), "correct": bool(correct),
        }
        try:
            _retry_transient(lambda: self.client.table("warmup_answers").insert(payload).execute())
        except Exception as exc:
            if not _is_unique(exc):
                raise
        row = _first(_retry_transient(lambda: self.client.table("warmup_answers").select("*")
            .eq("student_id", str(student_id)).eq("warmup_set_id", str(warmup_set_id))
            .eq("question_slot", int(question_slot)).limit(1).execute()))
        if row is None:
            raise FactStoreError("Could not save the Warm-Up answer.")
        return _warmup_answer(row)

    def list_warmup_answers(
        self, start_date: date | str, end_date: date | str, *, class_id: str | None = None, include_test: bool = False
    ) -> list[WarmupAnswerRecord]:
        start_key = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
        end_key = end_date.isoformat() if isinstance(end_date, date) else str(end_date)

        # Standards history can grow beyond Supabase/PostgREST's default
        # per-request row cap. Page deliberately so a full school-year tracker
        # never silently stops at the first 1,000 responses.
        page_size = 1000
        offset = 0
        rows = []
        while True:
            def fetch_page():
                query = self.client.table("warmup_answers").select("*").gte("warmup_date", start_key).lte("warmup_date", end_key)
                if class_id is not None:
                    query = query.eq("class_id", str(class_id))
                return query.order("warmup_date").order("question_slot").range(offset, offset + page_size - 1).execute()

            page = _rows(_retry_transient(fetch_page))
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        records = [_warmup_answer(row) for row in rows]
        if include_test or not records:
            return records
        student_ids = sorted({row.student_id for row in records})
        test_rows = _rows(_retry_transient(lambda: self.client.table("students").select("student_id")
            .in_("student_id", student_ids).eq("is_test", True).range(0, 9999).execute()))
        test_ids = {str(row["student_id"]) for row in test_rows}
        return [row for row in records if row.student_id not in test_ids]

    def clear_old_warmup_response_text(self, before_date: date | str) -> int:
        """Clear prior-day raw student text while preserving correctness/standards evidence."""
        before_key = before_date.isoformat() if isinstance(before_date, date) else str(before_date)
        rows = _rows(_retry_transient(lambda: self.client.table("warmup_answers")
            .select("warmup_answer_id").lt("warmup_date", before_key).neq("student_answer", "").range(0, 9999).execute()))
        if rows:
            _retry_transient(lambda: self.client.table("warmup_answers").update({"student_answer": ""})
                .lt("warmup_date", before_key).neq("student_answer", "").execute())
        return len(rows)

    # ----- AWTRIX classroom clock integration -----
    def get_awtrix_clock_config(self) -> dict | None:
        row = _first(_retry_transient(lambda: (
            self.client.table("awtrix_clock_config")
            .select("block1_class_id,block2_class_id,block3_class_id,token_hash,token_hint,updated_at")
            .eq("config_id", 1)
            .limit(1)
            .execute()
        ), attempts=2))
        if row is None:
            return None
        return {
            "block1_class_id": None if row.get("block1_class_id") is None else str(row.get("block1_class_id")),
            "block2_class_id": None if row.get("block2_class_id") is None else str(row.get("block2_class_id")),
            "block3_class_id": None if row.get("block3_class_id") is None else str(row.get("block3_class_id")),
            "has_token": bool(row.get("token_hash")),
            "token_hint": row.get("token_hint"),
            "updated_at": row.get("updated_at"),
        }

    def save_awtrix_clock_mapping(self, block1_class_id: str, block2_class_id: str, block3_class_id: str) -> None:
        class_ids = [str(block1_class_id), str(block2_class_id), str(block3_class_id)]
        if len(set(class_ids)) != 3:
            raise ValueError("Block 1, Block 2, and Block 3 must map to three different classes.")
        payload = {
            "config_id": 1,
            "block1_class_id": class_ids[0],
            "block2_class_id": class_ids[1],
            "block3_class_id": class_ids[2],
            "updated_at": utc_now().isoformat(),
        }
        _retry_transient(lambda: self.client.table("awtrix_clock_config").upsert(payload, on_conflict="config_id").execute())

    def rotate_awtrix_clock_token(self) -> str:
        token = secrets.token_urlsafe(24)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        payload = {
            "config_id": 1,
            "token_hash": digest,
            "token_hint": token[-6:],
            "updated_at": utc_now().isoformat(),
        }
        _retry_transient(lambda: self.client.table("awtrix_clock_config").upsert(payload, on_conflict="config_id").execute())
        return token

    def awtrix_block_for_class(self, class_id: str) -> int | None:
        cfg = self.get_awtrix_clock_config()
        if not cfg:
            return None
        target = str(class_id)
        for block in (1, 2, 3):
            if cfg.get(f"block{block}_class_id") == target:
                return block
        return None

    def queue_awtrix_top10(self, block_number: int) -> int:
        block = int(block_number)
        if block not in (1, 2, 3):
            raise ValueError("Block number must be 1, 2, or 3.")
        cfg = self.get_awtrix_clock_config()
        if not cfg or not cfg.get(f"block{block}_class_id"):
            raise FactStoreError(f"Block {block} is not mapped to a class yet.")
        if not cfg.get("has_token"):
            raise FactStoreError("The classroom clock token has not been generated yet.")
        row = _first(_execute_returning(self.client.table("awtrix_clock_commands").insert({
            "block_number": block,
            "requested_at": utc_now().isoformat(),
        })))
        if row is None or row.get("command_id") is None:
            raise FactStoreError("The clock command could not be queued.")
        return int(row["command_id"])

    def get_app_setting(self, setting_key: str, default=None):
        row = _first(_retry_transient(lambda: self.client.table("app_settings")
            .select("setting_value").eq("setting_key", str(setting_key)).limit(1).execute()))
        if not row:
            return default
        value = row.get("setting_value")
        return default if value is None else value

    def set_app_setting(self, setting_key: str, value) -> None:
        _retry_transient(lambda: self.client.table("app_settings").upsert({
            "setting_key": str(setting_key),
            "setting_value": value,
            "updated_at": utc_now().isoformat(),
        }, on_conflict="setting_key").execute())

    def delete_app_setting(self, setting_key: str) -> None:
        _retry_transient(lambda: self.client.table("app_settings").delete()
            .eq("setting_key", str(setting_key)).execute())

    @staticmethod
    def _mystery_plan_key(week_start: date | str) -> str:
        week_key = week_start.isoformat() if isinstance(week_start, date) else str(week_start)
        return f"weekly_mystery_plan::{week_key}"

    def get_mystery_plan(self, week_start: date | str) -> dict | None:
        value = self.get_app_setting(self._mystery_plan_key(week_start))
        return dict(value) if isinstance(value, Mapping) else None

    def save_mystery_plan(self, week_start: date | str, plan: Mapping) -> None:
        week_key = week_start.isoformat() if isinstance(week_start, date) else str(week_start)
        if self.weekly_mystery_locked(week_key):
            raise FactStoreError("This week's mystery is locked because a student has already unlocked a clue.")
        payload = dict(plan)
        self.set_app_setting(self._mystery_plan_key(week_key), payload)
        mystery_key = str(payload.get("mystery_key") or "").strip()
        if mystery_key:
            existing = self.get_weekly_mystery(week_key)
            if existing is not None and existing.mystery_key != mystery_key:
                self.replace_weekly_mystery(week_key, mystery_key)

    def clear_mystery_plan(self, week_start: date | str) -> None:
        week_key = week_start.isoformat() if isinstance(week_start, date) else str(week_start)
        if self.weekly_mystery_locked(week_key):
            raise FactStoreError("This week's mystery is locked because a student has already unlocked a clue.")
        self.delete_app_setting(self._mystery_plan_key(week_key))

    def set_global_focus_override(self, family: int | None) -> None:
        value = self._normalize_override(family)
        self.client.table("app_settings").upsert({
            "setting_key": "global_focus_override",
            "setting_value": value,
            "updated_at": utc_now().isoformat(),
        }, on_conflict="setting_key").execute()

    def set_class_focus_override(self, class_id: str, family: int | None) -> None:
        value = self._normalize_override(family)
        self.client.table("classes").update({"focus_override": value}).eq("class_id", str(class_id)).execute()

    def set_student_focus_override(self, student_id: str, family: int | None) -> None:
        value = self._normalize_override(family)
        self.client.table("students").update({"focus_override": value}).eq("student_id", str(student_id)).execute()

    def get_global_focus_override(self) -> int | None:
        row = _first(_retry_transient(lambda: self.client.table("app_settings").select("setting_value").eq("setting_key", "global_focus_override").limit(1).execute()))
        if not row or row.get("setting_value") is None:
            return None
        return int(row["setting_value"])

    def get_class_focus_override(self, class_id: str) -> int | None:
        row = _first(_retry_transient(lambda: self.client.table("classes").select("focus_override").eq("class_id", str(class_id)).limit(1).execute()))
        return None if not row or row.get("focus_override") is None else int(row["focus_override"])

    def get_student_focus_override(self, student_id: str) -> int | None:
        row = _first(_retry_transient(lambda: self.client.table("students").select("focus_override").eq("student_id", str(student_id)).limit(1).execute()))
        return None if not row or row.get("focus_override") is None else int(row["focus_override"])

    def get_effective_focus_override(self, student_id: str) -> int | None:
        student_row = _first(_retry_transient(lambda: self.client.table("students").select("class_id,focus_override").eq("student_id", str(student_id)).limit(1).execute()))
        if not student_row:
            return None
        if student_row.get("focus_override") is not None:
            return int(student_row["focus_override"])
        class_value = self.get_class_focus_override(str(student_row["class_id"]))
        if class_value is not None:
            return class_value
        return self.get_global_focus_override()

    def _learning_stats_for_students(self, student_ids: Sequence[str], through_date: date | str) -> dict[str, dict[str, int]]:
        target = date.fromisoformat(through_date) if isinstance(through_date, str) else through_date
        if not student_ids:
            return {}
        challenge_rows = _rows(
            self.client.table("daily_challenges").select("challenge_id,challenge_date")
            .lte("challenge_date", target.isoformat()).order("challenge_date").range(0, 4999).execute()
        )
        challenge_dates = {str(row["challenge_id"]): date.fromisoformat(str(row["challenge_date"])) for row in challenge_rows}
        assigned = sorted({d for d in challenge_dates.values() if d.weekday() < 5})
        progress_rows = _rows(
            self.client.table("daily_learning_progress").select("student_id,challenge_id,completed_at")
            .in_("student_id", list(student_ids)).not_.is_("completed_at", "null").range(0, 9999).execute()
        )
        completed_by_student = {sid: set() for sid in student_ids}
        for row in progress_rows:
            sid = str(row["student_id"]); cid = str(row["challenge_id"]); d = challenge_dates.get(cid)
            if sid in completed_by_student and d is not None and d.weekday() < 5:
                completed_by_student[sid].add(d)
        result = {}
        for sid in student_ids:
            completed = completed_by_student[sid]
            current = 0
            for d in reversed(assigned):
                if d in completed:
                    current += 1
                else:
                    break
            longest = 0; run = 0
            for d in assigned:
                if d in completed:
                    run += 1; longest = max(longest, run)
                else:
                    run = 0
            result[sid] = {"current_streak": current, "longest_streak": longest, "stars": len(completed)}
        return result

    def student_learning_stats(self, student_id: str, through_date: date | str) -> dict[str, int]:
        return self._learning_stats_for_students([str(student_id)], through_date).get(
            str(student_id), {"current_streak": 0, "longest_streak": 0, "stars": 0}
        )

    def class_learning_stats(
        self, class_id: str, through_date: date | str, *, students: Sequence[StudentRecord] | None = None
    ) -> dict[str, dict[str, int]]:
        students = list(students) if students is not None else self.list_students(class_id)
        return self._learning_stats_for_students([student.student_id for student in students], through_date)

    def class_learning_progress(
        self, class_id: str, challenge_id: str, *, students: Sequence[StudentRecord] | None = None
    ) -> dict[str, LearningProgressRecord]:
        students = list(students) if students is not None else self.list_students(class_id)
        ids = [student.student_id for student in students]
        if not ids:
            return {}
        rows = _rows(
            self.client.table("daily_learning_progress").select("*")
            .eq("challenge_id", str(challenge_id)).in_("student_id", ids).execute()
        )
        return {str(row["student_id"]): _learning(row) for row in rows}

    def teacher_daily_history(
        self, class_id: str, start_date: date | str, end_date: date | str,
        *, students: Sequence[StudentRecord] | None = None,
    ) -> list[dict]:
        """Return a compact teacher-only Daily history for instructional analysis.

        The read is deliberately bulked into a small number of Supabase queries:
        challenges, completed attempts, then chunked multiplication-answer reads.
        Chunking keeps large classes below PostgREST URL limits. Alternate Daily
        modes remain visible for completion summaries but never become
        multiplication fact evidence.
        """
        start_key = start_date.isoformat() if isinstance(start_date, date) else str(start_date)
        end_key = end_date.isoformat() if isinstance(end_date, date) else str(end_date)
        students = list(students) if students is not None else self.list_students(class_id, include_inactive=True)
        student_map = {str(student.student_id): student for student in students}
        if not student_map:
            return []

        challenge_rows = _rows(_retry_transient(lambda: (
            self.client.table("daily_challenges").select("challenge_id,challenge_date")
            .gte("challenge_date", start_key).lte("challenge_date", end_key)
            .order("challenge_date").range(0, 199).execute()
        )))
        challenge_dates = {str(row["challenge_id"]): str(row["challenge_date"]) for row in challenge_rows}
        if not challenge_dates:
            return []

        attempt_rows = _rows(_retry_transient(lambda: (
            self.client.table("daily_attempts")
            .select("attempt_id,student_id,challenge_id,correct_count,timed_seconds,completed_at,daily_mode")
            .in_("student_id", list(student_map))
            .in_("challenge_id", list(challenge_dates))
            .not_.is_("completed_at", "null")
            .range(0, 4999).execute()
        )))
        if not attempt_rows:
            return []

        multiplication_attempt_ids = [
            str(row["attempt_id"]) for row in attempt_rows
            if str(row.get("daily_mode") or "Multiplication") == "Multiplication"
        ]
        answers_by_attempt: dict[str, list[dict]] = {attempt_id: [] for attempt_id in multiplication_attempt_ids}
        answer_rows: list[dict] = []
        for offset in range(0, len(multiplication_attempt_ids), 100):
            attempt_batch = multiplication_attempt_ids[offset:offset + 100]
            answer_rows.extend(_rows(_retry_transient(lambda batch=attempt_batch: (
                self.client.table("daily_answers")
                .select("attempt_id,question_number,a,b,correct,first_correct,response_seconds,submitted_at")
                .in_("attempt_id", batch)
                .order("submitted_at").range(0, 1999).execute()
            ))))
        for row in answer_rows:
            attempt_id = str(row.get("attempt_id") or "")
            if attempt_id not in answers_by_attempt:
                continue
            answers_by_attempt[attempt_id].append({
                "question_number": int(row.get("question_number") or 0),
                "a": int(row.get("a") or 0),
                "b": int(row.get("b") or 0),
                "correct": bool(row.get("correct")),
                "first_correct": bool(row.get("first_correct")) if row.get("first_correct") is not None else bool(row.get("correct")),
                "response_seconds": None if row.get("response_seconds") is None else float(row.get("response_seconds")),
                "submitted_at": str(row.get("submitted_at") or ""),
            })

        history = []
        for row in attempt_rows:
            sid = str(row.get("student_id") or "")
            challenge_id = str(row.get("challenge_id") or "")
            student = student_map.get(sid)
            challenge_date = challenge_dates.get(challenge_id)
            if student is None or challenge_date is None:
                continue
            attempt_id = str(row.get("attempt_id") or "")
            history.append({
                "attempt_id": attempt_id, "student_id": sid, "nickname": student.nickname,
                "challenge_id": challenge_id, "challenge_date": challenge_date,
                "daily_mode": str(row.get("daily_mode") or "Multiplication"),
                "correct_count": int(row.get("correct_count") or 0),
                "timed_seconds": None if row.get("timed_seconds") is None else float(row.get("timed_seconds")),
                "completed_at": str(row.get("completed_at") or ""),
                "answers": list(answers_by_attempt.get(attempt_id, [])),
            })
        history.sort(key=lambda item: (item["challenge_date"], item["nickname"].casefold()))
        return history

    # ----- Weekly Mystery -----
    @staticmethod
    def _week_key(value: date | str) -> str:
        return value.isoformat() if isinstance(value, date) else str(value)

    def completed_mystery_days(
        self, student_id: str, week_start: date | str, *, through_day_number: int = 5
    ) -> list[tuple[int, str]]:
        """Return school days this week whose required routine was truly completed.

        Mystery unlock rows are a reward receipt, not the source of truth for whether
        the student finished. If a short network reset loses that receipt, this method
        lets the app repair it from already-saved Daily / learning completion data.
        A day with no completed required routine is never included.
        """
        week_key = self._week_key(week_start)
        monday = date.fromisoformat(week_key)
        through = max(0, min(5, int(through_day_number)))
        if through <= 0:
            return []
        end_key = (monday + timedelta(days=through - 1)).isoformat()
        challenge_rows = _rows(_retry_transient(lambda: (
            self.client.table("daily_challenges")
            .select("challenge_id,challenge_date")
            .gte("challenge_date", week_key)
            .lte("challenge_date", end_key)
            .order("challenge_date")
            .execute()
        )))
        if not challenge_rows:
            return []
        challenge_by_id = {str(row["challenge_id"]): str(row["challenge_date"]) for row in challenge_rows}
        challenge_ids = list(challenge_by_id)
        attempt_rows = _rows(_retry_transient(lambda: (
            self.client.table("daily_attempts")
            .select("challenge_id,daily_mode,completed_at")
            .eq("student_id", str(student_id))
            .in_("challenge_id", challenge_ids)
            .not_.is_("completed_at", "null")
            .execute()
        )))
        if not attempt_rows:
            return []

        multiplication_ids = [
            str(row["challenge_id"]) for row in attempt_rows
            if str(row.get("daily_mode") or "Multiplication") == "Multiplication"
        ]
        alternate_ids = [
            str(row["challenge_id"]) for row in attempt_rows
            if str(row.get("daily_mode") or "Multiplication") != "Multiplication"
        ]
        completed_learning: set[str] = set()
        if multiplication_ids:
            progress_rows = _rows(_retry_transient(lambda: (
                self.client.table("daily_learning_progress")
                .select("challenge_id,completed_at")
                .eq("student_id", str(student_id))
                .in_("challenge_id", multiplication_ids)
                .not_.is_("completed_at", "null")
                .execute()
            )))
            completed_learning = {str(row["challenge_id"]) for row in progress_rows}
        completed_alternate: set[str] = set()
        if alternate_ids:
            progress_rows = _rows(_retry_transient(lambda: (
                self.client.table("alternate_learning_progress")
                .select("challenge_id,completed_at")
                .eq("student_id", str(student_id))
                .in_("challenge_id", alternate_ids)
                .not_.is_("completed_at", "null")
                .execute()
            )))
            completed_alternate = {str(row["challenge_id"]) for row in progress_rows}

        qualified: list[tuple[int, str]] = []
        for row in attempt_rows:
            challenge_id = str(row["challenge_id"])
            mode = str(row.get("daily_mode") or "Multiplication")
            if mode == "Multiplication" and challenge_id not in completed_learning:
                continue
            if mode != "Multiplication" and challenge_id not in completed_alternate:
                continue
            challenge_date = date.fromisoformat(challenge_by_id[challenge_id])
            day_number = (challenge_date - monday).days + 1
            if 1 <= day_number <= through:
                qualified.append((day_number, challenge_id))
        qualified.sort(key=lambda item: item[0])
        return qualified

    def get_weekly_mystery(self, week_start: date | str) -> WeeklyMysteryRecord | None:
        row = _first(_retry_transient(lambda: (
            self.client.table("weekly_mysteries").select("*")
            .eq("week_start", self._week_key(week_start)).limit(1).execute()
        )))
        return None if row is None else _weekly_mystery(row)

    def get_or_create_weekly_mystery(self, week_start: date | str, mystery_key: str) -> WeeklyMysteryRecord:
        week_key = self._week_key(week_start)
        existing = self.get_weekly_mystery(week_key)
        if existing is not None:
            return existing
        payload = {"week_start": week_key, "mystery_key": str(mystery_key)}
        try:
            row = _first(_retry_transient(lambda: (
                _execute_returning(self.client.table("weekly_mysteries").insert(payload))
            )))
            if row is not None:
                return _weekly_mystery(row)
        except Exception as exc:
            # The insert may have landed even if its HTTP response was lost, or a
            # classmate may have won the first-create race. Re-read before failing.
            if not (_is_unique(exc) or _is_transient_http_error(exc)):
                raise
        concurrent = self.get_weekly_mystery(week_key)
        if concurrent is not None:
            return concurrent
        raise FactStoreError("Could not load this week's Mystery.")

    def weekly_mystery_locked(self, week_start: date | str) -> bool:
        rows = _rows(_retry_transient(lambda: self.client.table("weekly_mystery_unlocks").select("student_id")
            .eq("week_start", self._week_key(week_start)).range(0, 9999).execute()))
        test_ids = self._test_student_ids()
        return any(str(row["student_id"]) not in test_ids for row in rows)

    def replace_weekly_mystery(self, week_start: date | str, mystery_key: str) -> WeeklyMysteryRecord:
        week_key = self._week_key(week_start)
        if self.weekly_mystery_locked(week_key):
            raise FactStoreError("This week's mystery is locked because a student has already unlocked a clue.")
        now = utc_now().isoformat()
        response = _retry_transient(lambda: _execute_returning(self.client.table("weekly_mysteries").upsert({
            "week_start": week_key,
            "mystery_key": str(mystery_key),
            "updated_at": now,
        }, on_conflict="week_start")))
        row = _first(response)
        if row is None:
            raise FactStoreError("Supabase did not return the replaced weekly mystery.")
        return _weekly_mystery(row)

    def unlock_mystery_day(
        self, student_id: str, week_start: date | str, day_number: int, challenge_id: str
    ) -> MysteryUnlockRecord:
        day_number = int(day_number)
        if day_number not in {1, 2, 3, 4, 5}:
            raise ValueError("Mystery day number must be 1 through 5.")
        week_key = self._week_key(week_start)

        def fetch_existing():
            return _first(_retry_transient(lambda: (
                self.client.table("weekly_mystery_unlocks").select("*")
                .eq("student_id", str(student_id)).eq("week_start", week_key)
                .eq("day_number", day_number).limit(1).execute()
            )))

        existing = fetch_existing()
        if existing is not None:
            return _mystery_unlock(existing)
        payload = {
            "student_id": str(student_id),
            "week_start": week_key,
            "day_number": day_number,
            "challenge_id": str(challenge_id),
        }
        try:
            row = _first(_retry_transient(lambda: (
                _execute_returning(self.client.table("weekly_mystery_unlocks").insert(payload))
            )))
            if row is not None:
                return _mystery_unlock(row)
        except Exception as exc:
            # A lost insert response can turn the retry into a duplicate-key error.
            # Either way, a fresh read tells us whether the clue receipt exists.
            if not (_is_unique(exc) or _is_transient_http_error(exc)):
                raise
        row = fetch_existing()
        if row is not None:
            return _mystery_unlock(row)
        raise FactStoreError("Could not save today's Mystery clue.")

    def list_mystery_unlocks(self, student_id: str, week_start: date | str) -> list[MysteryUnlockRecord]:
        rows = _rows(_retry_transient(lambda: (
            self.client.table("weekly_mystery_unlocks").select("*")
            .eq("student_id", str(student_id)).eq("week_start", self._week_key(week_start))
            .order("day_number").execute()
        )))
        return [_mystery_unlock(row) for row in rows]

    def get_mystery_guess(
        self, student_id: str, week_start: date | str, *, guess_day: int | None = None
    ) -> MysteryGuessRecord | None:
        def fetch_guess():
            query = (
                self.client.table("weekly_mystery_guesses").select("*")
                .eq("student_id", str(student_id)).eq("week_start", self._week_key(week_start))
            )
            if guess_day is not None:
                query = query.eq("guess_day", int(guess_day))
            return query.order("guess_day").limit(1).execute()

        row = _first(_retry_transient(fetch_guess))
        return None if row is None else _mystery_guess(row)

    def list_mystery_guesses(self, student_id: str, week_start: date | str) -> list[MysteryGuessRecord]:
        rows = _rows(_retry_transient(lambda: (
            self.client.table("weekly_mystery_guesses").select("*")
            .eq("student_id", str(student_id)).eq("week_start", self._week_key(week_start))
            .order("guess_day").execute()
        )))
        return [_mystery_guess(row) for row in rows]

    def submit_mystery_guess(
        self, student_id: str, week_start: date | str, guess_text: str, *,
        correct: bool, clue_count: int, guess_day: int = 4,
    ) -> MysteryGuessRecord:
        week_key = self._week_key(week_start)
        guess_day = int(guess_day)
        if guess_day not in {4, 5}:
            raise ValueError("Mystery guesses are only allowed on Thursday or Friday.")
        existing = self.get_mystery_guess(student_id, week_key, guess_day=guess_day)
        if existing is not None:
            return existing
        cleaned = " ".join(str(guess_text or "").strip().split())
        if not cleaned:
            raise ValueError("Type a guess before submitting.")
        clue_count = int(clue_count)
        if clue_count not in {1, 2, 3, 4, 5}:
            raise ValueError("Clue count must be 1 through 5.")
        payload = {
            "student_id": str(student_id),
            "week_start": week_key,
            "guess_day": guess_day,
            "guess_text": cleaned[:80],
            "correct": bool(correct),
            "clue_count": clue_count,
        }
        try:
            row = _first(_retry_transient(lambda: (
                _execute_returning(self.client.table("weekly_mystery_guesses").insert(payload))
            )))
            if row is not None:
                return _mystery_guess(row)
        except Exception as exc:
            if not (_is_unique(exc) or _is_transient_http_error(exc)):
                raise
        row = self.get_mystery_guess(student_id, week_key, guess_day=guess_day)
        if row is not None:
            return row
        raise FactStoreError("Could not save the Mystery guess.")

    def mystery_student_stats(self, student_id: str) -> dict[str, int | None]:
        rows = _rows(_retry_transient(lambda: (
            self.client.table("weekly_mystery_guesses").select("week_start,correct,clue_count")
            .eq("student_id", str(student_id)).range(0, 4999).execute()
        )))
        correct_rows = [row for row in rows if bool(row.get("correct"))]
        return {
            "guesses": len(rows),
            "solved": len({str(row.get("week_start")) for row in correct_rows}),
            "earliest_solve": min((int(row["clue_count"]) for row in correct_rows), default=None),
        }

    def _test_student_ids(self) -> set[str]:
        rows = _rows(_retry_transient(lambda: self.client.table("students").select("student_id").eq("is_test", True).execute()))
        return {str(row["student_id"]) for row in rows}

    def weekly_mystery_correct_students(self, week_start: date | str) -> list[dict]:
        week_key = self._week_key(week_start)
        guess_rows = _rows(_retry_transient(lambda: self.client.table("weekly_mystery_guesses")
            .select("student_id,guess_day,clue_count,guessed_at")
            .eq("week_start", week_key).eq("correct", True).range(0, 9999).execute()))
        student_ids = list(dict.fromkeys(str(row["student_id"]) for row in guess_rows))
        if not student_ids:
            return []
        student_rows = _rows(_retry_transient(lambda: self.client.table("students")
            .select("student_id,class_id,nickname,is_test")
            .in_("student_id", student_ids).eq("is_test", False).execute()))
        class_ids = list({str(row["class_id"]) for row in student_rows})
        class_rows = _rows(_retry_transient(lambda: self.client.table("classes")
            .select("class_id,class_name").in_("class_id", class_ids).execute())) if class_ids else []
        class_names = {str(row["class_id"]): str(row["class_name"]) for row in class_rows}
        guess_by_student = {}
        for row in guess_rows:
            sid = str(row["student_id"])
            prior = guess_by_student.get(sid)
            if prior is None or int(row.get("guess_day") or 5) < int(prior.get("guess_day") or 5):
                guess_by_student[sid] = row
        result = []
        for row in student_rows:
            sid = str(row["student_id"])
            guess = guess_by_student.get(sid, {})
            result.append({
                "student_id": sid,
                "nickname": str(row["nickname"]),
                "class_id": str(row["class_id"]),
                "class_name": class_names.get(str(row["class_id"]), "Class"),
                "guess_day": int(guess.get("guess_day") or 5),
                "clue_count": int(guess.get("clue_count") or 0),
            })
        return sorted(result, key=lambda item: (item["class_name"].casefold(), item["nickname"].casefold()))

    def weekly_mystery_teacher_stats(self, week_start: date | str) -> dict[str, int]:
        week_key = self._week_key(week_start)
        test_ids = self._test_student_ids()
        unlock_rows = _rows(_retry_transient(lambda: (
            self.client.table("weekly_mystery_unlocks").select("student_id")
            .eq("week_start", week_key).range(0, 9999).execute()
        )))
        guess_rows = _rows(_retry_transient(lambda: (
            self.client.table("weekly_mystery_guesses").select("student_id,correct")
            .eq("week_start", week_key).range(0, 9999).execute()
        )))
        unlock_rows = [row for row in unlock_rows if str(row["student_id"]) not in test_ids]
        guess_rows = [row for row in guess_rows if str(row["student_id"]) not in test_ids]
        return {
            "students_unlocked": len({str(row["student_id"]) for row in unlock_rows}),
            "clues_unlocked": len(unlock_rows),
            "guesses": len(guess_rows),
            "correct": len({str(row["student_id"]) for row in guess_rows if bool(row.get("correct"))}),
        }
