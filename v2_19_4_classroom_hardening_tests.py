from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import hashlib
import httpx
import re

from fact_engine import APP_VERSION, CHALLENGE_VERSION
from daily_modes import configured_daily_mode, questions_for_mode
from alternate_followup import ALT_MODES, skill_identity_for_question
from alternate_focus import focus_candidate_pool
from alternate_teaching import teaching_plan_for_question
from supabase_fact_store import SupabaseFactStore

ROOT = Path(__file__).resolve().parent
CHECKS = 0

def check(label: str, condition: bool) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1

check("v2.19.5 version", APP_VERSION == "2.19.9")
check("multiplication challenge version frozen", CHALLENGE_VERSION == "TDFC-DAILY-v1")

# Student-mode reads must never silently fall back to Multiplication after a DB failure.
class SettingStore:
    def __init__(self, value=None, exc=None): self.value, self.exc = value, exc
    def get_app_setting(self, key):
        if self.exc: raise self.exc
        return self.value

check("missing setting keeps multiplication default", configured_daily_mode(SettingStore(None), "c", date(2026,9,4)) == "Multiplication")
check("teacher fallback remains safe", configured_daily_mode(SettingStore(exc=RuntimeError("offline")), "c", date(2026,9,4)) == "Multiplication")
try:
    configured_daily_mode(SettingStore(exc=RuntimeError("offline")), "c", date(2026,9,4), strict=True)
except RuntimeError:
    CHECKS += 1
else:
    raise AssertionError("strict student mode lookup must propagate failure")

APP = (ROOT / "app.py").read_text(encoding="utf-8")
check("student Daily uses strict configured-mode read", "configured_daily_mode(store, st.session_state.student_class_id, day, strict=True)" in APP)
check("student login has transient-service message", "The app could not check your sign-in just now. Try again." in APP)

UI = (ROOT / "student_alt_daily_ui.py").read_text(encoding="utf-8")
check("alternate Daily cache-busted", '"tdfc_alt_daily_v2195"' in UI)
check("alternate Fix cache-busted", '"tdfc_alt_fix_v2197"' in UI)
check("alternate Focus cache-busted", '"tdfc_alt_focus_v2197"' in UI)

# The alternate Daily keypad must keep its buttons mounted between rapid digit taps.
DAILY_HTML = (ROOT / "daily_alt_component" / "index.html").read_text(encoding="utf-8")
check("alternate Daily has stable entry updater", "function updateEntry" in DAILY_HTML)
for name, next_name in (("addDigit", "toggleMinus"), ("toggleMinus", "erase"), ("erase", "submit")):
    start_marker = f"function {name}"
    end_marker = f"function {next_name}"
    check(f"{name} exists", start_marker in DAILY_HTML and end_marker in DAILY_HTML)
    body = DAILY_HTML.split(start_marker, 1)[1].split(end_marker, 1)[0]
    check(f"{name} updates display locally", "updateEntry()" in body)
    check(f"{name} does not rebuild keypad", "render()" not in body)

# Every question that can appear in an alternate Daily must be eligible for Focus.
start = date(2026,1,1)
for mode in ALT_MODES:
    pool_keys = {q["item_key"] for q in focus_candidate_pool(mode)}
    missing = []
    for offset in range(365):
        day = start + timedelta(days=offset)
        for q in questions_for_mode(day, mode):
            key = skill_identity_for_question(q).item_key
            if key not in pool_keys:
                missing.append((day.isoformat(), q["prompt"], key))
    check(f"{mode} has complete Focus coverage for 2026", not missing)

mixed_pool = {q["item_key"] for q in focus_candidate_pool("Mixed")}
check("Mixed Focus includes x11", "mul:9x11" in mixed_pool)
check("Mixed Focus includes x12", "mul:9x12" in mixed_pool)
int_pool = {q["item_key"] for q in focus_candidate_pool("Integers")}
check("Integer Focus includes 0 + 0", "int:0+0" in int_pool)
check("Integer Focus includes 0 - 0", "int:0-0" in int_pool)

add_zero = teaching_plan_for_question({"prompt":"5 + 0","correct_answer":5,"category":"Integers"})
sub_zero = teaching_plan_for_question({"prompt":"5 − 0","correct_answer":5,"category":"Integers"})
check("integer add-zero model says stay put", add_zero.title == "Add zero: stay put" and "does not change" in add_zero.relationship)
check("integer subtract-zero model says stay put", sub_zero.title == "Subtract zero: stay put" and "does not change" in sub_zero.relationship)
sub00 = teaching_plan_for_question({"prompt":"0 − 0","correct_answer":0,"category":"Subtraction Facts"})
check("0 minus 0 model is mathematically correct", sub00.final_equation == "0 − 0 = 0" and int(sub00.visual["total"]) == 0)

for comp in ("alt_fix_component", "alt_focus_component"):
    html = (ROOT / comp / "index.html").read_text(encoding="utf-8")
    check(f"{comp} no fake Whole=1 zero coercion", "Math.max(1,Number(v.total))" not in html)
    check(f"{comp} supports zero part-whole width", "total===0?50" in html.replace(" ", ""))
    check(f"{comp} waits for WATCH IT like multiplication", "state.phase==='coach'&&!Number(state.coachStartedAt||0)" not in html.replace(' ',''))

# Supabase list reads must construct a new query object on retry.
class Resp:
    def __init__(self, data): self.data = data

class Builder:
    def __init__(self, owner, should_fail): self.owner, self.should_fail = owner, should_fail
    def select(self, *args, **kwargs): return self
    def eq(self, *args, **kwargs): return self
    def order(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    def execute(self):
        if self.should_fail:
            raise httpx.ReadError("temporary read failure")
        return Resp([{
            "student_id":"s1","class_id":"c1","nickname":"A","pin_code":"0000",
            "active":True,"created_at":"2026-09-04T12:00:00+00:00","is_test":False,
        }])

class Client:
    def __init__(self): self.calls = 0
    def table(self, name):
        self.calls += 1
        return Builder(self, self.calls == 1)

client = Client()
store = SupabaseFactStore("https://example.supabase.co", "fake-key", client=client)
students = store.list_students("c1")
check("list_students retries with fresh query", len(students) == 1 and client.calls >= 2)

client2 = Client()
store2 = SupabaseFactStore("https://example.supabase.co", "fake-key", client=client2)
student = store2.get_test_student()
check("get_test_student retries with fresh query", student is not None and client2.calls >= 2)

# Gold-standard multiplication surfaces remain exact v2.19.5 bytes.
EXPECTED = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
}
for rel, expected in EXPECTED.items():
    actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    check(f"protected multiplication surface unchanged: {rel}", actual == expected)

print(f"PASS: {CHECKS}/{CHECKS} v2.19.5 classroom-hardening checks")
