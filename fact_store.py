from __future__ import annotations

"""Persistence contract and in-memory reference backend for the fact app.

The production app uses SupabaseFactStore.  InMemoryFactStore mirrors the same
behavior closely enough to run deterministic regression tests without a network.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
import base64
import hashlib
import hmac
import re
import secrets
import string
import uuid
from typing import Iterable, Mapping, Sequence

from fact_engine import Fact


class FactStoreError(RuntimeError):
    pass


class NameTaken(FactStoreError):
    pass


class NotFound(FactStoreError):
    pass


class AttemptComplete(FactStoreError):
    pass


class AttemptNotStarted(FactStoreError):
    pass


@dataclass(frozen=True)
class ClassRecord:
    class_id: str
    class_name: str
    class_code: str
    active: bool
    created_at: datetime


@dataclass(frozen=True)
class StudentRecord:
    student_id: str
    class_id: str
    nickname: str
    active: bool
    created_at: datetime


@dataclass(frozen=True)
class ChallengeRecord:
    challenge_id: str
    challenge_date: str
    challenge_version: str
    facts: tuple[Fact, ...]
    created_at: datetime


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    student_id: str
    challenge_id: str
    created_at: datetime
    timed_started_at: datetime | None = None
    completed_at: datetime | None = None
    correct_count: int | None = None
    timed_seconds: float | None = None


@dataclass(frozen=True)
class AnswerRecord:
    attempt_id: str
    question_number: int
    a: int
    b: int
    student_answer: int
    correct_answer: int
    correct: bool
    submitted_at: datetime


@dataclass(frozen=True)
class PracticeRecord:
    student_id: str | None
    focus: str
    a: int
    b: int
    student_answer: int
    correct_answer: int
    correct: bool
    created_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_name(value: str, *, label: str = "Name", max_length: int = 40) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    if not cleaned:
        raise ValueError(f"{label} is required.")
    if len(cleaned) > max_length:
        raise ValueError(f"{label} must be {max_length} characters or fewer.")
    key = cleaned.casefold()
    return cleaned, key


def validate_pin(pin: str) -> str:
    value = str(pin or "").strip()
    if not re.fullmatch(r"\d{4}", value):
        raise ValueError("PIN must be exactly 4 digits.")
    return value


def hash_pin(pin: str) -> str:
    pin = validate_pin(pin)
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(derived).decode()


def verify_pin(pin: str, encoded: str) -> bool:
    try:
        pin = validate_pin(pin)
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            pin.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def generate_pin() -> str:
    return f"{secrets.randbelow(10000):04d}"


def generate_class_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def _uuid() -> str:
    return str(uuid.uuid4())


def _as_date_key(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


class InMemoryFactStore:
    def __init__(self):
        self.classes: dict[str, dict] = {}
        self.students: dict[str, dict] = {}
        self.challenges: dict[str, ChallengeRecord] = {}
        self.attempts: dict[str, AttemptRecord] = {}
        self.answers: dict[str, list[AnswerRecord]] = {}
        self.practice: list[PracticeRecord] = []

    # ----- Classes -----
    def create_class(self, class_name: str, class_code: str | None = None) -> ClassRecord:
        class_name, key = normalize_name(class_name, label="Class name")
        if any(row["class_name_key"] == key for row in self.classes.values()):
            raise NameTaken("That class name already exists.")
        code = (class_code or generate_class_code()).upper()
        if any(row["record"].class_code == code for row in self.classes.values()):
            raise NameTaken("That class code already exists.")
        record = ClassRecord(_uuid(), class_name, code, True, utc_now())
        self.classes[record.class_id] = {"record": record, "class_name_key": key}
        return record

    def list_classes(self, *, include_inactive: bool = False) -> list[ClassRecord]:
        values = [row["record"] for row in self.classes.values()]
        if not include_inactive:
            values = [item for item in values if item.active]
        return sorted(values, key=lambda item: item.class_name.casefold())

    def set_class_active(self, class_id: str, active: bool) -> ClassRecord:
        if class_id not in self.classes:
            raise NotFound("Class not found.")
        row = self.classes[class_id]
        record = replace(row["record"], active=bool(active))
        row["record"] = record
        return record

    # ----- Students -----
    def create_student(self, class_id: str, nickname: str, pin: str) -> StudentRecord:
        if class_id not in self.classes:
            raise NotFound("Class not found.")
        nickname, key = normalize_name(nickname, label="Nickname", max_length=28)
        pin_hash = hash_pin(pin)
        if any(
            row["record"].class_id == class_id and row["nickname_key"] == key
            for row in self.students.values()
        ):
            raise NameTaken(f"{nickname} already exists in this class.")
        record = StudentRecord(_uuid(), class_id, nickname, True, utc_now())
        self.students[record.student_id] = {
            "record": record,
            "nickname_key": key,
            "pin_hash": pin_hash,
        }
        return record

    def authenticate_student(self, class_id: str, nickname: str, pin: str) -> StudentRecord | None:
        try:
            _, key = normalize_name(nickname, label="Nickname", max_length=28)
        except ValueError:
            return None
        for row in self.students.values():
            record = row["record"]
            if record.class_id == class_id and row["nickname_key"] == key and record.active:
                return record if verify_pin(pin, row["pin_hash"]) else None
        return None

    def list_students(self, class_id: str, *, include_inactive: bool = False) -> list[StudentRecord]:
        result = [row["record"] for row in self.students.values() if row["record"].class_id == class_id]
        if not include_inactive:
            result = [student for student in result if student.active]
        return sorted(result, key=lambda item: item.nickname.casefold())

    def get_student(self, student_id: str) -> StudentRecord:
        try:
            return self.students[student_id]["record"]
        except KeyError as exc:
            raise NotFound("Student not found.") from exc

    def rename_student(self, student_id: str, nickname: str) -> StudentRecord:
        if student_id not in self.students:
            raise NotFound("Student not found.")
        nickname, key = normalize_name(nickname, label="Nickname", max_length=28)
        record = self.students[student_id]["record"]
        if any(
            sid != student_id and row["record"].class_id == record.class_id and row["nickname_key"] == key
            for sid, row in self.students.items()
        ):
            raise NameTaken("That nickname is already used in this class.")
        updated = replace(record, nickname=nickname)
        self.students[student_id].update(record=updated, nickname_key=key)
        return updated

    def reset_student_pin(self, student_id: str, pin: str) -> None:
        if student_id not in self.students:
            raise NotFound("Student not found.")
        self.students[student_id]["pin_hash"] = hash_pin(pin)

    def set_student_active(self, student_id: str, active: bool) -> StudentRecord:
        if student_id not in self.students:
            raise NotFound("Student not found.")
        updated = replace(self.students[student_id]["record"], active=bool(active))
        self.students[student_id]["record"] = updated
        return updated

    # ----- Daily challenge -----
    def get_or_create_challenge(
        self, challenge_date: date | str, challenge_version: str, facts: Sequence[Fact]
    ) -> ChallengeRecord:
        key = _as_date_key(challenge_date)
        existing = self.challenges.get(key)
        if existing:
            if existing.challenge_version != challenge_version or tuple(existing.facts) != tuple(facts):
                raise FactStoreError("Stored Daily Challenge does not match the local generator.")
            return existing
        record = ChallengeRecord(_uuid(), key, challenge_version, tuple(facts), utc_now())
        self.challenges[key] = record
        return record

    def get_challenge(self, challenge_date: date | str) -> ChallengeRecord | None:
        return self.challenges.get(_as_date_key(challenge_date))

    def get_or_create_attempt(self, student_id: str, challenge_id: str) -> AttemptRecord:
        self.get_student(student_id)
        if not any(c.challenge_id == challenge_id for c in self.challenges.values()):
            raise NotFound("Challenge not found.")
        for attempt in self.attempts.values():
            if attempt.student_id == student_id and attempt.challenge_id == challenge_id:
                return attempt
        record = AttemptRecord(_uuid(), student_id, challenge_id, utc_now())
        self.attempts[record.attempt_id] = record
        self.answers[record.attempt_id] = []
        return record

    def get_attempt(self, attempt_id: str) -> AttemptRecord:
        try:
            return self.attempts[attempt_id]
        except KeyError as exc:
            raise NotFound("Attempt not found.") from exc

    def get_attempt_for_student(self, student_id: str, challenge_id: str) -> AttemptRecord | None:
        for attempt in self.attempts.values():
            if attempt.student_id == student_id and attempt.challenge_id == challenge_id:
                return attempt
        return None

    def get_answers(self, attempt_id: str) -> list[AnswerRecord]:
        if attempt_id not in self.answers:
            raise NotFound("Attempt not found.")
        return sorted(self.answers[attempt_id], key=lambda item: item.question_number)

    def submit_first_answer(
        self, attempt_id: str, fact: Fact, student_answer: int, *, submitted_at: datetime | None = None
    ) -> AttemptRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.completed_at is not None:
            raise AttemptComplete("Today's Daily is already complete.")
        existing = self.get_answers(attempt_id)
        if existing:
            return attempt
        when = submitted_at or utc_now()
        answer = AnswerRecord(
            attempt_id=attempt_id,
            question_number=1,
            a=fact.a,
            b=fact.b,
            student_answer=int(student_answer),
            correct_answer=fact.product,
            correct=int(student_answer) == fact.product,
            submitted_at=when,
        )
        self.answers[attempt_id].append(answer)
        updated = replace(attempt, timed_started_at=when)
        self.attempts[attempt_id] = updated
        return updated

    def complete_attempt(
        self,
        attempt_id: str,
        remaining_answers: Sequence[tuple[Fact, int]],
        *,
        completed_at: datetime | None = None,
    ) -> AttemptRecord:
        attempt = self.get_attempt(attempt_id)
        if attempt.completed_at is not None:
            raise AttemptComplete("Today's Daily is already complete.")
        if attempt.timed_started_at is None or len(self.get_answers(attempt_id)) != 1:
            raise AttemptNotStarted("Submit Fact 1 before completing the timed sprint.")
        if len(remaining_answers) != 9:
            raise ValueError("The timed sprint must contain Facts 2-10.")
        when = completed_at or utc_now()
        for question_number, (fact, value) in enumerate(remaining_answers, start=2):
            self.answers[attempt_id].append(
                AnswerRecord(
                    attempt_id=attempt_id,
                    question_number=question_number,
                    a=fact.a,
                    b=fact.b,
                    student_answer=int(value),
                    correct_answer=fact.product,
                    correct=int(value) == fact.product,
                    submitted_at=when,
                )
            )
        answers = self.get_answers(attempt_id)
        correct_count = sum(answer.correct for answer in answers)
        seconds = max(0.0, (when - attempt.timed_started_at).total_seconds())
        updated = replace(
            attempt,
            completed_at=when,
            correct_count=correct_count,
            timed_seconds=seconds,
        )
        self.attempts[attempt_id] = updated
        return updated

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
        self.answers[attempt_id] = []
        for question_number, (fact, value) in enumerate(answers, start=1):
            self.answers[attempt_id].append(
                AnswerRecord(
                    attempt_id=attempt_id,
                    question_number=question_number,
                    a=fact.a,
                    b=fact.b,
                    student_answer=int(value),
                    correct_answer=fact.product,
                    correct=int(value) == fact.product,
                    submitted_at=when,
                )
            )
        correct_count = sum(answer.correct for answer in self.answers[attempt_id])
        updated = replace(
            attempt,
            timed_started_at=started,
            completed_at=when,
            correct_count=correct_count,
            timed_seconds=seconds,
        )
        self.attempts[attempt_id] = updated
        return updated

    def reset_daily_attempt(self, student_id: str, challenge_id: str) -> bool:
        target = self.get_attempt_for_student(student_id, challenge_id)
        if target is None:
            return False
        self.answers.pop(target.attempt_id, None)
        self.attempts.pop(target.attempt_id, None)
        return True

    def completed_attempts_for_class(self, class_id: str, challenge_id: str) -> list[dict]:
        student_map = {s.student_id: s for s in self.list_students(class_id, include_inactive=True)}
        rows = []
        for attempt in self.attempts.values():
            if (
                attempt.challenge_id == challenge_id
                and attempt.student_id in student_map
                and attempt.completed_at is not None
            ):
                student = student_map[attempt.student_id]
                rows.append({
                    "student_id": student.student_id,
                    "nickname": student.nickname,
                    "correct_count": int(attempt.correct_count or 0),
                    "timed_seconds": float(attempt.timed_seconds or 0.0),
                    "completed_at": attempt.completed_at,
                    "attempt_id": attempt.attempt_id,
                })
        rows.sort(key=lambda row: (-row["correct_count"], row["timed_seconds"], row["completed_at"]))
        return rows

    def leaderboard(self, class_id: str, challenge_id: str, *, limit: int = 10) -> list[dict]:
        rows = self.completed_attempts_for_class(class_id, challenge_id)[:limit]
        return [dict(row, rank=index) for index, row in enumerate(rows, start=1)]

    def daily_status(self, class_id: str, challenge_id: str) -> list[dict]:
        students = self.list_students(class_id)
        attempt_by_student = {
            attempt.student_id: attempt
            for attempt in self.attempts.values()
            if attempt.challenge_id == challenge_id
        }
        result = []
        for student in students:
            attempt = attempt_by_student.get(student.student_id)
            result.append({
                "student_id": student.student_id,
                "nickname": student.nickname,
                "status": (
                    "Complete" if attempt and attempt.completed_at else
                    "In progress" if attempt else
                    "Not started"
                ),
                "correct_count": attempt.correct_count if attempt else None,
                "timed_seconds": attempt.timed_seconds if attempt else None,
                "attempt_id": attempt.attempt_id if attempt else None,
            })
        return result


    def student_daily_streak(self, student_id: str, through_date: date | str) -> int:
        target = date.fromisoformat(through_date) if isinstance(through_date, str) else through_date
        completed_dates: set[date] = set()
        challenge_by_id = {record.challenge_id: record for record in self.challenges.values()}
        for attempt in self.attempts.values():
            if attempt.student_id == student_id and attempt.completed_at is not None:
                challenge = challenge_by_id.get(attempt.challenge_id)
                if challenge:
                    completed_dates.add(date.fromisoformat(challenge.challenge_date))
        streak = 0
        cursor = target
        from datetime import timedelta
        while cursor in completed_dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    # ----- Practice -----
    def record_practice(
        self, student_id: str | None, focus: str, fact: Fact, student_answer: int
    ) -> PracticeRecord:
        if student_id is not None:
            self.get_student(student_id)
        record = PracticeRecord(
            student_id=student_id,
            focus=str(focus),
            a=fact.a,
            b=fact.b,
            student_answer=int(student_answer),
            correct_answer=fact.product,
            correct=int(student_answer) == fact.product,
            created_at=utc_now(),
        )
        self.practice.append(record)
        return record

    def practice_summary(self, student_id: str) -> dict[str, int]:
        rows = [row for row in self.practice if row.student_id == student_id]
        return {"attempts": len(rows), "correct": sum(row.correct for row in rows)}
