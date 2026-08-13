from __future__ import annotations

"""Supabase production backend for Teal's Daily Fact Challenge.

All calls are made server-side from Streamlit with SUPABASE_SECRET_KEY. RLS is
enabled with no public policies in the supplied schema, so student browsers never
receive direct database credentials.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Mapping, Sequence

try:
    from supabase import Client, create_client
except ImportError:  # Local/offline Practice can still load before dependencies are installed.
    Client = object  # type: ignore[assignment]

    def create_client(*_args, **_kwargs):
        raise RuntimeError("The supabase package is not installed. Install requirements.txt for Daily accounts.")

from fact_engine import Fact, canonical_pair
from adaptive_engine import MasterySnapshot, update_snapshot, mastery_counts
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
    WeeklyMysteryRecord,
    MysteryUnlockRecord,
    MysteryGuessRecord,
    StudentRecord,
    generate_class_code,
    hash_pin,
    normalize_name,
    utc_now,
    verify_pin,
    validate_pin,
)


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


class SupabaseFactStore:
    def __init__(self, supabase_url: str, supabase_secret_key: str, *, client: Client | None = None):
        url = normalize_supabase_url(supabase_url)
        key = str(supabase_secret_key or "").strip()
        if not url:
            raise ValueError("SUPABASE_URL is missing.")
        if not key:
            raise ValueError("SUPABASE_SECRET_KEY is missing.")
        self.url_was_normalized = url != str(supabase_url or "").strip().rstrip("/")
        self.client: Client = client or create_client(url, key)

    @classmethod
    def from_secrets(cls, secrets: Mapping[str, str]) -> "SupabaseFactStore":
        return cls(str(secrets["SUPABASE_URL"]), str(secrets["SUPABASE_SECRET_KEY"]))

    def health_check(self) -> bool:
        self.client.table("classes").select("class_id").limit(1).execute()
        self.client.table("student_fact_mastery").select("student_id").limit(1).execute()
        self.client.table("daily_learning_progress").select("student_id").limit(1).execute()
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
                response = (
                    self.client.table("classes")
                    .insert({"class_name": name, "class_name_key": key, "class_code": code})
                    .select("*")
                    .execute()
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
        query = self.client.table("classes").select("*")
        if not include_inactive:
            query = query.eq("active", True)
        rows = _rows(query.order("class_name").execute())
        return [_class(row) for row in rows]

    def set_class_active(self, class_id: str, active: bool) -> ClassRecord:
        row = _first(
            self.client.table("classes")
            .update({"active": bool(active)})
            .eq("class_id", str(class_id))
            .select("*")
            .execute()
        )
        if row is None:
            raise NotFound("Class not found.")
        return _class(row)

    # ----- Students -----
    def create_student(self, class_id: str, nickname: str, pin: str) -> StudentRecord:
        name, key = normalize_name(nickname, label="Nickname", max_length=28)
        pin = validate_pin(pin)
        payload = {
            "class_id": str(class_id),
            "nickname": name,
            "nickname_key": key,
            "pin_hash": hash_pin(pin),
            "pin_code": pin,
        }
        try:
            row = _first(self.client.table("students").insert(payload).select("*").execute())
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
        row = _first(
            self.client.table("students")
            .select("student_id,class_id,nickname,pin_hash,active,created_at")
            .eq("class_id", str(class_id))
            .eq("nickname_key", key)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        if row is None or not verify_pin(pin, str(row.get("pin_hash") or "")):
            return None
        return _student(row)

    def list_students(self, class_id: str, *, include_inactive: bool = False) -> list[StudentRecord]:
        query = self.client.table("students").select("student_id,class_id,nickname,pin_code,active,created_at").eq("class_id", str(class_id))
        if not include_inactive:
            query = query.eq("active", True)
        return [_student(row) for row in _rows(query.order("nickname").execute())]

    def get_student(self, student_id: str) -> StudentRecord:
        row = _first(
            self.client.table("students")
            .select("student_id,class_id,nickname,pin_code,active,created_at")
            .eq("student_id", str(student_id))
            .limit(1)
            .execute()
        )
        if row is None:
            raise NotFound("Student not found.")
        return _student(row)

    def rename_student(self, student_id: str, nickname: str) -> StudentRecord:
        student = self.get_student(student_id)
        name, key = normalize_name(nickname, label="Nickname", max_length=28)
        try:
            row = _first(
                self.client.table("students")
                .update({"nickname": name, "nickname_key": key})
                .eq("student_id", student.student_id)
                .select("student_id,class_id,nickname,pin_code,active,created_at")
                .execute()
            )
        except Exception as exc:
            if _is_unique(exc):
                raise NameTaken("That nickname is already used in this class.") from exc
            raise
        if row is None:
            raise NotFound("Student not found.")
        return _student(row)

    def reset_student_pin(self, student_id: str, pin: str) -> None:
        pin = validate_pin(pin)
        response = (
            self.client.table("students")
            .update({"pin_hash": hash_pin(pin), "pin_code": pin})
            .eq("student_id", str(student_id))
            .select("student_id")
            .execute()
        )
        if _first(response) is None:
            raise NotFound("Student not found.")

    def set_student_active(self, student_id: str, active: bool) -> StudentRecord:
        row = _first(
            self.client.table("students")
            .update({"active": bool(active)})
            .eq("student_id", str(student_id))
            .select("student_id,class_id,nickname,pin_code,active,created_at")
            .execute()
        )
        if row is None:
            raise NotFound("Student not found.")
        return _student(row)

    # ----- Challenge -----
    def get_challenge(self, challenge_date: date | str) -> ChallengeRecord | None:
        key = challenge_date.isoformat() if isinstance(challenge_date, date) else str(challenge_date)
        row = _first(
            self.client.table("daily_challenges")
            .select("*")
            .eq("challenge_date", key)
            .limit(1)
            .execute()
        )
        return _challenge(row) if row else None

    def get_or_create_challenge(
        self, challenge_date: date | str, challenge_version: str, facts: Sequence[Fact]
    ) -> ChallengeRecord:
        key = challenge_date.isoformat() if isinstance(challenge_date, date) else str(challenge_date)
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
        record = self.get_challenge(key)
        if record is None:
            raise FactStoreError("Could not load today's challenge after registration.")
        if record.challenge_version != challenge_version or tuple(record.facts) != tuple(facts):
            raise FactStoreError("Stored Daily Challenge does not match the local generator.")
        return record

    # ----- Attempts / answers -----
    def get_or_create_attempt(self, student_id: str, challenge_id: str) -> AttemptRecord:
        existing = self.get_attempt_for_student(student_id, challenge_id)
        if existing:
            return existing
        try:
            row = _first(
                self.client.table("daily_attempts")
                .insert({"student_id": str(student_id), "challenge_id": str(challenge_id)})
                .select("*")
                .execute()
            )
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
        row = _first(
            self.client.table("daily_attempts")
            .select("*")
            .eq("attempt_id", str(attempt_id))
            .limit(1)
            .execute()
        )
        if row is None:
            raise NotFound("Attempt not found.")
        return _attempt(row)

    def get_attempt_for_student(self, student_id: str, challenge_id: str) -> AttemptRecord | None:
        row = _first(
            self.client.table("daily_attempts")
            .select("*")
            .eq("student_id", str(student_id))
            .eq("challenge_id", str(challenge_id))
            .limit(1)
            .execute()
        )
        return _attempt(row) if row else None

    def get_answers(self, attempt_id: str) -> list[AnswerRecord]:
        return [
            _answer(row)
            for row in _rows(
                self.client.table("daily_answers")
                .select("*")
                .eq("attempt_id", str(attempt_id))
                .order("question_number")
                .execute()
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
                "submitted_at": when.isoformat(),
            })
        # Upsert makes completion retry-safe if a network hiccup lands between
        # the answer write and the attempt summary update.
        self.client.table("daily_answers").upsert(
            payloads, on_conflict="attempt_id,question_number"
        ).execute()
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
        completed_at: datetime | None = None,
    ) -> AttemptRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.completed_at is not None:
            return attempt
        if len(answers) != 10:
            raise ValueError("A Daily completion must contain exactly 10 answers.")
        seconds = float(timed_seconds)
        if not 0.1 <= seconds <= 3600:
            raise ValueError("Timed sprint duration is outside the allowed range.")
        latencies = list(response_seconds or [None] * 10)
        if len(latencies) != 10:
            raise ValueError("Daily response timing must contain exactly 10 values.")
        when = completed_at or utc_now()
        started = when - timedelta(seconds=seconds)
        payloads = []
        for question_number, ((fact, value), latency) in enumerate(zip(answers, latencies), start=1):
            payloads.append({
                "attempt_id": str(attempt_id),
                "question_number": question_number,
                "a": fact.a,
                "b": fact.b,
                "student_answer": int(value),
                "correct_answer": fact.product,
                "correct": int(value) == fact.product,
                "submitted_at": when.isoformat(),
                "response_seconds": None if latency is None else round(float(latency), 3),
            })
        self.client.table("daily_answers").upsert(
            payloads, on_conflict="attempt_id,question_number"
        ).execute()
        saved = self.get_answers(attempt_id)
        if len(saved) != 10:
            raise FactStoreError("Daily completion did not save all 10 answers.")
        correct_count = sum(answer.correct for answer in saved)
        self.client.table("daily_attempts").update({
            "timed_started_at": started.isoformat(),
            "completed_at": when.isoformat(),
            "correct_count": correct_count,
            "timed_seconds": round(seconds, 3),
        }).eq("attempt_id", str(attempt_id)).execute()
        # Daily retrievals are the first source of evidence for the gradual
        # mastery map. Fact 1 intentionally has no speed evidence.
        for answer in saved:
            fact = Fact(a=answer.a, b=answer.b, tier="core")
            if max(fact.key) <= 10:
                self.record_mastery_evidence(
                    attempt.student_id, fact, answer.correct,
                    response_seconds=answer.response_seconds, practiced_at=when,
                )
        self.get_or_create_learning_progress(attempt.student_id, attempt.challenge_id)
        if correct_count == 10:
            self.mark_fix_complete(attempt.student_id, attempt.challenge_id)
        return self.get_attempt(attempt_id)

    def rebuild_mastery(self, student_id: str) -> list[MasterySnapshot]:
        attempt_rows = _rows(
            self.client.table("daily_attempts").select("attempt_id,completed_at")
            .eq("student_id", str(student_id)).not_.is_("completed_at", "null").range(0, 4999).execute()
        )
        attempt_ids = [str(row["attempt_id"]) for row in attempt_rows]
        daily_rows = []
        if attempt_ids:
            daily_rows = _rows(
                self.client.table("daily_answers").select("a,b,correct,response_seconds,submitted_at")
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
                events.append((_dt(row.get("submitted_at")) or utc_now(), a, b, bool(row["correct"]), None if row.get("response_seconds") is None else float(row["response_seconds"])))
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
        self.client.table("daily_attempts").delete().eq("attempt_id", attempt.attempt_id).execute()
        self.rebuild_mastery(student_id)
        return True

    def completed_attempts_for_class(self, class_id: str, challenge_id: str) -> list[dict]:
        students = self.list_students(class_id, include_inactive=True)
        if not students:
            return []
        student_map = {student.student_id: student for student in students}
        student_ids = list(student_map)
        rows = _rows(
            self.client.table("daily_attempts")
            .select("attempt_id,student_id,correct_count,timed_seconds,completed_at")
            .eq("challenge_id", str(challenge_id))
            .in_("student_id", student_ids)
            .not_.is_("completed_at", "null")
            .execute()
        )
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

    def daily_status(self, class_id: str, challenge_id: str) -> list[dict]:
        students = self.list_students(class_id)
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

    def get_mastery(self, student_id: str) -> list[MasterySnapshot]:
        rows = _rows(
            self.client.table("student_fact_mastery").select("*")
            .eq("student_id", str(student_id)).execute()
        )
        if rows:
            return [_mastery(row) for row in rows]
        # Existing v1 Daily history can seed v2 automatically; there is still
        # no placement test and no invented evidence.
        prior_daily = _first(
            self.client.table("daily_attempts").select("attempt_id")
            .eq("student_id", str(student_id)).not_.is_("completed_at", "null").limit(1).execute()
        )
        prior_focus = _first(
            self.client.table("practice_answers").select("practice_answer_id")
            .eq("student_id", str(student_id)).eq("activity_type", "focus")
            .eq("is_retry", False).limit(1).execute()
        )
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

    def get_or_create_learning_progress(self, student_id: str, challenge_id: str) -> LearningProgressRecord:
        row = _first(
            self.client.table("daily_learning_progress").select("*")
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).limit(1).execute()
        )
        if row is None:
            row = _first(
                self.client.table("daily_learning_progress").insert({
                    "student_id": str(student_id), "challenge_id": str(challenge_id), "focus_plan": []
                }).select("*").execute()
            )
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
        row = _first(
            self.client.table("daily_learning_progress").update(payload)
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id)).select("*").execute()
        )
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
        if (
            student_id is not None and challenge_id is not None and activity_type == "focus"
            and activity_index is not None and not is_retry
        ):
            existing = _first(
                self.client.table("practice_answers").select("*")
                .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id))
                .eq("activity_type", "focus").eq("activity_index", int(activity_index))
                .eq("is_retry", False).limit(1).execute()
            )
            if existing is not None:
                return _practice(existing)
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
        row = _first(self.client.table("practice_answers").insert(payload).select("*").execute())
        if row is None:
            raise FactStoreError("Could not save Practice answer.")
        record = _practice(row)
        if count_for_mastery and student_id is not None and not is_retry and max(fact.key) <= 10:
            self.record_mastery_evidence(
                student_id, fact, record.correct, response_seconds=response_seconds, practiced_at=record.created_at
            )
        return record

    def learning_activity_rows(self, student_id: str, challenge_id: str, activity_type: str) -> list[PracticeRecord]:
        rows = _rows(
            self.client.table("practice_answers").select("*")
            .eq("student_id", str(student_id)).eq("challenge_id", str(challenge_id))
            .eq("activity_type", str(activity_type)).order("activity_index").order("created_at").execute()
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
        row = _first(self.client.table("app_settings").select("setting_value").eq("setting_key", "global_focus_override").limit(1).execute())
        if not row or row.get("setting_value") is None:
            return None
        return int(row["setting_value"])

    def get_class_focus_override(self, class_id: str) -> int | None:
        row = _first(self.client.table("classes").select("focus_override").eq("class_id", str(class_id)).limit(1).execute())
        return None if not row or row.get("focus_override") is None else int(row["focus_override"])

    def get_student_focus_override(self, student_id: str) -> int | None:
        row = _first(self.client.table("students").select("focus_override").eq("student_id", str(student_id)).limit(1).execute())
        return None if not row or row.get("focus_override") is None else int(row["focus_override"])

    def get_effective_focus_override(self, student_id: str) -> int | None:
        student_row = _first(self.client.table("students").select("class_id,focus_override").eq("student_id", str(student_id)).limit(1).execute())
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

    def class_learning_stats(self, class_id: str, through_date: date | str) -> dict[str, dict[str, int]]:
        students = self.list_students(class_id)
        return self._learning_stats_for_students([student.student_id for student in students], through_date)

    def class_learning_progress(self, class_id: str, challenge_id: str) -> dict[str, LearningProgressRecord]:
        students = self.list_students(class_id)
        ids = [student.student_id for student in students]
        if not ids:
            return {}
        rows = _rows(
            self.client.table("daily_learning_progress").select("*")
            .eq("challenge_id", str(challenge_id)).in_("student_id", ids).execute()
        )
        return {str(row["student_id"]): _learning(row) for row in rows}

    # ----- Weekly Mystery -----
    @staticmethod
    def _week_key(value: date | str) -> str:
        return value.isoformat() if isinstance(value, date) else str(value)

    def get_weekly_mystery(self, week_start: date | str) -> WeeklyMysteryRecord | None:
        row = _first(
            self.client.table("weekly_mysteries").select("*")
            .eq("week_start", self._week_key(week_start)).limit(1).execute()
        )
        return None if row is None else _weekly_mystery(row)

    def get_or_create_weekly_mystery(self, week_start: date | str, mystery_key: str) -> WeeklyMysteryRecord:
        week_key = self._week_key(week_start)
        existing = self.get_weekly_mystery(week_key)
        if existing is not None:
            return existing
        try:
            row = _first(
                self.client.table("weekly_mysteries").insert({
                    "week_start": week_key,
                    "mystery_key": str(mystery_key),
                }).select("*").execute()
            )
            if row is None:
                raise FactStoreError("Supabase did not return the weekly mystery.")
            return _weekly_mystery(row)
        except Exception as exc:
            if _is_unique(exc):
                concurrent = self.get_weekly_mystery(week_key)
                if concurrent is not None:
                    return concurrent
            raise

    def weekly_mystery_locked(self, week_start: date | str) -> bool:
        row = _first(
            self.client.table("weekly_mystery_unlocks").select("student_id")
            .eq("week_start", self._week_key(week_start)).limit(1).execute()
        )
        return row is not None

    def replace_weekly_mystery(self, week_start: date | str, mystery_key: str) -> WeeklyMysteryRecord:
        week_key = self._week_key(week_start)
        if self.weekly_mystery_locked(week_key):
            raise FactStoreError("This week's mystery is locked because a student has already unlocked a clue.")
        now = utc_now().isoformat()
        response = self.client.table("weekly_mysteries").upsert({
            "week_start": week_key,
            "mystery_key": str(mystery_key),
            "updated_at": now,
        }, on_conflict="week_start").select("*").execute()
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
        existing = _first(
            self.client.table("weekly_mystery_unlocks").select("*")
            .eq("student_id", str(student_id)).eq("week_start", week_key)
            .eq("day_number", day_number).limit(1).execute()
        )
        if existing is not None:
            return _mystery_unlock(existing)
        payload = {
            "student_id": str(student_id),
            "week_start": week_key,
            "day_number": day_number,
            "challenge_id": str(challenge_id),
        }
        try:
            row = _first(self.client.table("weekly_mystery_unlocks").insert(payload).select("*").execute())
            if row is None:
                raise FactStoreError("Supabase did not return the mystery unlock.")
            return _mystery_unlock(row)
        except Exception as exc:
            if _is_unique(exc):
                row = _first(
                    self.client.table("weekly_mystery_unlocks").select("*")
                    .eq("student_id", str(student_id)).eq("week_start", week_key)
                    .eq("day_number", day_number).limit(1).execute()
                )
                if row is not None:
                    return _mystery_unlock(row)
            raise

    def list_mystery_unlocks(self, student_id: str, week_start: date | str) -> list[MysteryUnlockRecord]:
        rows = _rows(
            self.client.table("weekly_mystery_unlocks").select("*")
            .eq("student_id", str(student_id)).eq("week_start", self._week_key(week_start))
            .order("day_number").execute()
        )
        return [_mystery_unlock(row) for row in rows]

    def get_mystery_guess(self, student_id: str, week_start: date | str) -> MysteryGuessRecord | None:
        row = _first(
            self.client.table("weekly_mystery_guesses").select("*")
            .eq("student_id", str(student_id)).eq("week_start", self._week_key(week_start)).limit(1).execute()
        )
        return None if row is None else _mystery_guess(row)

    def submit_mystery_guess(
        self, student_id: str, week_start: date | str, guess_text: str, *, correct: bool, clue_count: int
    ) -> MysteryGuessRecord:
        week_key = self._week_key(week_start)
        existing = self.get_mystery_guess(student_id, week_key)
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
            "guess_text": cleaned[:80],
            "correct": bool(correct),
            "clue_count": clue_count,
        }
        try:
            row = _first(self.client.table("weekly_mystery_guesses").insert(payload).select("*").execute())
            if row is None:
                raise FactStoreError("Supabase did not return the mystery guess.")
            return _mystery_guess(row)
        except Exception as exc:
            if _is_unique(exc):
                row = self.get_mystery_guess(student_id, week_key)
                if row is not None:
                    return row
            raise

    def mystery_student_stats(self, student_id: str) -> dict[str, int | None]:
        rows = _rows(
            self.client.table("weekly_mystery_guesses").select("correct,clue_count")
            .eq("student_id", str(student_id)).range(0, 4999).execute()
        )
        correct_rows = [row for row in rows if bool(row.get("correct"))]
        return {
            "guesses": len(rows),
            "solved": len(correct_rows),
            "earliest_solve": min((int(row["clue_count"]) for row in correct_rows), default=None),
        }

    def weekly_mystery_teacher_stats(self, week_start: date | str) -> dict[str, int]:
        week_key = self._week_key(week_start)
        unlock_rows = _rows(
            self.client.table("weekly_mystery_unlocks").select("student_id")
            .eq("week_start", week_key).range(0, 9999).execute()
        )
        guess_rows = _rows(
            self.client.table("weekly_mystery_guesses").select("student_id,correct")
            .eq("week_start", week_key).range(0, 9999).execute()
        )
        return {
            "students_unlocked": len({str(row["student_id"]) for row in unlock_rows}),
            "clues_unlocked": len(unlock_rows),
            "guesses": len(guess_rows),
            "correct": sum(bool(row.get("correct")) for row in guess_rows),
        }

