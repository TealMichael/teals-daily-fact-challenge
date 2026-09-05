from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import hashlib

from fact_engine import APP_VERSION, CHALLENGE_VERSION
from fact_store import StudentRecord
from teacher_planning import copy_daily_week, monday_for, next_school_day, previous_school_day, save_warmup_template, warmup_templates, copy_warmup_set, school_days_for_week
from teacher_history import common_multiplication_misses, rank_daily, warmup_summary

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
DAILY_UI = (ROOT / "teacher_daily_setup_ui.py").read_text(encoding="utf-8")
WARMUP_UI = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
HISTORY_UI = (ROOT / "teacher_class_history_ui.py").read_text(encoding="utf-8")

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

check("v2.16 version", APP_VERSION == "2.19.7")
check("student Daily contract unchanged", CHALLENGE_VERSION == "TDFC-DAILY-v1")
check("Class History added to Learning", '["🗓️ Class History"]' in APP and "render_teacher_class_history(store)" in APP)
check("existing Phase 2 Learning tools preserved", '["🧭 Next Steps", "📈 Learning Data", "🛠️ Student Support", "📅 Weekly Recap"]' in APP)
check("Daily setup is now weekly", "Save weekly Daily 10 plan" in DAILY_UI)
check("weekly planner has copy week", "Copy previous week" in DAILY_UI)
check("weekly planner can apply a class plan to all", "Apply this class's week to all classes" in DAILY_UI)
check("weekly planner can reset to multiplication", "Reset week to Multiplication" in DAILY_UI)
check("weekly planner previews tomorrow", "Preview tomorrow" in DAILY_UI and "See the 10 questions" in DAILY_UI)
check("warmup previous-school-day shortcut exists", "Use previous school day's Warm-Up" in WARMUP_UI)
check("warmup reuse next week exists", "Reuse next week" in WARMUP_UI)
check("warmup targeted class copy exists", "Copy to selected class" in WARMUP_UI)
check("warmup templates exist", "Save this Warm-Up as a template" in WARMUP_UI and "Use template on this date" in WARMUP_UI)
check("warmup student preview hides correct answers", "Student preview. Correct answers stay hidden." in WARMUP_UI)
check("Class History includes Daily Top 10", 'st.markdown("##### Top 10")' in HISTORY_UI)
check("Class History includes common misses", "Common multiplication misses" in HISTORY_UI)
check("Class History includes Warm-Up", 'st.markdown("#### Warm-Up")' in HISTORY_UI)
check("Class History protects historical raw response privacy", "For past dates, typed student answers are no longer kept" in HISTORY_UI)
check("Class History includes Mystery status", 'st.markdown("#### Weekly Mystery")' in HISTORY_UI)
check("Class History keeps Mystery details collapsed", "🔒 Mystery answer & clues" in HISTORY_UI)
check("no v2.16 SQL migration", not (ROOT / "RUN_THIS_ONCE_IN_SUPABASE_v2_16.sql").exists())
check("app architecture remains under 3000 lines", len(APP.splitlines()) < 3000)

# Date helpers.
check("week normalizes to Monday", monday_for(date(2026, 9, 3)) == date(2026, 8, 31))
check("school week is Mon-Fri", school_days_for_week(date(2026, 8, 31)) == [date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)])
check("tomorrow skips weekend", next_school_day(date(2026, 9, 4)) == date(2026, 9, 7))
check("previous warmup day skips weekend", previous_school_day(date(2026, 8, 31)) == date(2026, 8, 28))

class FakeSettingsStore:
    def __init__(self):
        self.settings = {}
    def get_app_setting(self, key, default=None):
        return self.settings.get(key, default)
    def set_app_setting(self, key, value):
        self.settings[key] = value
    def delete_app_setting(self, key):
        self.settings.pop(key, None)

class C:
    def __init__(self, cid, name): self.class_id, self.class_name = cid, name

settings = FakeSettingsStore()
classes = [C("c1", "Block 1"), C("c2", "Block 2")]
from daily_modes import daily_mode_setting_key, configured_daily_mode
source = date(2026, 8, 24)
target = date(2026, 8, 31)
settings.set_app_setting(daily_mode_setting_key(source, "c1"), "Integers")
settings.set_app_setting(daily_mode_setting_key(source + __import__('datetime').timedelta(days=1), "c2"), "Division Facts")
copy_daily_week(settings, classes, source, target)
check("copy week preserves configured mode", configured_daily_mode(settings, "c1", target) == "Integers")
check("copy week preserves other class/day mode", configured_daily_mode(settings, "c2", target + __import__('datetime').timedelta(days=1)) == "Division Facts")
check("copy week preserves Multiplication defaults", configured_daily_mode(settings, "c2", target) == "Multiplication")

# Warm-Up template and copy safety.
class Warm:
    def __init__(self, q1, q2, wid="w1"):
        self.question_one, self.question_two, self.warmup_set_id = q1, q2, wid

class FakeWarmStore(FakeSettingsStore):
    def __init__(self):
        super().__init__(); self.sets = {}; self.locked = set()
    def get_warmup_set(self, class_id, day):
        key=(str(class_id), day.isoformat() if hasattr(day,'isoformat') else str(day)); return self.sets.get(key)
    def warmup_set_locked(self, warmup_set_id): return warmup_set_id in self.locked
    def save_warmup_set(self, class_id, day, q1, q2):
        key=(str(class_id), day.isoformat() if hasattr(day,'isoformat') else str(day)); self.sets[key]=Warm(dict(q1),dict(q2),f"{class_id}-{key[1]}"); return self.sets[key]

ws=FakeWarmStore(); source_warm=Warm({"prompt":"6 × 7?","question_type":"Short answer"},{"prompt":"3.4 + 2.1?","question_type":"Short answer"})
copy_warmup_set(ws, source=source_warm, target_class_id="c1", target_date=date(2026,8,31))
check("warmup copy preserves both questions", ws.get_warmup_set("c1",date(2026,8,31)).question_two["prompt"] == "3.4 + 2.1?")
save_warmup_template(ws,"Fact + Decimal",source_warm.question_one,source_warm.question_two)
check("warmup template persists", warmup_templates(ws)[0]["name"] == "Fact + Decimal")
save_warmup_template(ws,"Fact + Decimal",{"prompt":"updated"},source_warm.question_two)
check("template name overwrites rather than duplicates", len(warmup_templates(ws)) == 1 and warmup_templates(ws)[0]["question_one"]["prompt"] == "updated")
locked=ws.save_warmup_set("c2",date(2026,8,31),{"prompt":"old"},{"prompt":"old2"}); ws.locked.add(locked.warmup_set_id)
try:
    copy_warmup_set(ws,source=source_warm,target_class_id="c2",target_date=date(2026,8,31))
    locked_blocked=False
except Exception:
    locked_blocked=True
check("warmup copy cannot overwrite locked student history", locked_blocked)

# Class History ranking and evidence summaries.
rows=[
    {"nickname":"Alpha","correct_count":9,"timed_seconds":31.0,"completed_at":"2026-08-31T10:00:00","daily_mode":"Multiplication","answers":[{"a":7,"b":8,"first_correct":False},{"a":3,"b":4,"first_correct":True}]},
    {"nickname":"Bravo","correct_count":10,"timed_seconds":55.0,"completed_at":"2026-08-31T10:01:00","daily_mode":"Multiplication","answers":[{"a":8,"b":7,"first_correct":False}]},
    {"nickname":"Charlie","correct_count":10,"timed_seconds":42.0,"completed_at":"2026-08-31T10:02:00","daily_mode":"Multiplication","answers":[]},
]
ranked=rank_daily(rows)
check("history Top 10 ranks accuracy then time", [r["nickname"] for r in ranked] == ["Charlie","Bravo","Alpha"])
misses=common_multiplication_misses(rows)
check("history canonicalizes commutative misses", misses[0]["Fact"] == "7 × 8" and misses[0]["Misses"] == 2)
check("history names students on common miss", "Alpha" in misses[0]["Students"] and "Bravo" in misses[0]["Students"])

created=datetime(2026,8,1,tzinfo=timezone.utc)
students=[StudentRecord("s1","c1","Alpha",True,created,"1111"),StudentRecord("s2","c1","Bravo",True,created,"2222")]
class A:
    def __init__(self,sid,slot,correct): self.student_id=sid; self.question_slot=slot; self.correct=correct
summary=warmup_summary(students,[A("s1",1,True),A("s1",2,False),A("s2",1,False),A("s2",2,True)])
check("warmup history counts completed students", summary["completed"] == 2)
check("warmup history preserves slot accuracy", summary["slots"][1]["correct"] == 1 and summary["slots"][2]["correct"] == 1)

# Four-class weekly scheduling scale: 20 cells remain independent.
scale=FakeSettingsStore(); roster=[C(f"b{i}",f"Block {i}") for i in range(1,5)]
modes=["Multiplication","Addition Facts","Subtraction Facts","Division Facts","Integers"]
for ci,c in enumerate(roster):
    for offset,mode in enumerate(modes):
        if (ci+offset)%2:
            scale.set_app_setting(daily_mode_setting_key(source+__import__('datetime').timedelta(days=offset),c.class_id),mode)
copy_daily_week(scale,roster,source,target)
scale_ok=True
for ci,c in enumerate(roster):
    for offset in range(5):
        scale_ok = scale_ok and configured_daily_mode(scale,c.class_id,target+__import__('datetime').timedelta(days=offset)) == configured_daily_mode(scale,c.class_id,source+__import__('datetime').timedelta(days=offset))
check("4x5 weekly scheduler simulation passes", scale_ok)

# Protect student-facing and Phase 2 intelligence surfaces byte-for-byte from v2.16.0.
protected = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "daily_alt_component/index.html": "332ee7265c450b00d4848a059f000439dba2089c4ec765bf18f41e2bed734c4d",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "persistent_login_component/index.html": "fae94c44f25512d2c017b24e17e3be2d987f21604072ed4c061fbae1cc9f9585",
    "pin_entry_component/index.html": "18a89b45481f83f33fd93746bdf854ba0e4b216c0c1f0904e035f871d5d8c2b7",
    "student_igniter_ui.py": "043f3905b3e37a926cbae66d40de5e9ff963b2af3676f6bc4678336ca08e39ed",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "daily_modes.py": "f37b151fc44514f761f66f616434d26764df9719b0ab64d1865c9ee0d1881561",
    "warmup.py": "e9dc2faabf9234c4463f84fc02c3453b4a1f5e37376cd8461d1adccc34bb816b",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
}
for relative, expected in protected.items():
    actual=hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
    check(f"protected v2.15 surface unchanged: {relative}", actual == expected)

print(f"v2.16.0 Planning & History regression: {len(checks)}/{len(checks)} checks passed")
