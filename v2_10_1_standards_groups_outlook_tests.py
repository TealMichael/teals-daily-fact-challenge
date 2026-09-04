from pathlib import Path
from collections import Counter
from types import SimpleNamespace
from urllib.parse import urlencode, quote, urlparse, parse_qs
import ast

from fact_engine import APP_VERSION
from indiana_math_standards import (
    STANDARDS, BY_CODE, CUSTOM_CODE, grade_from_standard_code,
    ordered_standard_codes, display_label,
)

ROOT = Path(__file__).resolve().parent
APP_CORE = (ROOT / "app.py").read_text(encoding="utf-8")
WARMUP_UI = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")
TODAY_UI = (ROOT / "teacher_today_ui.py").read_text(encoding="utf-8")
APP = APP_CORE + "\n" + WARMUP_UI + "\n" + TODAY_UI


def run():
    checks = 0
    assert APP_VERSION == "2.19.3"; checks += 1

    # Official-grade picker coverage: content standards across Grades 4–7.
    counts = Counter(item.grade for item in STANDARDS)
    assert set(counts) == {4, 5, 6, 7} and all(counts[g] >= 20 for g in counts); checks += 1
    for code in ("4.CA.1", "5.CA.9", "6.RP.2", "7.AF.3", "7.DSP.5"):
        assert code in BY_CODE and BY_CODE[code].description; checks += 1
    assert grade_from_standard_code("4.CA.1") == 4 and grade_from_standard_code("7.DSP.5") == 7; checks += 1
    recent = ordered_standard_codes(["7.AF.3", "5.CA.9"])
    assert recent[:2] == ["7.AF.3", "5.CA.9"]; checks += 1
    assert display_label("7.AF.3", ["7.AF.3"]).startswith("★ Recently used"); checks += 1
    assert CUSTOM_CODE not in BY_CODE; checks += 1

    # Teacher planning UI uses the searchable picker, not typed planning-material codes.
    assert "Indiana Math standard · Grades 4–7" in APP; checks += 1
    assert "Type a standard code or a skill keyword to search the list" in APP; checks += 1
    assert "Paste the standard code from your planning materials" not in APP; checks += 1
    assert "warmup_recent_standards" in APP and "_remember_warmup_standards" in APP; checks += 1
    assert "Other / Custom standard" in (ROOT / "indiana_math_standards.py").read_text(); checks += 1

    # Grouping keeps incomplete work separate from incorrect work.
    assert "unfinished_ids = student_ids - completed_ids" in APP; checks += 1
    assert "q1_wrong_completed = {sid for sid in completed_ids" in APP; checks += 1
    assert "q2_wrong_completed = {sid for sid in completed_ids" in APP; checks += 1
    assert "missed_both_ids = q1_wrong_completed & q2_wrong_completed" in APP; checks += 1

    # Execute the actual pure grouping helper from app.py without importing Streamlit.
    tree = ast.parse(WARMUP_UI)
    helper_nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"_warmup_name_list", "_warmup_grouping"}]
    ns = {}
    exec(compile(ast.Module(body=helper_nodes, type_ignores=[]), "app_grouping", "exec"), ns)
    students = [SimpleNamespace(student_id="a", nickname="Alpha"), SimpleNamespace(student_id="b", nickname="Beta"), SimpleNamespace(student_id="c", nickname="Gamma")]
    rows = [
        SimpleNamespace(student_id="a", question_slot=1, correct=False),
        SimpleNamespace(student_id="a", question_slot=2, correct=False),
        SimpleNamespace(student_id="b", question_slot=1, correct=False),  # unfinished: not a reteach group yet
        SimpleNamespace(student_id="c", question_slot=1, correct=True),
        SimpleNamespace(student_id="c", question_slot=2, correct=False),
    ]
    grouping = ns["_warmup_grouping"](students, rows)
    assert grouping["missed_both"] == ["Alpha"]; checks += 1
    assert grouping["q1_support"] == ["Alpha"] and "Beta" not in grouping["q1_support"]; checks += 1
    assert grouping["q2_support"] == ["Alpha", "Gamma"]; checks += 1
    assert grouping["unfinished"] == ["Beta"]; checks += 1
    assert "These students didn't finish, so please check in with them!" in APP; checks += 1
    assert "Unfinished work stays separate from incorrect work" in APP; checks += 1
    assert "Good small-group reteach target" in APP and "whole-class clarification" in APP; checks += 1

    # Email is class-aware, teacher-reviewed, and opens Outlook rather than auto-sending.
    assert 'return f"warmup_email_secondary::{class_id}"' in APP; checks += 1
    assert '"warmup_email_primary"' in APP; checks += 1
    assert "Push-in teacher for {class_record.class_name}" in APP; checks += 1
    assert "https://outlook.office.com/mail/deeplink/compose?" in APP; checks += 1
    assert "Nothing is sent automatically" in APP; checks += 1
    assert "Open this draft in Outlook" in APP; checks += 1
    assert "sendgrid" not in APP.casefold() and "resend" not in APP.casefold(); checks += 1
    outlook_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_warmup_outlook_url")
    outlook_ns = {"urlencode": urlencode, "quote": quote}
    exec(compile(ast.Module(body=[outlook_node], type_ignores=[]), "app_outlook", "exec"), outlook_ns)
    url = outlook_ns["_warmup_outlook_url"]("me@school.org", "pushin@school.org", "Warm-Up Results", "Line 1\nLine 2")
    parsed = parse_qs(urlparse(url).query)
    assert parsed["to"] == ["me@school.org"] and parsed["cc"] == ["pushin@school.org"]; checks += 1
    assert parsed["subject"] == ["Warm-Up Results"] and parsed["body"] == ["Line 1\nLine 2"]; checks += 1
    assert "+" not in url; checks += 1

    # Immediate Today workflow plus detailed Warm-Up page both expose groups/email.
    assert "🎯 Show Warm-Up groups & email" in APP; checks += 1
    assert APP.count("_render_warmup_groups_and_email(") >= 3; checks += 1  # def + Today + Warm-Up page

    # Weekly CSV stays real-student only and gains grade context.
    assert "include_test=False" in APP; checks += 1
    assert "Prepare Test Student Outlook email" in APP; checks += 1
    assert "Test Student drafts go only to you; the push-in teacher is not included." in APP; checks += 1
    assert "[TEST STUDENT — preview only]" in APP; checks += 1
    assert '"Grade": grade_from_standard_code(row.standard_code)' in APP; checks += 1
    assert '"Date", "Class", "Nickname", "Question", "Question Type", "Grade", "Indiana Standard"' in APP; checks += 1

    print(f"v2.11.2 standards/groups/Outlook regression: PASS ({checks} checks)")


if __name__ == "__main__":
    run()
