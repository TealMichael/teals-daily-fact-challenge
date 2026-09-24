from __future__ import annotations

from io import BytesIO
from pathlib import Path
from datetime import date

from PIL import Image

from fact_engine import APP_VERSION
from question_images import _normalize_image, RETENTION_DAYS, MAX_STORED_BYTES
from warmup import prepare_question
from weekly_quiz import prepare_quiz_question

ROOT = Path(__file__).resolve().parent
checks = []

def check(name, condition):
    assert condition, name
    checks.append(name)

check("v2.21.2 version", APP_VERSION == "2.21.2")
check("7-day retention", RETENTION_DAYS == 7)

q = prepare_quiz_question(
    slot=1, prompt="Find the volume.", question_type="Number", correct_answer="24",
    image_path="2026-09-25/quiz/q1.webp", image_alt="Prism labeled 2, 3, and 4 units",
)
check("Quiz preserves image path", q["image_path"].endswith("q1.webp"))
check("Quiz preserves alt", q["image_alt"].startswith("Prism labeled"))

w = prepare_question(
    slot=1, prompt="Find the volume.", question_type="Number", correct_answer="24",
    standard_code="5.M.3", image_path="2026-09-25/igniter/q1.webp",
    image_alt="Rectangular prism",
)
check("Igniter preserves image path", w["image_path"].endswith("q1.webp"))
check("Igniter preserves alt", w["image_alt"] == "Rectangular prism")

# Oversized dimensions are normalized to a small WEBP suitable for free-tier storage.
img = Image.new("RGB", (3000, 2200), "white")
buf = BytesIO(); img.save(buf, format="PNG")
normalized = _normalize_image(buf.getvalue())
check("Normalized image under storage cap", len(normalized) <= MAX_STORED_BYTES)
with Image.open(BytesIO(normalized)) as out:
    check("Normalized format is WEBP", out.format == "WEBP")
    check("Normalized dimensions bounded", max(out.size) <= 1800)

teacher = (ROOT / "teacher_question_editor.py").read_text(encoding="utf-8")
student_q = (ROOT / "student_weekly_quiz_ui.py").read_text(encoding="utf-8")
student_i = (ROOT / "student_igniter_ui.py").read_text(encoding="utf-8")
check("Teacher uploader exposed", "file_uploader" in teacher and "auto-deletes" in teacher)
check("Quiz student image display", "signed_question_image_url" in student_q and "st.image" in student_q)
check("Igniter student image display", "signed_question_image_url" in student_i and "st.image" in student_i)

print(f"v2_21_2_question_image_tests: PASS ({len(checks)}/{len(checks)})")
