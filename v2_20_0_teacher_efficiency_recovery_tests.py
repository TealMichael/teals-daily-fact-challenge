from __future__ import annotations

from datetime import date
import hashlib
from pathlib import Path

from daily_modes import daily_mode_setting_key
from fact_engine import APP_VERSION, CHALLENGE_VERSION, daily_facts_for_date
from fact_store import FactStoreError, InMemoryFactStore, NameTaken
from teacher_mystery_raffle import mystery_raffle_snapshot
from teacher_planning import load_daily_modes, save_daily_modes_bulk, school_days_for_week

ROOT = Path(__file__).resolve().parent
CHECKS = 0


def check(label: str, condition: bool) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1


check("v2.20.0 version", APP_VERSION == "2.21.0")
check("multiplication challenge contract untouched", CHALLENGE_VERSION == "TDFC-DAILY-v1")


class CountingStore(InMemoryFactStore):
    def __init__(self):
        super().__init__()
        self.calls = {"get_one": 0, "get_many": 0, "set_one": 0, "set_many": 0, "delete_one": 0, "delete_many": 0}

    def get_app_setting(self, setting_key: str):
        self.calls["get_one"] += 1
        return super().get_app_setting(setting_key)

    def get_app_settings(self, setting_keys):
        self.calls["get_many"] += 1
        return super().get_app_settings(setting_keys)

    def set_app_setting(self, setting_key: str, value) -> None:
        self.calls["set_one"] += 1
        return super().set_app_setting(setting_key, value)

    def set_app_settings(self, values) -> None:
        self.calls["set_many"] += 1
        return super().set_app_settings(values)

    def delete_app_setting(self, setting_key: str) -> None:
        self.calls["delete_one"] += 1
        return super().delete_app_setting(setting_key)

    def delete_app_settings(self, setting_keys) -> None:
        self.calls["delete_many"] += 1
        return super().delete_app_settings(setting_keys)

    def clear_counts(self):
        for key in self.calls:
            self.calls[key] = 0


# Weekly Daily 10 planning: 20 cells load once, unchanged saves do nothing,
# changed defaults/alternates batch into at most two writes.
store = CountingStore()
classes = [store.create_class(f"Block {i}") for i in range(1, 5)]
week = date(2026, 9, 7)
days = school_days_for_week(week)
store.set_app_setting(daily_mode_setting_key(days[0], classes[0].class_id), "Addition Facts")
store.clear_counts()
grid = load_daily_modes(store, [c.class_id for c in classes], days)
check("weekly grid contains all 20 cells", len(grid) == 20)
check("weekly grid uses one bulk settings read", store.calls["get_many"] == 1)
check("weekly grid avoids single settings reads", store.calls["get_one"] == 0)
check("saved alternate mode loads correctly", grid[(classes[0].class_id, days[0])] == "Addition Facts")
check("default multiplication still loads correctly", grid[(classes[1].class_id, days[1])] == "Multiplication")
store.clear_counts()
check("unchanged weekly save changes zero cells", save_daily_modes_bulk(store, dict(grid), current=grid) == 0)
check("unchanged weekly save makes no writes", store.calls["set_many"] == 0 and store.calls["delete_many"] == 0 and store.calls["set_one"] == 0 and store.calls["delete_one"] == 0)
planned = dict(grid)
planned[(classes[0].class_id, days[0])] = "Multiplication"  # delete one alternate setting
planned[(classes[1].class_id, days[1])] = "Division Facts"  # upsert one alternate setting
planned[(classes[2].class_id, days[2])] = "Mixed"           # upsert another
store.clear_counts()
check("three weekly boxes reported changed", save_daily_modes_bulk(store, planned, current=grid) == 3)
check("alternate weekly changes share one bulk upsert", store.calls["set_many"] == 1 and store.calls["set_one"] == 0)
check("multiplication reset shares one bulk delete", store.calls["delete_many"] == 1 and store.calls["delete_one"] == 0)
check("weekly save result persisted", load_daily_modes(store, [c.class_id for c in classes], days) == planned)

# Bulk app-settings behavior itself.
settings = InMemoryFactStore()
settings.set_app_settings({"a": 1, "b": {"x": 2}, "c": "three"})
check("bulk app settings round-trip", settings.get_app_settings(["a", "b", "c"]) == {"a": 1, "b": {"x": 2}, "c": "three"})
settings.delete_app_settings(["a", "c"])
check("bulk app settings delete", settings.get_app_settings(["a", "b", "c"]) == {"b": {"x": 2}})

# Bulk roster moves keep the destination uniqueness contract and move atomically.
move_store = InMemoryFactStore()
source_a = move_store.create_class("A")
source_b = move_store.create_class("B")
dest = move_store.create_class("Destination")
s1 = move_store.create_student(source_a.class_id, "Alpha", "1111")
s2 = move_store.create_student(source_a.class_id, "Beta", "2222")
check("bulk move moves two students", move_store.move_students([s1.student_id, s2.student_id], dest.class_id) == 2)
check("bulk move updates both class ids", all(move_store.get_student(s.student_id).class_id == dest.class_id for s in (s1, s2)))
conflict = move_store.create_student(source_b.class_id, "Alpha", "3333")
try:
    move_store.move_students([conflict.student_id], dest.class_id)
    conflict_blocked = False
except NameTaken:
    conflict_blocked = True
check("bulk move still blocks duplicate nicknames", conflict_blocked)
check("failed bulk move leaves student in original class", move_store.get_student(conflict.student_id).class_id == source_b.class_id)

# Warm-Up all-class save: combined save works, and any real-student answer locks
# the operation before another class is changed.
warm = InMemoryFactStore()
wc1, wc2 = warm.create_class("W1"), warm.create_class("W2")
q1 = {"prompt": "1+1", "question_type": "Short answer", "correct_answer": "2"}
q2 = {"prompt": "2+2", "question_type": "Short answer", "correct_answer": "4"}
saved = warm.save_warmup_sets_bulk([wc1.class_id, wc2.class_id], week, q1, q2)
check("bulk Warm-Up saves both classes", len(saved) == 2)
check("bulk Warm-Up returns one set per class", {row.class_id for row in saved} == {wc1.class_id, wc2.class_id})
real = warm.create_student(wc1.class_id, "WarmKid", "2468")
warm.record_warmup_answer(
    warmup_set_id=saved[0].warmup_set_id, student_id=real.student_id, class_id=wc1.class_id,
    warmup_date=week, question_slot=1, question_type="Short answer", prompt="1+1",
    standard_code="5.CA.1", standard_description="test", student_answer="2", correct_answer="2", correct=True,
)
old_wc2 = warm.get_warmup_set(wc2.class_id, week)
try:
    warm.save_warmup_sets_bulk([wc1.class_id, wc2.class_id], week, {**q1, "prompt": "new"}, q2)
    warm_locked = False
except FactStoreError:
    warm_locked = True
check("bulk Warm-Up respects real-student lock", warm_locked)
check("locked bulk Warm-Up does not partially change another class", warm.get_warmup_set(wc2.class_id, week).question_one == old_wc2.question_one)


def complete_mult_day(target_store, student, day):
    facts = daily_facts_for_date(day)
    challenge = target_store.get_or_create_challenge(day, CHALLENGE_VERSION, facts)
    attempt = target_store.get_or_create_attempt(student.student_id, challenge.challenge_id)
    target_store.complete_full_attempt(attempt.attempt_id, [(f, f.product) for f in facts], 20.0, response_seconds=[1.0] * 10)
    target_store.mark_focus_complete(student.student_id, challenge.challenge_id)
    return challenge


def complete_alt_day(target_store, student, day):
    facts = daily_facts_for_date(day)
    challenge = target_store.get_or_create_challenge(day, CHALLENGE_VERSION, facts)
    questions = [{"prompt": f"{i}+1", "correct_answer": i + 1, "kind": "addition"} for i in range(10)]
    attempt = target_store.get_or_create_attempt(student.student_id, challenge.challenge_id, daily_mode="Addition Facts", custom_questions=questions)
    target_store.complete_custom_attempt(attempt.attempt_id, [i + 1 for i in range(10)], 20.0)
    target_store.mark_alternate_focus_complete(student.student_id, challenge.challenge_id, "Addition Facts")
    return challenge


# Class-wide clue repair must restore receipts only from proven completed routines.
repair = InMemoryFactStore()
rc = repair.create_class("Block 1")
r1 = repair.create_student(rc.class_id, "NeedsClue", "1111")
r2 = repair.create_student(rc.class_id, "AlreadyGood", "2222")
r3 = repair.create_student(rc.class_id, "Incomplete", "3333")
mon = complete_mult_day(repair, r1, date(2026, 9, 7))
tue = complete_alt_day(repair, r2, date(2026, 9, 8))
# r3 finishes Daily but not Focus, so no earned clue is provable.
facts = daily_facts_for_date(date(2026, 9, 9))
wed = repair.get_or_create_challenge(date(2026, 9, 9), CHALLENGE_VERSION, facts)
r3_attempt = repair.get_or_create_attempt(r3.student_id, wed.challenge_id)
repair.complete_full_attempt(r3_attempt.attempt_id, [(f, f.product) for f in facts], 20.0, response_seconds=[1.0] * 10)
repair.unlock_mystery_day(r2.student_id, week, 2, tue.challenge_id)
result = repair.repair_missing_mystery_clues_for_class(rc.class_id, week, through_day_number=3)
check("repair restores exactly one student's missing receipt", result["repaired_count"] == 1)
check("repair identifies the correct student", result["repaired"][0]["nickname"] == "NeedsClue")
check("repair records the correct day", result["repaired"][0]["days"] == [1])
check("already-correct student is not duplicated", "AlreadyGood" in result["already_ok"])
check("incomplete student is not granted a clue", "Incomplete" in result["incomplete"])
check("missing clue receipt now exists", [u.day_number for u in repair.list_mystery_unlocks(r1.student_id, week)] == [1])
check("incomplete student still has no clue receipt", repair.list_mystery_unlocks(r3.student_id, week) == [])
second = repair.repair_missing_mystery_clues_for_class(rc.class_id, week, through_day_number=3)
check("repair is idempotent", second["repaired_count"] == 0 and "NeedsClue" in second["already_ok"])

# Bulk reopen: alternate reset must not rebuild/remove existing multiplication
# mastery; multiplication reset must remove the reset day's mastery evidence.
reset_store = InMemoryFactStore()
reset_class = reset_store.create_class("Reset")
student = reset_store.create_student(reset_class.class_id, "ResetKid", "4444")
old_mult = complete_mult_day(reset_store, student, date(2026, 9, 7))
mastery_before_alt = reset_store.get_mastery(student.student_id)
alt = complete_alt_day(reset_store, student, date(2026, 9, 8))
check("bulk reopen removes alternate attempt", reset_store.reset_daily_attempts([student.student_id], alt.challenge_id) == 1)
check("alternate reopen leaves multiplication mastery unchanged", reset_store.get_mastery(student.student_id) == mastery_before_alt)
check("alternate attempt really removed", reset_store.get_attempt_for_student(student.student_id, alt.challenge_id) is None)
check("single reopen delegates to same safe bulk behavior", reset_store.reset_daily_attempt(student.student_id, alt.challenge_id) is False)
check("bulk reopen removes multiplication attempt", reset_store.reset_daily_attempts([student.student_id], old_mult.challenge_id) == 1)
check("multiplication mastery rebuild removes deleted day's evidence", reset_store.get_mastery(student.student_id) == [])

# Raffle snapshot: saved winner settings are retrieved in one bulk read rather
# than one request per class.
raffle = CountingStore()
rclasses = [raffle.create_class(f"R{i}") for i in range(4)]
for klass in rclasses:
    raffle.set_app_setting(f"weekly_mystery_raffle::{week.isoformat()}::{klass.class_id}", {"student_id": "saved", "nickname": "Saved"})
raffle.clear_counts()
snap = mystery_raffle_snapshot(raffle, week)
check("raffle snapshot includes all classes", len(snap["classes"]) == 4)
check("raffle saved winners use one bulk settings read", raffle.calls["get_many"] == 1)
check("raffle snapshot avoids per-class settings reads", raffle.calls["get_one"] == 0)

# Static production contracts for v2.20's request consolidation and recovery UI.
app = (ROOT / "app.py").read_text(encoding="utf-8")
supa = (ROOT / "supabase_fact_store.py").read_text(encoding="utf-8")
today_ui = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")
daily_setup = (ROOT / "teacher_daily_setup_ui.py").read_text(encoding="utf-8")
intel_ui = (ROOT / "teacher_intelligence_ui.py").read_text(encoding="utf-8")
warm_ui = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
recovery_ui = (ROOT / "teacher_recovery_ui.py").read_text(encoding="utf-8")
raffle_helper = (ROOT / "teacher_mystery_raffle.py").read_text(encoding="utf-8")
warm_settings = (ROOT / "teacher_warmup_settings.py").read_text(encoding="utf-8")

check("Today loads class rosters in bulk", "list_students_for_classes" in today_ui)
check("Today loads Daily statuses in bulk", "daily_status_for_classes" in today_ui)
check("Today bulk-loads Daily modes", "load_daily_modes" in today_ui)
check("selected Today class reuses overview roster", 'selected_snapshot.get("students")' in today_ui)
check("weekly setup bulk-loads grid", "current_grid = load_daily_modes" in daily_setup)
check("weekly setup bulk-saves changed cells", "save_daily_modes_bulk" in daily_setup)
check("weekly reset has bulk settings delete", "delete_app_settings" in daily_setup)
check("Student Support history is selected-student only", "students=[student]" in intel_ui)
check("Warm-Up copy-all uses bulk save", "save_warmup_sets_bulk" in warm_ui)
check("Warm-Up recipients use bulk settings", "get_app_settings" in warm_settings and "set_app_settings" in warm_settings)
check("recovery tools are opt-in gated", '"🚑 Show class recovery tools"' in recovery_ui)
check("recovery has class clue repair", "repair_missing_mystery_clues_for_class" in recovery_ui)
check("recovery has bulk Daily reopen", "reset_daily_attempts" in recovery_ui)
check("Supabase reset rebuild is conditional", 'rebuild_ids = list(dict.fromkeys(' in supa and 'daily_mode") or "Multiplication") == "Multiplication"' in supa)
check("bulk mastery rebuild preserves first-try Focus only", '.eq("activity_type", "focus")' in supa and '.eq("is_retry", False)' in supa)
check("bulk mastery rebuild paginates Focus history", 'page_start += page_size' in supa and '.range(page_start, page_start + page_size - 1)' in supa)
check("Mystery raffle uses one snapshot", "mystery_raffle_snapshot" in raffle_helper and "get_app_settings" in raffle_helper)
check("ensure Mystery avoids duplicate plan resolution read", "mystery_from_plan(plan) if plan else mystery_for_key(record.mystery_key)" in app)
check("bulk roster UI uses move_students", 'getattr(store, "move_students", None)' in app)
check("teacher app stays under architecture cap", len(app.splitlines()) < 3000)
check("Warm-Up module stays under architecture cap", len(warm_ui.splitlines()) < 700)

# No student interaction / multiplication drift.
PROTECTED = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "daily_alt_component/index.html": "332ee7265c450b00d4848a059f000439dba2089c4ec765bf18f41e2bed734c4d",
    "alt_fix_component/index.html": "6a60d52ce0775250b54477c2cafb909f3cf5e4cb6fe53d51795ca30aacda64d4",
    "alt_focus_component/index.html": "3fbc588093066e786dd4e579f9a4f0659d5480c5108f632a63f109ffd3460a86",
    "student_alt_daily_ui.py": "8ee99c33158a7de165bde0dcfcd59fcf4b1bce4395e1031ebe1ed8153b087afe",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
}
for relative, expected in PROTECTED.items():
    check(f"protected source unchanged: {relative}", hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected)

print(f"v2.20.0 Teacher Efficiency & Recovery: PASS ({CHECKS}/{CHECKS} checks)")
