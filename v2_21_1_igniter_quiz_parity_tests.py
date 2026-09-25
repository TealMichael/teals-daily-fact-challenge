from __future__ import annotations

from pathlib import Path
import hashlib

from fact_engine import APP_VERSION
from warmup import (
    QUESTION_TYPES,
    correct_answer_for_storage,
    display_student_response,
    grade_question,
    prepare_question,
)
from weekly_quiz import grade_quiz_response, prepare_quiz_question

ROOT = Path(__file__).resolve().parent
checks = []

def check(name, condition):
    assert condition, name
    checks.append(name)

check("current version", APP_VERSION == "2.21.3")

# Teacher editor must be live just like Friday Quiz; no form may trap answer-type
# changes until Save is clicked.
warmup_ui = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
quiz_ui = (ROOT / "teacher_weekly_quiz_ui.py").read_text(encoding="utf-8")
shared_editor = (ROOT / "teacher_question_editor.py").read_text(encoding="utf-8")
check("Igniter builder no longer wraps question editor in a form", 'with st.form(f"{key_prefix}_form")' not in warmup_ui)
check("Igniter save is a normal button", 'st.button("Save Warm-Up"' in warmup_ui)
check("Friday Quiz builder remains live", 'st.button("Save Quiz of the Week"' in quiz_ui)
check("Both builders use shared answer editor", "render_answer_editor(" in warmup_ui and "render_answer_editor(" in quiz_ui)
check("Multi-Part Part 2 teacher field exists", '"Correct answer — Part 2"' in shared_editor)
check("Number + Label teacher fields exist", '"Label / unit choices — one per line"' in shared_editor and '"Correct label / unit"' in shared_editor)

# Common answer types are explicitly available in both systems.
for qtype in ("Number", "Fraction", "Multiple choice", "Number + Label"):
    check(f"Igniter supports shared type {qtype}", qtype in QUESTION_TYPES)

# Number grading parity, including decimal equivalence.
w_num = prepare_question(slot=1, prompt="Enter 3", question_type="Number", correct_answer="3", standard_code="5.NS.1")
q_num = prepare_quiz_question(slot=1, prompt="Enter 3", question_type="Number", correct_answer="3")
for answer in ("3", "3.0", "3.00"):
    check(f"Number parity {answer}", grade_question(w_num, answer) == grade_quiz_response(q_num, answer)["correct"] is True)

# Fraction grading parity includes equivalent fractions, decimals, and mixed numbers.
w_frac = prepare_question(slot=1, prompt="Enter 2 1/3", question_type="Fraction", correct_answer="2 1/3", standard_code="5.NS.1")
q_frac = prepare_quiz_question(slot=1, prompt="Enter 2 1/3", question_type="Fraction", correct_answer="2 1/3")
for answer in ("2 1/3", "7/3"):
    check(f"Fraction mixed-number parity {answer}", grade_question(w_frac, answer) == grade_quiz_response(q_frac, answer)["correct"] is True)
w_frac2 = prepare_question(slot=1, prompt="Enter 3/4", question_type="Fraction", correct_answer="3/4", standard_code="5.NS.1")
q_frac2 = prepare_quiz_question(slot=1, prompt="Enter 3/4", question_type="Fraction", correct_answer="3/4")
for answer in ("3/4", "6/8", "0.75"):
    check(f"Fraction parity {answer}", grade_question(w_frac2, answer) == grade_quiz_response(q_frac2, answer)["correct"] is True)

# Multiple choice parity and no student-side default answer.
w_mc = prepare_question(slot=1, prompt="Choose 12", question_type="Multiple choice", correct_answer="12", options=["8", "10", "12", "14"], standard_code="5.CA.1")
q_mc = prepare_quiz_question(slot=1, prompt="Choose 12", question_type="Multiple choice", correct_answer="12", options=["8", "10", "12", "14"])
for answer, expected in (("12", True), ("10", False)):
    check(f"Multiple choice parity {answer}", grade_question(w_mc, answer) == grade_quiz_response(q_mc, answer)["correct"] is expected)
student_warmup = (ROOT / "student_igniter_ui.py").read_text(encoding="utf-8")
student_quiz = (ROOT / "student_weekly_quiz_ui.py").read_text(encoding="utf-8")
check("Igniter multiple choice has no default selection", '"Choose your answer", options, index=None' in student_warmup)
check("Quiz multiple choice has no default selection", '"Choose your answer", options, index=None' in student_quiz)

# Number + Label now behaves the same in both systems.
w_label = prepare_question(
    slot=1, prompt="Area", question_type="Number + Label", correct_answer="16",
    label_options=["feet", "square feet"], correct_label="square feet", standard_code="5.M.2",
)
q_label = prepare_quiz_question(
    slot=1, prompt="Area", question_type="Number + Label", correct_answer="16",
    label_options=["feet", "square feet"], correct_label="square feet",
)
check("Number + Label parity correct", grade_question(w_label, "16.0", "square feet") == grade_quiz_response(q_label, "16.0", "square feet")["correct"] is True)
check("Number + Label parity wrong label", grade_question(w_label, "16", "feet") == grade_quiz_response(q_label, "16", "feet")["correct"] is False)
check("Number + Label persisted labels", w_label["label_options"] == ["feet", "square feet"] and w_label["correct_label"] == "square feet")
check("Number + Label storage display", display_student_response(correct_answer_for_storage(w_label), "Number + Label") == "Number: 16 · Label: square feet")
check("Igniter student Number + Label UI", 'elif qtype == "Number + Label":' in student_warmup and '"Label / unit"' in student_warmup)

# Existing generic Multi-Part remains supported and now updates live in the teacher editor.
w_multi = prepare_question(
    slot=2, prompt="Give both", question_type="Multi-Part — 2 answers",
    correct_answer="1/2", correct_answer_two="0.25", standard_code="5.NS.1",
)
check("Legacy Multi-Part still grades both pieces", grade_question(w_multi, "0.5", "1/4"))
check("Legacy Multi-Part still rejects missing/wrong Part 2", not grade_question(w_multi, "0.5", "1/3"))
check("Multi-Part editor is live in shared component", 'if qtype == "Multi-Part — 2 answers":' in shared_editor)

# Curriculum-specific Igniter types are retained.
for qtype in ("Short answer", "Expanded Form", "Equivalent Number", "Multi-Part — 2 answers"):
    check(f"Igniter-specific type retained {qtype}", qtype in QUESTION_TYPES)

# Exercise the shared teacher editor with a tiny Streamlit fake. This proves the
# conditional fields are selected from the answer-type value immediately rather
# than waiting for a form submit/rerun cycle.
import importlib.util
import sys
import types

class _FakeStreamlit(types.ModuleType):
    def __init__(self, selected_type: str):
        super().__init__("streamlit")
        self.selected_type = selected_type
        self.labels = []
    def selectbox(self, label, options, **kwargs):
        self.labels.append(label)
        return self.selected_type
    def text_input(self, label, **kwargs):
        self.labels.append(label)
        return str(kwargs.get("value") or "")
    def text_area(self, label, **kwargs):
        self.labels.append(label)
        return str(kwargs.get("value") or "")
    def caption(self, *args, **kwargs):
        pass

def _run_editor(selected_type: str):
    fake = _FakeStreamlit(selected_type)
    old = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake
    try:
        spec = importlib.util.spec_from_file_location("_teacher_question_editor_test", ROOT / "teacher_question_editor.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.render_answer_editor(
            {}, slot=1, prefix="qa", question_types=QUESTION_TYPES, default_type="Short answer"
        )
        return result, fake.labels
    finally:
        if old is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = old

multi_result, multi_labels = _run_editor("Multi-Part — 2 answers")
check("live Multi-Part editor reveals Part 2", "Correct answer — Part 2" in multi_labels and multi_result["question_type"] == "Multi-Part — 2 answers")
label_result, label_labels = _run_editor("Number + Label")
check("live Number + Label editor reveals label controls", "Label / unit choices — one per line" in label_labels and "Correct label / unit" in label_labels and label_result["question_type"] == "Number + Label")

# Protected student Daily/teaching surfaces are not part of this change.
expected_hashes = {
    "daily_sprint_component/index.html": "dc8a59e1dbab86b3dd23f3eec37a4054fdc4fa9e117ffdb8b35395a4c9dcabad",
    "daily_alt_component/index.html": "332ee7265c450b00d4848a059f000439dba2089c4ec765bf18f41e2bed734c4d",
    "guided_practice_component/index.html": "f073b8fa704a7f52ebb45a046082d30bbad8892b8340fa2b933132bbf7c835cd",
    "alt_fix_component/index.html": "6a60d52ce0775250b54477c2cafb909f3cf5e4cb6fe53d51795ca30aacda64d4",
    "alt_focus_component/index.html": "3fbc588093066e786dd4e579f9a4f0659d5480c5108f632a63f109ffd3460a86",
    "fact_coach.py": "dcbaf3aa62774a4627724d6de65fab31fb87254a25e601c16201980f806af9fb",
    "adaptive_engine.py": "b828414cd7207a04c10feb71a797ee8650d09fba81017a503a4eacf274a1e6e9",
    "weekly_mystery.py": "dfe98e7ba8c9f86daa28396e9a61282bd2705f5f132c84ff7cbb5051b4740b1f",
}
for relative, expected in expected_hashes.items():
    check(f"protected hash {relative}", hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected)

print(f"v2_21_1_igniter_quiz_parity_tests: PASS ({len(checks)}/{len(checks)})")

if __name__ == "__main__":
    pass
