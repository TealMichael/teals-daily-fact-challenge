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
from alternate_followup import ALT_MODES, daily_evidence_rows, missed_question_items


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
    is_test: bool = False


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
    learning_evidence_applied_at: datetime | None = None
    daily_mode: str = "Multiplication"
    custom_questions: tuple[dict, ...] = ()
    custom_answers: tuple[int, ...] = ()


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
    first_student_answer: int | None = None
    first_correct: bool | None = None


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


@dataclass(frozen=True)
class AlternateLearningProgressRecord:
    student_id: str
    challenge_id: str
    daily_mode: str
    focus_plan: tuple[dict, ...] = ()
    fix_completed_at: datetime | None = None
    focus_completed_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class AlternateLearningEventRecord:
    event_id: str
    student_id: str
    challenge_id: str
    attempt_id: str
    daily_mode: str
    activity_type: str
    activity_index: int
    domain: str
    skill_key: str
    skill_label: str
    item_key: str
    prompt: str
    student_answer: int
    correct_answer: int
    correct: bool
    is_retry: bool
    created_at: datetime
    response_seconds: float | None = None
    client_event_id: str | None = None


@dataclass(frozen=True)
class WarmupSetRecord:
    warmup_set_id: str
    class_id: str
    warmup_date: str
    question_one: dict
    question_two: dict
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WarmupAnswerRecord:
    warmup_answer_id: str
    warmup_set_id: str
    student_id: str
    class_id: str
    warmup_date: str
    question_slot: int
    question_type: str
    prompt: str
    standard_code: str
    standard_description: str
    student_answer: str
    correct_answer: str
    correct: bool
    answered_at: datetime


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
        self.alternate_learning_progress: dict[tuple[str, str], AlternateLearningProgressRecord] = {}
        self.alternate_learning_events: list[AlternateLearningEventRecord] = []
        self.alternate_event_ids: set[str] = set()
        self.class_focus_overrides: dict[str, int | None] = {}
        self.student_focus_overrides: dict[str, int | None] = {}
        self.global_focus_override: int | None = None
        self.app_settings: dict[str, object] = {}
        self.awtrix_clock_config: dict[str, object] = {
            "block1_class_id": None, "block2_class_id": None, "block3_class_id": None,
            "token_hash": None, "token_hint": None,
        }
        self.awtrix_clock_commands: list[dict] = []
        self._awtrix_command_id = 0
        self.weekly_mysteries: dict[str, WeeklyMysteryRecord] = {}
        self.mystery_unlocks: dict[tuple[str, str, int], MysteryUnlockRecord] = {}
        self.mystery_guesses: dict[tuple[str, str, int], MysteryGuessRecord] = {}
        self.warmup_sets: dict[tuple[str, str], WarmupSetRecord] = {}
        self.warmup_answers: dict[tuple[str, str, int], WarmupAnswerRecord] = {}

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
    def create_student(self, class_id: str, nickname: str, pin: str, *, is_test: bool = False) -> StudentRecord:
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
        record = StudentRecord(_uuid(), class_id, nickname, True, utc_now(), pin, bool(is_test))
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
            if record.class_id == class_id and row["nickname_key"] == key and record.active and not record.is_test:
                return record if verify_pin(pin, row["pin_hash"]) else None
        return None

    def list_students(self, class_id: str, *, include_inactive: bool = False, include_test: bool = False) -> list[StudentRecord]:
        result = [row["record"] for row in self.students.values() if row["record"].class_id == class_id]
        if not include_test:
            result = [student for student in result if not student.is_test]
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

    def get_test_student(self, class_id: str | None = None) -> StudentRecord | None:
        rows = [row["record"] for row in self.students.values() if row["record"].is_test]
        if class_id is not None:
            rows = [row for row in rows if row.class_id == str(class_id)]
        return rows[0] if rows else None

    def reset_test_student(self, class_id: str) -> StudentRecord:
        test_ids = [sid for sid, row in self.students.items() if row["record"].is_test]
        if test_ids:
            self.delete_students(test_ids)
        return self.create_student(str(class_id), "🧪 Test Student", "0000", is_test=True)

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
        self.alternate_learning_progress = {key: row for key, row in self.alternate_learning_progress.items() if key[0] not in id_set}
        self.alternate_learning_events = [row for row in self.alternate_learning_events if row.student_id not in id_set]
        self.alternate_event_ids = {str(row.client_event_id) for row in self.alternate_learning_events if row.client_event_id}
        for student_id in id_set:
            self.student_focus_overrides.pop(student_id, None)
        self.mystery_unlocks = {key: row for key, row in self.mystery_unlocks.items() if key[0] not in id_set}
        self.mystery_guesses = {key: row for key, row in self.mystery_guesses.items() if key[0] not in id_set}
        self.warmup_answers = {key: row for key, row in self.warmup_answers.items() if row.student_id not in id_set}
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

    def get_or_create_attempt(
        self, student_id: str, challenge_id: str, *, daily_mode: str = "Multiplication",
        custom_questions: Sequence[Mapping] | None = None,
    ) -> AttemptRecord:
        self.get_student(student_id)
        if not any(c.challenge_id == challenge_id for c in self.challenges.values()):
            raise NotFound("Challenge not found.")
        for attempt in self.attempts.values():
            if attempt.student_id == student_id and attempt.challenge_id == challenge_id:
                return attempt
        mode = str(daily_mode or "Multiplication")
        questions = tuple(dict(item) for item in (custom_questions or ()))
        if mode != "Multiplication" and len(questions) != 10:
            raise ValueError("Alternate Daily 10 attempts require exactly 10 stored questions.")
        if mode == "Multiplication":
            questions = ()
        record = AttemptRecord(
            _uuid(), student_id, challenge_id, utc_now(),
            daily_mode=mode, custom_questions=questions,
        )
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
                    first_student_answer=int(value),
                    first_correct=int(value) == fact.product,
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
        self.answers[attempt_id] = []
        for question_number, (((fact, value), (evidence_fact, first_value)), latency) in enumerate(
            zip(zip(answers, evidence_answers), latencies), start=1
        ):
            if fact.key != evidence_fact.key:
                raise ValueError("Daily first-answer evidence does not match the Daily fact order.")
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
                first_student_answer=int(first_value),
                first_correct=int(first_value) == fact.product,
            )
            self.answers[attempt_id].append(answer)
        correct_count = sum(answer.correct for answer in self.answers[attempt_id])
        updated = replace(
            attempt,
            timed_started_at=started,
            completed_at=when,
            correct_count=correct_count,
            timed_seconds=seconds,
            learning_evidence_applied_at=None,
        )
        self.attempts[attempt_id] = updated
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
        updated = replace(
            attempt, timed_started_at=started, completed_at=when,
            correct_count=correct_count, timed_seconds=seconds,
            learning_evidence_applied_at=None, custom_answers=tuple(values),
        )
        self.attempts[attempt_id] = updated
        return self.ensure_daily_learning_evidence(attempt_id)

    def ensure_daily_learning_evidence(self, attempt_id: str) -> AttemptRecord:
        """Repair-safe application of Daily evidence after the official score is saved.

        The official Daily result uses the student's final submitted answers.
        Mastery evidence uses the first answer to each fact.  Marking evidence as
        applied only after mastery/progress updates makes a connection interruption
        repairable the next time the completed Daily is opened.
        """
        attempt = self.get_attempt(attempt_id)
        if attempt.completed_at is None or attempt.learning_evidence_applied_at is not None:
            return attempt
        if attempt.daily_mode != "Multiplication":
            self.ensure_alternate_followup_state(attempt_id)
            updated = replace(attempt, learning_evidence_applied_at=utc_now())
            self.attempts[attempt_id] = updated
            return updated
        answers = self.get_answers(attempt_id)
        if len(answers) != 10:
            raise FactStoreError("Daily evidence repair requires all 10 saved answers.")
        when = attempt.completed_at
        for answer in answers:
            if max(answer.a, answer.b) <= 10:
                a, b = canonical_pair(answer.a, answer.b)
                existing = self.mastery.get((attempt.student_id, a, b))
                if existing is not None and existing.last_practiced_at is not None and when <= existing.last_practiced_at:
                    continue
                self.record_mastery_evidence(
                    attempt.student_id, Fact(a=answer.a, b=answer.b, tier="core"),
                    bool(answer.first_correct if answer.first_correct is not None else answer.correct),
                    response_seconds=answer.response_seconds, practiced_at=when,
                )
        self.get_or_create_learning_progress(attempt.student_id, attempt.challenge_id)
        if int(attempt.correct_count or 0) == 10:
            self.mark_fix_complete(attempt.student_id, attempt.challenge_id)
        updated = replace(attempt, learning_evidence_applied_at=utc_now())
        self.attempts[attempt_id] = updated
        return updated

    # ----- Alternate Daily follow-up foundation (v2.17) -----
    def get_or_create_alternate_learning_progress(
        self, student_id: str, challenge_id: str, daily_mode: str
    ) -> AlternateLearningProgressRecord:
        self.get_student(student_id)
        mode = str(daily_mode or "")
        if mode not in ALT_MODES:
            raise ValueError("Alternate learning progress requires an alternate Daily 10 mode.")
        key = (str(student_id), str(challenge_id))
        existing = self.alternate_learning_progress.get(key)
        if existing is not None:
            return existing
        record = AlternateLearningProgressRecord(
            student_id=str(student_id), challenge_id=str(challenge_id), daily_mode=mode
        )
        self.alternate_learning_progress[key] = record
        return record

    def get_alternate_learning_progress(
        self, student_id: str, challenge_id: str, daily_mode: str | None = None
    ) -> AlternateLearningProgressRecord | None:
        record = self.alternate_learning_progress.get((str(student_id), str(challenge_id)))
        if record is None and daily_mode is not None:
            return self.get_or_create_alternate_learning_progress(student_id, challenge_id, daily_mode)
        return record

    def class_alternate_learning_progress(
        self, class_id: str, challenge_id: str, *, students: Sequence[StudentRecord] | None = None
    ) -> dict[str, AlternateLearningProgressRecord]:
        students = list(students) if students is not None else self.list_students(class_id)
        ids = {student.student_id for student in students}
        return {
            sid: row for (sid, cid), row in self.alternate_learning_progress.items()
            if cid == str(challenge_id) and sid in ids
        }

    def alternate_learning_activity_rows(
        self, student_id: str, challenge_id: str, activity_type: str | None = None
    ) -> list[AlternateLearningEventRecord]:
        rows = [
            row for row in self.alternate_learning_events
            if row.student_id == str(student_id) and row.challenge_id == str(challenge_id)
            and (activity_type is None or row.activity_type == str(activity_type))
        ]
        return sorted(rows, key=lambda row: (row.created_at, row.activity_index, row.event_id))

    def _append_alternate_learning_event(
        self, *, student_id: str, challenge_id: str, attempt_id: str, daily_mode: str,
        activity_type: str, activity_index: int, domain: str, skill_key: str,
        skill_label: str, item_key: str, prompt: str, student_answer: int,
        correct_answer: int, correct: bool, is_retry: bool, client_event_id: str,
        response_seconds: float | None = None, created_at: datetime | None = None,
    ) -> AlternateLearningEventRecord:
        if client_event_id in self.alternate_event_ids:
            return next(row for row in self.alternate_learning_events if row.client_event_id == client_event_id)
        record = AlternateLearningEventRecord(
            event_id=_uuid(), student_id=str(student_id), challenge_id=str(challenge_id),
            attempt_id=str(attempt_id), daily_mode=str(daily_mode), activity_type=str(activity_type),
            activity_index=int(activity_index), domain=str(domain), skill_key=str(skill_key),
            skill_label=str(skill_label), item_key=str(item_key), prompt=str(prompt),
            student_answer=int(student_answer), correct_answer=int(correct_answer),
            correct=bool(correct), is_retry=bool(is_retry), created_at=created_at or utc_now(),
            response_seconds=None if response_seconds is None else float(response_seconds),
            client_event_id=str(client_event_id),
        )
        self.alternate_learning_events.append(record)
        self.alternate_event_ids.add(str(client_event_id))
        return record

    def mark_alternate_fix_complete(
        self, student_id: str, challenge_id: str, daily_mode: str
    ) -> AlternateLearningProgressRecord:
        progress = self.get_or_create_alternate_learning_progress(student_id, challenge_id, daily_mode)
        now = utc_now()
        updated = replace(
            progress,
            fix_completed_at=progress.fix_completed_at or now,
            completed_at=progress.completed_at or now,
        )
        self.alternate_learning_progress[(str(student_id), str(challenge_id))] = updated
        return updated

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

        daily_rows = daily_evidence_rows(questions, answers, default_domain=None if attempt.daily_mode == "Mixed" else attempt.daily_mode)
        for row in daily_rows:
            index = int(row["question_number"])
            self._append_alternate_learning_event(
                student_id=attempt.student_id, challenge_id=attempt.challenge_id, attempt_id=attempt.attempt_id,
                daily_mode=attempt.daily_mode, activity_type="daily", activity_index=index,
                domain=row["domain"], skill_key=row["skill_key"], skill_label=row["skill_label"],
                item_key=row["item_key"], prompt=row["prompt"], student_answer=row["student_answer"],
                correct_answer=row["correct_answer"], correct=row["correct"], is_retry=False,
                client_event_id=f"alt-daily:{attempt.attempt_id}:{index}", created_at=attempt.completed_at,
            )

        progress = self.get_or_create_alternate_learning_progress(
            attempt.student_id, attempt.challenge_id, attempt.daily_mode
        )
        missed = missed_question_items(questions, answers, default_domain=None if attempt.daily_mode == "Mixed" else attempt.daily_mode)
        if not missed:
            return self.mark_alternate_fix_complete(attempt.student_id, attempt.challenge_id, attempt.daily_mode)
        corrected = {
            int(row.activity_index) for row in self.alternate_learning_activity_rows(
                attempt.student_id, attempt.challenge_id, "fix_miss"
            ) if row.correct
        }
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
        missed = {
            int(item["question_number"]): item for item in missed_question_items(
                questions, answers, default_domain=None if attempt.daily_mode == "Mixed" else attempt.daily_mode
            )
        }
        submitted: dict[int, int] = {}
        for item in corrections:
            index = int(item.get("question_number"))
            if index in submitted:
                raise ValueError("Each missed question may be corrected once in a saved Fix batch.")
            submitted[index] = int(item.get("student_answer"))
        if set(submitted) != set(missed):
            raise ValueError("Fix Your Misses must correct every missed Daily question.")
        for index, value in submitted.items():
            expected = int(missed[index]["correct_answer"])
            if value != expected:
                raise ValueError("Fix Your Misses can only complete after every missed question is corrected.")
            item = missed[index]
            self._append_alternate_learning_event(
                student_id=attempt.student_id, challenge_id=attempt.challenge_id, attempt_id=attempt.attempt_id,
                daily_mode=attempt.daily_mode, activity_type="fix_miss", activity_index=index,
                domain=item["domain"], skill_key=item["skill_key"], skill_label=item["skill_label"],
                item_key=item["item_key"], prompt=item["prompt"], student_answer=value,
                correct_answer=expected, correct=True, is_retry=True,
                client_event_id=f"alt-fix:{attempt.attempt_id}:{index}",
            )
        return self.ensure_alternate_followup_state(attempt_id)

    def rebuild_mastery(self, student_id: str) -> list[MasterySnapshot]:
        self.get_student(student_id)
        self.mastery = {key: row for key, row in self.mastery.items() if key[0] != student_id}
        events = []
        completed_attempt_ids = {
            attempt.attempt_id for attempt in self.attempts.values()
            if attempt.student_id == student_id and attempt.completed_at is not None and attempt.daily_mode == "Multiplication"
        }
        for attempt_id in completed_attempt_ids:
            for answer in self.answers.get(attempt_id, []):
                if max(answer.a, answer.b) <= 10:
                    events.append((
                        answer.submitted_at, answer.a, answer.b,
                        bool(answer.first_correct if answer.first_correct is not None else answer.correct),
                        answer.response_seconds,
                    ))
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
        self.alternate_learning_progress.pop((str(student_id), str(challenge_id)), None)
        self.alternate_learning_events = [
            row for row in self.alternate_learning_events
            if not (row.student_id == str(student_id) and row.challenge_id == str(challenge_id))
        ]
        self.alternate_event_ids = {str(row.client_event_id) for row in self.alternate_learning_events if row.client_event_id}
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
            attempt.student_id == student_id and attempt.completed_at is not None and attempt.daily_mode == "Multiplication"
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

    # ----- Quick Warm-Up -----
    def get_warmup_set(self, class_id: str, warmup_date: date | str) -> WarmupSetRecord | None:
        return self.warmup_sets.get((str(class_id), _as_date_key(warmup_date)))

    def warmup_set_locked(self, warmup_set_id: str) -> bool:
        test_ids = {sid for sid, row in self.students.items() if row["record"].is_test}
        return any(
            row.warmup_set_id == str(warmup_set_id) and row.student_id not in test_ids
            for row in self.warmup_answers.values()
        )

    def save_warmup_set(self, class_id: str, warmup_date: date | str, question_one: Mapping, question_two: Mapping) -> WarmupSetRecord:
        class_id = str(class_id)
        if class_id not in self.classes:
            raise NotFound("Class not found.")
        key = (class_id, _as_date_key(warmup_date))
        existing = self.warmup_sets.get(key)
        if existing is not None and self.warmup_set_locked(existing.warmup_set_id):
            raise FactStoreError("This Warm-Up is locked because a student has already answered it.")
        if existing is not None:
            # If only the sandbox has answered, editing the trial should reset
            # those sandbox answers so the updated questions can be tested again.
            self.warmup_answers = {k: row for k, row in self.warmup_answers.items() if row.warmup_set_id != existing.warmup_set_id}
        now = utc_now()
        record = WarmupSetRecord(
            existing.warmup_set_id if existing else _uuid(),
            class_id, key[1], dict(question_one), dict(question_two),
            existing.created_at if existing else now, now,
        )
        self.warmup_sets[key] = record
        return record

    def delete_warmup_set(self, class_id: str, warmup_date: date | str) -> None:
        key = (str(class_id), _as_date_key(warmup_date))
        existing = self.warmup_sets.get(key)
        if existing is None:
            return
        if self.warmup_set_locked(existing.warmup_set_id):
            raise FactStoreError("This Warm-Up is locked because a student has already answered it.")
        self.warmup_sets.pop(key, None)
        self.warmup_answers = {k: row for k, row in self.warmup_answers.items() if row.warmup_set_id != existing.warmup_set_id}

    def get_warmup_answers(self, student_id: str, warmup_set_id: str) -> list[WarmupAnswerRecord]:
        rows = [
            row for row in self.warmup_answers.values()
            if row.student_id == str(student_id) and row.warmup_set_id == str(warmup_set_id)
        ]
        return sorted(rows, key=lambda row: row.question_slot)

    def record_warmup_answer(
        self, *, warmup_set_id: str, student_id: str, class_id: str, warmup_date: date | str,
        question_slot: int, question_type: str, prompt: str, standard_code: str,
        standard_description: str, student_answer: str, correct_answer: str, correct: bool,
    ) -> WarmupAnswerRecord:
        date_key = _as_date_key(warmup_date)
        if getattr(self, "_warmup_retention_date", None) != date_key:
            self.clear_old_warmup_response_text(date_key)
            self._warmup_retention_date = date_key
        key = (str(student_id), str(warmup_set_id), int(question_slot))
        existing = self.warmup_answers.get(key)
        if existing is not None:
            return existing
        record = WarmupAnswerRecord(
            _uuid(), str(warmup_set_id), str(student_id), str(class_id), date_key,
            int(question_slot), str(question_type), str(prompt), str(standard_code), str(standard_description),
            str(student_answer), str(correct_answer), bool(correct), utc_now(),
        )
        self.warmup_answers[key] = record
        return record

    def list_warmup_answers(
        self, start_date: date | str, end_date: date | str, *, class_id: str | None = None, include_test: bool = False
    ) -> list[WarmupAnswerRecord]:
        start_key, end_key = _as_date_key(start_date), _as_date_key(end_date)
        test_ids = {sid for sid, row in self.students.items() if row["record"].is_test}
        rows = [row for row in self.warmup_answers.values() if start_key <= row.warmup_date <= end_key]
        if class_id is not None:
            rows = [row for row in rows if row.class_id == str(class_id)]
        if not include_test:
            rows = [row for row in rows if row.student_id not in test_ids]
        return sorted(rows, key=lambda row: (row.warmup_date, row.class_id, row.student_id, row.question_slot))

    def clear_old_warmup_response_text(self, before_date: date | str) -> int:
        """Clear prior-day raw student text while preserving correctness/standards evidence."""
        before_key = _as_date_key(before_date)
        count = 0
        for key, row in list(self.warmup_answers.items()):
            if str(row.warmup_date) < before_key and row.student_answer:
                self.warmup_answers[key] = replace(row, student_answer="")
                count += 1
        return count

    # ----- AWTRIX classroom clock integration (reference backend) -----
    def get_awtrix_clock_config(self) -> dict:
        cfg = dict(self.awtrix_clock_config)
        cfg["has_token"] = bool(cfg.get("token_hash"))
        cfg.pop("token_hash", None)
        return cfg

    def save_awtrix_clock_mapping(self, block1_class_id: str, block2_class_id: str, block3_class_id: str) -> None:
        class_ids = [str(block1_class_id), str(block2_class_id), str(block3_class_id)]
        if len(set(class_ids)) != 3:
            raise ValueError("Block 1, Block 2, and Block 3 must map to three different classes.")
        if any(class_id not in self.classes for class_id in class_ids):
            raise NotFound("One of the selected classes was not found.")
        self.awtrix_clock_config.update({
            "block1_class_id": class_ids[0],
            "block2_class_id": class_ids[1],
            "block3_class_id": class_ids[2],
        })

    def rotate_awtrix_clock_token(self) -> str:
        token = secrets.token_urlsafe(24)
        self.awtrix_clock_config["token_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self.awtrix_clock_config["token_hint"] = token[-6:]
        return token

    def awtrix_block_for_class(self, class_id: str) -> int | None:
        target = str(class_id)
        for block in (1, 2, 3):
            if self.awtrix_clock_config.get(f"block{block}_class_id") == target:
                return block
        return None

    def queue_awtrix_top10(self, block_number: int) -> int:
        block = int(block_number)
        if block not in (1, 2, 3):
            raise ValueError("Block number must be 1, 2, or 3.")
        if not self.awtrix_clock_config.get(f"block{block}_class_id"):
            raise FactStoreError(f"Block {block} is not mapped to a class yet.")
        if not self.awtrix_clock_config.get("token_hash"):
            raise FactStoreError("The classroom clock token has not been generated yet.")
        self._awtrix_command_id += 1
        self.awtrix_clock_commands.append({
            "command_id": self._awtrix_command_id,
            "block_number": block,
            "requested_at": utc_now(),
        })
        return self._awtrix_command_id

    # ----- Private app settings (reference backend) -----
    def get_app_setting(self, setting_key: str):
        return self.app_settings.get(str(setting_key))

    def set_app_setting(self, setting_key: str, value) -> None:
        self.app_settings[str(setting_key)] = value

    def delete_app_setting(self, setting_key: str) -> None:
        self.app_settings.pop(str(setting_key), None)

    @staticmethod
    def _mystery_plan_key(week_start: date | str) -> str:
        return f"weekly_mystery_plan::{_as_date_key(week_start)}"

    def get_mystery_plan(self, week_start: date | str) -> dict | None:
        value = self.get_app_setting(self._mystery_plan_key(week_start))
        return dict(value) if isinstance(value, dict) else None

    def save_mystery_plan(self, week_start: date | str, plan: Mapping) -> None:
        key = _as_date_key(week_start)
        if self.weekly_mystery_locked(key):
            raise FactStoreError("This week's mystery is locked because a student has already unlocked a clue.")
        self.set_app_setting(self._mystery_plan_key(key), dict(plan))

    def clear_mystery_plan(self, week_start: date | str) -> None:
        key = _as_date_key(week_start)
        if self.weekly_mystery_locked(key):
            raise FactStoreError("This week's mystery is locked because a student has already unlocked a clue.")
        self.delete_app_setting(self._mystery_plan_key(key))

    # ----- Weekly Mystery -----
    def completed_mystery_days(
        self, student_id: str, week_start: date | str, *, through_day_number: int = 5
    ) -> list[tuple[int, str]]:
        """Return school days this week whose required routine was truly completed.

        This is used only to repair a missing Mystery unlock after a transient
        connection failure. A genuinely skipped day is never backfilled.
        """
        self.get_student(student_id)
        week_key = _as_date_key(week_start)
        monday = date.fromisoformat(week_key)
        through = max(0, min(5, int(through_day_number)))
        qualified: list[tuple[int, str]] = []
        for day_number in range(1, through + 1):
            day_key = (monday + timedelta(days=day_number - 1)).isoformat()
            challenge = self.get_challenge(day_key)
            if challenge is None:
                continue
            attempt = self.get_attempt_for_student(student_id, challenge.challenge_id)
            if attempt is None or attempt.completed_at is None:
                continue
            if str(attempt.daily_mode or "Multiplication") == "Multiplication":
                progress = self.learning_progress.get((str(student_id), str(challenge.challenge_id)))
                if progress is None or progress.completed_at is None:
                    continue
            else:
                progress = self.alternate_learning_progress.get((str(student_id), str(challenge.challenge_id)))
                if progress is None or progress.completed_at is None:
                    continue
            qualified.append((day_number, challenge.challenge_id))
        return qualified

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
        test_ids = {sid for sid, row in self.students.items() if row["record"].is_test}
        return any(row.week_start == key and row.student_id not in test_ids for row in self.mystery_unlocks.values())

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

    def weekly_mystery_correct_students(self, week_start: date | str) -> list[dict]:
        week_key = _as_date_key(week_start)
        correct = [row for row in self.mystery_guesses.values() if row.week_start == week_key and row.correct]
        by_student = {}
        for row in correct:
            student = self.students.get(row.student_id, {}).get("record")
            if student is None or student.is_test:
                continue
            prior = by_student.get(row.student_id)
            if prior is None or row.guess_day < prior.guess_day:
                by_student[row.student_id] = row
        class_names = {item.class_id: item.class_name for item in self.list_classes(include_inactive=True)}
        result = []
        for sid, guess in by_student.items():
            student = self.students[sid]["record"]
            result.append({
                "student_id": sid, "nickname": student.nickname,
                "class_id": student.class_id, "class_name": class_names.get(student.class_id, "Class"),
                "guess_day": guess.guess_day, "clue_count": guess.clue_count,
            })
        return sorted(result, key=lambda item: (item["class_name"].casefold(), item["nickname"].casefold()))

    def weekly_mystery_teacher_stats(self, week_start: date | str) -> dict[str, int]:
        week_key = _as_date_key(week_start)
        test_ids = {sid for sid, row in self.students.items() if row["record"].is_test}
        unlocks = [row for row in self.mystery_unlocks.values() if row.week_start == week_key and row.student_id not in test_ids]
        guesses = [row for row in self.mystery_guesses.values() if row.week_start == week_key and row.student_id not in test_ids]
        return {
            "students_unlocked": len({row.student_id for row in unlocks}),
            "clues_unlocked": len(unlocks),
            "guesses": len(guesses),
            "correct": len({row.student_id for row in guesses if row.correct}),
        }
