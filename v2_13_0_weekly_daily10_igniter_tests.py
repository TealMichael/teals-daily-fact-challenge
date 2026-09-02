from __future__ import annotations

from datetime import date
from pathlib import Path
import hashlib

from daily_modes import DAILY_MODES, configured_daily_mode, daily_mode_setting_key, questions_for_mode
from fact_engine import APP_VERSION, CHALLENGE_VERSION, daily_facts_for_date
from fact_store import InMemoryFactStore
from warmup import (
    QUESTION_TYPES, expanded_form_matches, grade_question, pack_multi_part_response,
    prepare_question,
)

checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)

DAY = date(2026, 8, 26)
check("v2.13 version", APP_VERSION == "2.18.0")
check("multiplication challenge version untouched", CHALLENGE_VERSION == "TDFC-DAILY-v1")
expected = [(6,10,'medium'),(4,4,'easy'),(11,3,'extension'),(5,10,'easy'),(3,7,'hard'),(8,7,'hard'),(9,3,'medium'),(8,5,'medium'),(5,4,'easy'),(6,5,'medium')]
check("known multiplication daily unchanged", [(f.a,f.b,f.tier) for f in daily_facts_for_date(DAY)] == expected)
check("six teacher modes", tuple(DAILY_MODES) == ("Multiplication","Addition Facts","Subtraction Facts","Division Facts","Integers","Mixed"))

# Freeze the proven Hotfix 3 surfaces that v2.13 is not allowed to redesign.
PROTECTED_HASHES = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "answer_pad_component/index.html": "81dd828f95dcde11f20ae414bae1e16da3c9534d20400e1c3986989fdb7fe5cd",
    "persistent_login.py": "bace7a3ae337c5cb651afe16face0262ebae482d56e1b435de1e997293a289f2",
    "persistent_login_component/index.html": "fae94c44f25512d2c017b24e17e3be2d987f21604072ed4c061fbae1cc9f9585",
    "pin_entry_component/index.html": "18a89b45481f83f33fd93746bdf854ba0e4b216c0c1f0904e035f871d5d8c2b7",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
    "AWTRIX_FactTop10.berry": "4ab1b8a25e84535591a2ff7905366aa89f18c83b41c2b56d22f2d68a49edc3e2",
    "requirements.txt": "3436997a9043e9843f0960bac0ade5a33acb72eba52a3070bd98a49b3fed7180",
    "teacher_insights.py": "4fdf3516e75a8d697747f4d92aadd3f39c51a116e5990054c5eca4c66b0094a5",
}
for protected_path, expected_hash in PROTECTED_HASHES.items():
    actual = hashlib.sha256(Path(protected_path).read_bytes()).hexdigest()
    check(f"protected Hotfix 3 hash: {protected_path}", actual == expected_hash)

migration = Path("RUN_THIS_ONCE_IN_SUPABASE_v2_13.sql").read_text(encoding="utf-8")
check("v2.13 migration defaults old attempts to multiplication", "daily_mode text not null default 'Multiplication'" in migration)
check("v2.13 migration stores custom questions", "custom_questions jsonb" in migration)
check("v2.13 migration stores custom answers", "custom_answers jsonb" in migration)
check("v2.13 migration expands Igniter answer types", all(name in migration for name in QUESTION_TYPES))

addition = questions_for_mode(DAY, "Addition Facts")
check("addition has ten", len(addition) == 10)
check("addition single-digit addends", all(all(0 <= int(x) <= 9 for x in q["prompt"].split(" + ")) for q in addition))
subtraction = questions_for_mode(DAY, "Subtraction Facts")
check("subtraction has ten", len(subtraction) == 10)
check("subtraction stays basic through 18", all(int(q["prompt"].split(" − ")[0]) <= 18 and int(q["correct_answer"]) >= 0 for q in subtraction))
division = questions_for_mode(DAY, "Division Facts")
check("division has ten", len(division) == 10)
check("division exact no remainder", all(int(q["prompt"].split(" ÷ ")[0]) % int(q["prompt"].split(" ÷ ")[1]) == 0 for q in division))
integers = questions_for_mode(DAY, "Integers")
check("integers has ten", len(integers) == 10)
check("integer display wraps negative second operand", all("+ -" not in q["prompt"] and "− -" not in q["prompt"] for q in integers))
mixed = questions_for_mode(DAY, "Mixed")
check("mixed has ten", len(mixed) == 10)
counts = {name: sum(q["category"] == name for q in mixed) for name in ("Multiplication","Addition Facts","Subtraction Facts","Division Facts","Integers")}
check("mixed exactly two of each", set(counts.values()) == {2})
check("alternate generation deterministic", questions_for_mode(DAY, "Mixed") == mixed)

store = InMemoryFactStore()
classes = [store.create_class(f"Block {i}") for i in range(1,5)]
check("block 4 supported", len(store.list_classes()) == 4)
store.set_app_setting(daily_mode_setting_key(DAY, classes[3].class_id), "Integers")
check("class/date mode setting independent", configured_daily_mode(store, classes[3].class_id, DAY) == "Integers" and configured_daily_mode(store, classes[0].class_id, DAY) == "Multiplication")
challenge = store.get_or_create_challenge(DAY, CHALLENGE_VERSION, daily_facts_for_date(DAY))

modes = ["Multiplication", "Addition Facts", "Mixed", "Integers"]
first_students = []
for class_index, klass in enumerate(classes):
    mode = modes[class_index]
    questions = None if mode == "Multiplication" else questions_for_mode(DAY, mode)
    for student_index in range(30):
        student = store.create_student(klass.class_id, f"B{class_index+1} Student {student_index+1}", f"{1000 + class_index*100 + student_index:04d}"[-4:])
        if student_index == 0:
            first_students.append(student)
        attempt = store.get_or_create_attempt(student.student_id, challenge.challenge_id, daily_mode=mode, custom_questions=questions)
        if mode == "Multiplication":
            facts = list(challenge.facts)
            values = [fact.product for fact in facts]
            if student_index % 7 == 0:
                values[-1] += 1
            store.complete_full_attempt(attempt.attempt_id, list(zip(facts, values)), 12 + student_index / 10)
        else:
            values = [int(q["correct_answer"]) for q in questions]
            if student_index % 7 == 0:
                values[-1] += 1
            store.complete_custom_attempt(attempt.attempt_id, values, 12 + student_index / 10)

check("four-class simulation roster", all(len(store.list_students(c.class_id)) == 30 for c in classes))
check("all classes maintain top ten", all(len(store.leaderboard(c.class_id, challenge.challenge_id)) == 10 for c in classes))
check("multiplication writes mastery", sum(row.evidence_count for row in store.get_mastery(first_students[0].student_id)) > 0)
check("addition writes zero multiplication mastery", sum(row.evidence_count for row in store.get_mastery(first_students[1].student_id)) == 0)
check("mixed writes zero multiplication mastery", sum(row.evidence_count for row in store.get_mastery(first_students[2].student_id)) == 0)
check("integers write zero multiplication mastery", sum(row.evidence_count for row in store.get_mastery(first_students[3].student_id)) == 0)
locked = store.get_or_create_attempt(first_students[1].student_id, challenge.challenge_id, daily_mode="Integers", custom_questions=questions_for_mode(DAY, "Integers"))
check("started attempt mode remains locked", locked.daily_mode == "Addition Facts")

check("five igniter answer types", tuple(QUESTION_TYPES) == ("Short answer","Multiple choice","Expanded Form","Equivalent Number","Multi-Part — 2 answers"))
check("expanded form accepts full structure", expanded_form_matches("60,000 + 3,000 + 400 + 5", "63,405"))
check("expanded form accepts compact spacing", expanded_form_matches("60000+3000+400+5", "63,405"))
check("expanded form rejects standard form", not expanded_form_matches("63,405", "63,405"))
check("expanded form rejects partial expansion", not expanded_form_matches("60,000 + 3,405", "63,405"))
q = prepare_question(slot=1, prompt="Give two equivalents", question_type="Multi-Part — 2 answers", correct_answer="1/2", correct_answer_two="0.25", standard_code="5.NS.1")
check("multi-part requires and grades two answers", grade_question(q, "0.5", "1/4"))
check("equivalent-number numeric matching", grade_question(prepare_question(slot=1,prompt="Equivalent",question_type="Equivalent Number",correct_answer="1/2",standard_code="5.NS.1"), "0.50"))

# Raw-response retention: yesterday's text clears when today's first response is stored.
ret = InMemoryFactStore(); klass = ret.create_class("Retention"); student = ret.create_student(klass.class_id, "Learner", "2468")
yesterday = date(2026,8,25); today = DAY
w1 = ret.save_warmup_set(klass.class_id, yesterday,
    prepare_question(slot=1,prompt="Old Q1",question_type="Short answer",correct_answer="1",standard_code="5.NS.1"),
    prepare_question(slot=2,prompt="Old Q2",question_type="Short answer",correct_answer="2",standard_code="5.NS.1"))
ret.record_warmup_answer(warmup_set_id=w1.warmup_set_id,student_id=student.student_id,class_id=klass.class_id,warmup_date=yesterday,question_slot=1,question_type="Short answer",prompt="Old Q1",standard_code="5.NS.1",standard_description="",student_answer="private old text",correct_answer="1",correct=False)
w2 = ret.save_warmup_set(klass.class_id, today,
    prepare_question(slot=1,prompt="New Q1",question_type="Short answer",correct_answer="3",standard_code="5.NS.1"),
    prepare_question(slot=2,prompt="New Q2",question_type="Short answer",correct_answer="4",standard_code="5.NS.1"))
ret.record_warmup_answer(warmup_set_id=w2.warmup_set_id,student_id=student.student_id,class_id=klass.class_id,warmup_date=today,question_slot=1,question_type="Short answer",prompt="New Q1",standard_code="5.NS.1",standard_description="",student_answer="3",correct_answer="3",correct=True)
old = ret.list_warmup_answers(yesterday,yesterday,class_id=klass.class_id)[0]
check("old raw response text clears", old.student_answer == "")
check("old correctness evidence remains", old.correct is False and old.standard_code == "5.NS.1")

assert len(checks) == 49, len(checks)
print(f"v2.13 weekly feature regression: {len(checks)}/{len(checks)} checks passed")
