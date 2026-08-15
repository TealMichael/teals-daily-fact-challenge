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

from fact_engine import Fact, canonical_pair
from adaptive_engine import MasterySnapshot, update_snapshot, mastery_counts, complete_mastery_map


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
    pin_code: str | None = None


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
    response_seconds: float | None = None


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
    response_seconds: float | None = None
    challenge_id: str | None = None
    activity_type: str = "free_practice"
    activity_index: int | None = None
    is_retry: bool = False


@dataclass(frozen=True)
class WeeklyMysteryRecord:
    week_start: str
    mystery_key: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MysteryUnlockRecord:
    student_id: str
    week_start: str
    day_number: int
    challenge_id: str
    unlocked_at: datetime


@dataclass(frozen=True)
class MysteryGuessRecord:
    student_id: str
    week_start: str
    guess_text: str
    correct: bool
    clue_count: int
    guessed_at: datetime
    guess_day: int = 4


@dataclass(frozen=True)
class LearningProgressRecord:
    student_id: str
    challenge_id: str
    focus_plan: tuple[Fact, ...] = ()
    fix_completed_at: datetime | None = None
    focus_completed_at: datetime | None = None
    completed_at: datetime | None = None


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
        self.practice_event_ids: set[str] = set()
        self.mastery: dict[tuple[str, int, int], MasterySnapshot] = {}
        self.learning_progress: dict[tuple[str, str], LearningProgressRecord] = {}
        self.class_focus_overrides: dict[str, int | None] = {}
        self.student_focus_overrides: dict[str, int | None] = {}
        self.global_focus_override: int | None = None
        self.weekly_mysteries: dict[str, WeeklyMysteryRecord] = {}
        self.mystery_unlocks: dict[tuple[str, str, int], MysteryUnlockRecord] = {}
        self.mystery_guesses: dict[tuple[str, str, int], MysteryGuessRecord] = {}

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
        pin = validate_pin(pin)
        record = StudentRecord(_uuid(), class_id, nickname, True, utc_now(), pin)
        self.students[record.student_id] = {
            "record": record,
            "nickname_key": key,
            "pin_hash": pin_hash,
            "pin_code": pin,
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
        pin = validate_pin(pin)
        self.students[student_id]["pin_hash"] = hash_pin(pin)
        self.students[student_id]["pin_code"] = pin
        self.students[student_id]["record"] = replace(self.students[student_id]["record"], pin_code=pin)

    def set_student_active(self, student_id: str, active: bool) -> StudentRecord:
        if student_id not in self.students:
            raise NotFound("Student not found.")
        updated = replace(self.students[student_id]["record"], active=bool(active))
        self.students[student_id]["record"] = updated
        return updated

    def move_student(self, student_id: str, new_class_id: str) -> StudentRecord:
        if student_id not in self.students:
            raise NotFound("Student not found.")
        if new_class_id not in self.classes:
            raise NotFound("Class not found.")
        record = self.students[student_id]["record"]
        if record.class_id == new_class_id:
            return record
        nickname_key = self.students[student_id]["nickname_key"]
        if any(
            sid != student_id
            and row["record"].class_id == new_class_id
            and row["nickname_key"] == nickname_key
            for sid, row in self.students.items()
        ):
            raise NameTaken("That nickname is already used in the destination class.")
        updated = replace(record, class_id=new_class_id)
        self.students[student_id]["record"] = updated
        return updated

    def delete_student(self, student_id: str) -> None:
        self.delete_students([student_id])

    def delete_students(self, student_ids: Sequence[str]) -> int:
        ids = [str(student_id) for student_id in student_ids if str(student_id)]
        if not ids:
            return 0
        missing = [student_id for student_id in ids if student_id not in self.students]
        if missing:
            raise NotFound("Student not found.")
        id_set = set(ids)
        attempt_ids = [
            attempt_id for attempt_id, attempt in self.attempts.items()
            if attempt.student_id in id_set
        ]
        for attempt_id in attempt_ids:
            self.answers.pop(attempt_id, None)
            self.attempts.pop(attempt_id, None)
        self.practice = [row for row in self.practice if row.student_id not in id_set]
        self.mastery = {key: row for key, row in self.mastery.items() if key[0] not in id_set}
        self.learning_progress = {key: row for key, row in self.learning_progress.items() if key[0] not in id_set}
        for student_id in id_set:
            self.student_focus_overrides.pop(student_id, None)
        self.mystery_unlocks = {key: row for key, row in self.mystery_unlocks.items() if key[0] not in id_set}
        self.mystery_guesses = {key: row for key, row in self.mystery_guesses.items() if key[0] not in id_set}
        for student_id in id_set:
            self.students.pop(student_id, None)
        return len(id_set)

    def delete_class_students(self, class_id: str) -> int:
        ids = [
            student_id for student_id, row in self.students.items()
            if row["record"].class_id == str(class_id)
        ]
        return self.delete_students(ids)

    # ----- Daily challenge -----
    def get_or_create_challenge(
        self, challenge_date: date | str, challenge_version: str, facts: Sequence[Fact]
    ) -> ChallengeRecord:
        key = _as_date_key(challenge_date)
        existing = self.challenges.get(key)
        if existing:
            # Once a Daily has been created for a calendar date, that stored
            # challenge is authoritative for the rest of the day.  A later app
            # deployment must never invalidate students' already-live Daily.
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
        self.answers[attempt_id] = []
        for question_number, ((fact, value), latency) in enumerate(zip(answers, latencies), start=1):
            answer = AnswerRecord(
                attempt_id=attempt_id,
                question_number=question_number,
                a=fact.a,
                b=fact.b,
                student_answer=int(value),
                correct_answer=fact.product,
                correct=int(value) == fact.product,
                submitted_at=when,
                response_seconds=None if latency is None else float(latency),
            )
            self.answers[attempt_id].append(answer)
            if max(fact.key) <= 10:
                self.record_mastery_evidence(
                    attempt.student_id, fact, answer.correct,
                    response_seconds=answer.response_seconds, practiced_at=when,
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
        self.get_or_create_learning_progress(attempt.student_id, attempt.challenge_id)
        if correct_count == 10:
            self.mark_fix_complete(attempt.student_id, attempt.challenge_id)
        return updated

    def rebuild_mastery(self, student_id: str) -> list[MasterySnapshot]:
        self.get_student(student_id)
        self.mastery = {key: row for key, row in self.mastery.items() if key[0] != student_id}
        events = []
        completed_attempt_ids = {
            attempt.attempt_id for attempt in self.attempts.values()
            if attempt.student_id == student_id and attempt.completed_at is not None
        }
        for attempt_id in completed_attempt_ids:
            for answer in self.answers.get(attempt_id, []):
                if max(answer.a, answer.b) <= 10:
                    events.append((answer.submitted_at, answer.a, answer.b, answer.correct, answer.response_seconds))
        for row in self.practice:
            if row.student_id == student_id and row.activity_type == "focus" and not row.is_retry and max(row.a, row.b) <= 10:
                events.append((row.created_at, row.a, row.b, row.correct, row.response_seconds))
        events.sort(key=lambda item: item[0])
        for when, a, b, correct, seconds in events:
            self.record_mastery_evidence(
                student_id, Fact(a=a, b=b, tier="core"), correct,
                response_seconds=seconds, practiced_at=when,
            )
        return self.get_mastery(student_id)

    def reset_daily_attempt(self, student_id: str, challenge_id: str) -> bool:
        target = self.get_attempt_for_student(student_id, challenge_id)
        if target is None:
            return False
        self.practice = [
            row for row in self.practice
            if not (row.student_id == student_id and row.challenge_id == challenge_id and row.activity_type in {"fix_miss", "focus"})
        ]
        self.learning_progress.pop((student_id, challenge_id), None)
        self.answers.pop(target.attempt_id, None)
        self.attempts.pop(target.attempt_id, None)
        self.rebuild_mastery(student_id)
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


    # ----- Adaptive learning / Practice -----
    def record_mastery_evidence(
        self, student_id: str, fact: Fact, correct: bool, *,
        response_seconds: float | None = None, practiced_at: datetime | None = None,
    ) -> MasterySnapshot:
        self.get_student(student_id)
        a, b = canonical_pair(fact.a, fact.b)
        if not (2 <= a <= b <= 10):
            raise ValueError("The persistent mastery map covers core 2s-10s facts only.")
        key = (student_id, a, b)
        updated = update_snapshot(
            self.mastery.get(key), a=a, b=b, correct=bool(correct),
            response_seconds=response_seconds, practiced_at=practiced_at,
        )
        self.mastery[key] = updated
        return updated

    def get_mastery(self, student_id: str) -> list[MasterySnapshot]:
        self.get_student(student_id)
        rows = [row for (sid, _, _), row in self.mastery.items() if sid == student_id]
        if rows:
            return rows
        # Backfill any v1 Daily history the first time v2 asks for a profile.
        has_history = any(
            attempt.student_id == student_id and attempt.completed_at is not None
            for attempt in self.attempts.values()
        ) or any(
            row.student_id == student_id and row.activity_type == "focus" and not row.is_retry
            for row in self.practice
        )
        return self.rebuild_mastery(student_id) if has_history else []

    def mastery_summary(self, student_id: str) -> dict[str, int]:
        return mastery_counts(self.get_mastery(student_id))

    def class_mastery_summary(self, class_id: str) -> list[dict]:
        students = self.list_students(class_id)
        result = []
        for a in range(2, 11):
            for b in range(a, 11):
                counts = {"Fluent": 0, "Building": 0, "Focus": 0, "Unknown": 0}
                for student in students:
                    row = self.mastery.get((student.student_id, a, b), MasterySnapshot(a=a, b=b))
                    counts[row.status] += 1
                result.append({"a": a, "b": b, "fact": f"{a} × {b}", **counts, "students": len(students)})
        return result

    def get_or_create_learning_progress(self, student_id: str, challenge_id: str) -> LearningProgressRecord:
        self.get_student(student_id)
        key = (student_id, challenge_id)
        if key not in self.learning_progress:
            self.learning_progress[key] = LearningProgressRecord(student_id=student_id, challenge_id=challenge_id)
        return self.learning_progress[key]

    def get_learning_progress(self, student_id: str, challenge_id: str) -> LearningProgressRecord:
        return self.get_or_create_learning_progress(student_id, challenge_id)

    def set_focus_plan(self, student_id: str, challenge_id: str, facts: Sequence[Fact]) -> LearningProgressRecord:
        progress = self.get_or_create_learning_progress(student_id, challenge_id)
        if progress.focus_plan:
            return progress
        updated = replace(progress, focus_plan=tuple(facts))
        self.learning_progress[(student_id, challenge_id)] = updated
        return updated

    def mark_fix_complete(self, student_id: str, challenge_id: str) -> LearningProgressRecord:
        progress = self.get_or_create_learning_progress(student_id, challenge_id)
        updated = replace(progress, fix_completed_at=progress.fix_completed_at or utc_now())
        self.learning_progress[(student_id, challenge_id)] = updated
        return updated

    def mark_focus_complete(self, student_id: str, challenge_id: str) -> LearningProgressRecord:
        progress = self.get_or_create_learning_progress(student_id, challenge_id)
        now = utc_now()
        updated = replace(
            progress,
            focus_completed_at=progress.focus_completed_at or now,
            completed_at=progress.completed_at or now,
        )
        self.learning_progress[(student_id, challenge_id)] = updated
        return updated

    def record_practice(
        self, student_id: str | None, focus: str, fact: Fact, student_answer: int, *,
        response_seconds: float | None = None, challenge_id: str | None = None,
        activity_type: str = "free_practice", activity_index: int | None = None,
        is_retry: bool = False, count_for_mastery: bool = False,
    ) -> PracticeRecord:
        if student_id is not None:
            self.get_student(student_id)
        if (
            student_id is not None and challenge_id is not None and activity_type == "focus"
            and activity_index is not None and not is_retry
        ):
            existing = next((
                row for row in self.practice
                if row.student_id == student_id and row.challenge_id == challenge_id
                and row.activity_type == "focus" and row.activity_index == activity_index and not row.is_retry
            ), None)
            if existing is not None:
                return existing
        record = PracticeRecord(
            student_id=student_id,
            focus=str(focus),
            a=fact.a,
            b=fact.b,
            student_answer=int(student_answer),
            correct_answer=fact.product,
            correct=int(student_answer) == fact.product,
            created_at=utc_now(),
            response_seconds=None if response_seconds is None else float(response_seconds),
            challenge_id=challenge_id,
            activity_type=str(activity_type),
            activity_index=activity_index,
            is_retry=bool(is_retry),
        )
        self.practice.append(record)
        if count_for_mastery and student_id is not None and not is_retry and max(fact.key) <= 10:
            self.record_mastery_evidence(
                student_id, fact, record.correct, response_seconds=response_seconds, practiced_at=record.created_at
            )
        return record

    def record_practice_batch(
        self, student_id: str, focus: str, challenge_id: str, activity_type: str, events: Sequence[Mapping]
    ) -> list[PracticeRecord]:
        records = []
        seen_ids: set[str] = set()
        for event in events:
            event_id = str(event.get("client_event_id") or "").strip()
            if not event_id or event_id in seen_ids or event_id in self.practice_event_ids:
                continue
            seen_ids.add(event_id)
            self.practice_event_ids.add(event_id)
            fact = Fact(int(event["a"]), int(event["b"]), "guided")
            records.append(self.record_practice(
                student_id, focus, fact, int(event["student_answer"]),
                response_seconds=float(event.get("response_seconds") or 0.0),
                challenge_id=challenge_id, activity_type=activity_type,
                activity_index=int(event["activity_index"]),
                is_retry=bool(event.get("is_retry")), count_for_mastery=False,
            ))
        return records

    def learning_activity_rows(self, student_id: str, challenge_id: str, activity_type: str) -> list[PracticeRecord]:
        return sorted(
            [row for row in self.practice if row.student_id == student_id and row.challenge_id == challenge_id and row.activity_type == activity_type],
            key=lambda row: (row.activity_index if row.activity_index is not None else 999, row.created_at),
        )

    def practice_summary(self, student_id: str) -> dict[str, int]:
        rows = [row for row in self.practice if row.student_id == student_id]
        return {"attempts": len(rows), "correct": sum(row.correct for row in rows)}

    def set_global_focus_override(self, family: int | None) -> None:
        self.global_focus_override = family

    def set_class_focus_override(self, class_id: str, family: int | None) -> None:
        self.class_focus_overrides[class_id] = family

    def set_student_focus_override(self, student_id: str, family: int | None) -> None:
        self.student_focus_overrides[student_id] = family

    def get_effective_focus_override(self, student_id: str) -> int | None:
        student = self.get_student(student_id)
        return (
            self.student_focus_overrides.get(student_id)
            or self.class_focus_overrides.get(student.class_id)
            or self.global_focus_override
        )

    def student_learning_stats(self, student_id: str, through_date: date | str) -> dict[str, int]:
        self.get_student(student_id)
        target = date.fromisoformat(through_date) if isinstance(through_date, str) else through_date
        challenge_dates = {ch.challenge_id: date.fromisoformat(ch.challenge_date) for ch in self.challenges.values()}
        assigned = sorted({d for d in challenge_dates.values() if d <= target and d.weekday() < 5})
        completed = {
            challenge_dates[cid]
            for (sid, cid), row in self.learning_progress.items()
            if sid == student_id and row.completed_at is not None and cid in challenge_dates and challenge_dates[cid].weekday() < 5
        }
        current = 0
        for d in reversed(assigned):
            if d in completed:
                current += 1
            else:
                break
        longest = 0
        run = 0
        for d in assigned:
            if d in completed:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
        return {"current_streak": current, "longest_streak": longest, "stars": len(completed)}

    def get_global_focus_override(self) -> int | None:
        return self.global_focus_override

    def get_class_focus_override(self, class_id: str) -> int | None:
        return self.class_focus_overrides.get(class_id)

    def get_student_focus_override(self, student_id: str) -> int | None:
        return self.student_focus_overrides.get(student_id)

    def class_learning_stats(self, class_id: str, through_date: date | str) -> dict[str, dict[str, int]]:
        return {
            student.student_id: self.student_learning_stats(student.student_id, through_date)
            for student in self.list_students(class_id)
        }

    def class_learning_progress(self, class_id: str, challenge_id: str) -> dict[str, LearningProgressRecord]:
        ids = {student.student_id for student in self.list_students(class_id)}
        return {
            sid: row for (sid, cid), row in self.learning_progress.items()
            if cid == challenge_id and sid in ids
        }

    # ----- Weekly Mystery -----
    def get_weekly_mystery(self, week_start: date | str) -> WeeklyMysteryRecord | None:
        return self.weekly_mysteries.get(_as_date_key(week_start))

    def get_or_create_weekly_mystery(self, week_start: date | str, mystery_key: str) -> WeeklyMysteryRecord:
        key = _as_date_key(week_start)
        existing = self.weekly_mysteries.get(key)
        if existing is not None:
            return existing
        now = utc_now()
        record = WeeklyMysteryRecord(key, str(mystery_key), now, now)
        self.weekly_mysteries[key] = record
        return record

    def weekly_mystery_locked(self, week_start: date | str) -> bool:
        key = _as_date_key(week_start)
        return any(row.week_start == key for row in self.mystery_unlocks.values())

    def replace_weekly_mystery(self, week_start: date | str, mystery_key: str) -> WeeklyMysteryRecord:
        key = _as_date_key(week_start)
        if self.weekly_mystery_locked(key):
            raise FactStoreError("This week's mystery is locked because a student has already unlocked a clue.")
        existing = self.weekly_mysteries.get(key)
        now = utc_now()
        record = WeeklyMysteryRecord(key, str(mystery_key), existing.created_at if existing else now, now)
        self.weekly_mysteries[key] = record
        return record

    def unlock_mystery_day(
        self, student_id: str, week_start: date | str, day_number: int, challenge_id: str
    ) -> MysteryUnlockRecord:
        self.get_student(student_id)
        if challenge_id not in {ch.challenge_id for ch in self.challenges.values()}:
            raise NotFound("Challenge not found.")
        day_number = int(day_number)
        if day_number not in {1, 2, 3, 4, 5}:
            raise ValueError("Mystery day number must be 1 through 5.")
        week_key = _as_date_key(week_start)
        row_key = (student_id, week_key, day_number)
        existing = self.mystery_unlocks.get(row_key)
        if existing is not None:
            return existing
        record = MysteryUnlockRecord(student_id, week_key, day_number, challenge_id, utc_now())
        self.mystery_unlocks[row_key] = record
        return record

    def list_mystery_unlocks(self, student_id: str, week_start: date | str) -> list[MysteryUnlockRecord]:
        week_key = _as_date_key(week_start)
        return sorted(
            [row for row in self.mystery_unlocks.values() if row.student_id == student_id and row.week_start == week_key],
            key=lambda row: row.day_number,
        )

    def get_mystery_guess(
        self, student_id: str, week_start: date | str, *, guess_day: int | None = None
    ) -> MysteryGuessRecord | None:
        week_key = _as_date_key(week_start)
        if guess_day is not None:
            return self.mystery_guesses.get((student_id, week_key, int(guess_day)))
        rows = self.list_mystery_guesses(student_id, week_key)
        return rows[0] if rows else None

    def list_mystery_guesses(self, student_id: str, week_start: date | str) -> list[MysteryGuessRecord]:
        week_key = _as_date_key(week_start)
        return sorted(
            [row for row in self.mystery_guesses.values() if row.student_id == student_id and row.week_start == week_key],
            key=lambda row: (row.guess_day, row.guessed_at),
        )

    def submit_mystery_guess(
        self, student_id: str, week_start: date | str, guess_text: str, *,
        correct: bool, clue_count: int, guess_day: int = 4,
    ) -> MysteryGuessRecord:
        self.get_student(student_id)
        week_key = _as_date_key(week_start)
        guess_day = int(guess_day)
        if guess_day not in {4, 5}:
            raise ValueError("Mystery guesses are only allowed on Thursday or Friday.")
        row_key = (student_id, week_key, guess_day)
        existing = self.mystery_guesses.get(row_key)
        if existing is not None:
            return existing
        cleaned = re.sub(r"\s+", " ", str(guess_text or "").strip())
        if not cleaned:
            raise ValueError("Type a guess before submitting.")
        clue_count = int(clue_count)
        if clue_count not in {1, 2, 3, 4, 5}:
            raise ValueError("Clue count must be 1 through 5.")
        record = MysteryGuessRecord(
            student_id, week_key, cleaned[:80], bool(correct), clue_count, utc_now(), guess_day
        )
        self.mystery_guesses[row_key] = record
        return record

    def mystery_student_stats(self, student_id: str) -> dict[str, int | None]:
        self.get_student(student_id)
        rows = [row for row in self.mystery_guesses.values() if row.student_id == student_id]
        correct_rows = [row for row in rows if row.correct]
        solved_weeks = {row.week_start for row in correct_rows}
        return {
            "guesses": len(rows),
            "solved": len(solved_weeks),
            "earliest_solve": min((row.clue_count for row in correct_rows), default=None),
        }

    def weekly_mystery_teacher_stats(self, week_start: date | str) -> dict[str, int]:
        week_key = _as_date_key(week_start)
        unlocks = [row for row in self.mystery_unlocks.values() if row.week_start == week_key]
        guesses = [row for row in self.mystery_guesses.values() if row.week_start == week_key]
        return {
            "students_unlocked": len({row.student_id for row in unlocks}),
            "clues_unlocked": len(unlocks),
            "guesses": len(guesses),
            "correct": len({row.student_id for row in guesses if row.correct}),
        }
