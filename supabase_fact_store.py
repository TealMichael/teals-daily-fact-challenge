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

from fact_engine import Fact
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
    StudentRecord,
    generate_class_code,
    hash_pin,
    normalize_name,
    utc_now,
    verify_pin,
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
        payload = {
            "class_id": str(class_id),
            "nickname": name,
            "nickname_key": key,
            "pin_hash": hash_pin(pin),
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
        query = self.client.table("students").select("student_id,class_id,nickname,active,created_at").eq("class_id", str(class_id))
        if not include_inactive:
            query = query.eq("active", True)
        return [_student(row) for row in _rows(query.order("nickname").execute())]

    def get_student(self, student_id: str) -> StudentRecord:
        row = _first(
            self.client.table("students")
            .select("student_id,class_id,nickname,active,created_at")
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
                .select("student_id,class_id,nickname,active,created_at")
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
        response = (
            self.client.table("students")
            .update({"pin_hash": hash_pin(pin)})
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
            .select("student_id,class_id,nickname,active,created_at")
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
        when = completed_at or utc_now()
        started = when - timedelta(seconds=seconds)
        payloads = []
        for question_number, (fact, value) in enumerate(answers, start=1):
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
        return self.get_attempt(attempt_id)

    def reset_daily_attempt(self, student_id: str, challenge_id: str) -> bool:
        attempt = self.get_attempt_for_student(student_id, challenge_id)
        if attempt is None:
            return False
        self.client.table("daily_attempts").delete().eq("attempt_id", attempt.attempt_id).execute()
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


    def student_daily_streak(self, student_id: str, through_date: date | str) -> int:
        target = date.fromisoformat(through_date) if isinstance(through_date, str) else through_date
        attempt_rows = _rows(
            self.client.table("daily_attempts")
            .select("challenge_id")
            .eq("student_id", str(student_id))
            .not_.is_("completed_at", "null")
            .execute()
        )
        challenge_ids = [str(row["challenge_id"]) for row in attempt_rows]
        if not challenge_ids:
            return 0
        challenge_rows = _rows(
            self.client.table("daily_challenges")
            .select("challenge_date")
            .in_("challenge_id", challenge_ids)
            .execute()
        )
        completed_dates = {date.fromisoformat(str(row["challenge_date"])) for row in challenge_rows}
        from datetime import timedelta
        streak = 0
        cursor = target
        while cursor in completed_dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    # ----- Practice -----
    def record_practice(
        self, student_id: str | None, focus: str, fact: Fact, student_answer: int
    ) -> PracticeRecord:
        payload = {
            "student_id": str(student_id) if student_id else None,
            "focus": str(focus),
            "a": fact.a,
            "b": fact.b,
            "student_answer": int(student_answer),
            "correct_answer": fact.product,
            "correct": int(student_answer) == fact.product,
        }
        row = _first(self.client.table("practice_answers").insert(payload).select("*").execute())
        if row is None:
            raise FactStoreError("Could not save Practice answer.")
        return PracticeRecord(
            student_id=None if row.get("student_id") is None else str(row["student_id"]),
            focus=str(row["focus"]),
            a=int(row["a"]),
            b=int(row["b"]),
            student_answer=int(row["student_answer"]),
            correct_answer=int(row["correct_answer"]),
            correct=bool(row["correct"]),
            created_at=_dt(row.get("created_at")) or utc_now(),
        )

    def practice_summary(self, student_id: str) -> dict[str, int]:
        rows = _rows(
            self.client.table("practice_answers")
            .select("correct")
            .eq("student_id", str(student_id))
            .execute()
        )
        return {"attempts": len(rows), "correct": sum(bool(row.get("correct")) for row in rows)}
