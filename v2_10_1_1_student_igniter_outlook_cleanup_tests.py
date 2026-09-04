from pathlib import Path
from urllib.parse import quote, urlencode, urlparse, parse_qs
import ast

from fact_engine import APP_VERSION

ROOT = Path(__file__).resolve().parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
STUDENT_IGNITER = (ROOT / "student_igniter_ui.py").read_text(encoding="utf-8")
WARMUP_UI = (ROOT / "teacher_warmup_ui.py").read_text(encoding="utf-8")


def section(name: str, next_name: str | None = None, source: str = APP) -> str:
    start = source.index(f"def {name}")
    end = source.index(f"\ndef {next_name}", start) if next_name else len(source)
    return source[start:end]


def run():
    checks = {}
    checks["version 2.11.2"] = APP_VERSION == "2.19.5"

    header = section("render_header", "render_db_setup_message")
    checks["prelogin forces student landing mode"] = 'if not signed_in and mode != "Teacher":' in header
    checks["today practice nav only inside signed-in branch"] = header.index('if signed_in and mode != "Teacher":') < header.index('"Student navigation", ["Today", "Practice"]')
    checks["teacher stays available before login"] = header.count('st.button("🔒 Teacher"') >= 2

    checks["guest practice escape removed"] = "Open Practice without signing in" not in APP

    warmup = section("render_quick_warmup", source=STUDENT_IGNITER)
    checks["student calls it Igniter"] = "🧠 Igniter Question {slot}" in warmup
    checks["no student warmup heading"] = "## 🧠 Quick Warm-Up" not in warmup
    checks["no student progress bar"] = "st.progress(" not in warmup
    checks["no spiral yesterday labels shown"] = "student_label" not in warmup and "Review Question" not in warmup and "Yesterday's Question" not in warmup
    checks["igniter completion transition"] = "## 🧠 Igniter complete!" in warmup and "Start Daily 10 →" in warmup and "Both questions are finished" in warmup
    checks["markdown markers stripped"] = 're.sub(r"(?:\\*\\*|__|`)", "", raw_prompt)' in warmup

    daily = section("render_daily", "reset_practice_question")
    checks["sign in before daily title"] = daily.index("render_student_sign_in(store)") < daily.index('st.markdown("## Daily 10")')
    checks["igniter before daily title"] = daily.index("render_quick_warmup(store, day)") < daily.index('st.markdown("## Daily 10")')
    checks["old prelogin Daily Challenge title gone"] = 'st.markdown("## Daily Challenge")' not in daily

    report = section("_warmup_report_text", "_warmup_outlook_url", WARMUP_UI)
    checks["email has question one"] = "QUESTION 1 — SPIRAL REVIEW" in report and 'f"Standard: {q1.get' in report
    checks["email has question two"] = "QUESTION 2 — YESTERDAY'S LESSON" in report
    checks["email has student pull lists"] = report.count("Students to pull:") >= 2
    checks["email has priority group"] = "PRIORITY GROUP — MISSED BOTH" in report
    checks["email has unfinished check-in"] = "HAVE NOT FINISHED YET" in report and "Please check in with these students" in report
    checks["email removes analytics clutter"] = all(text not in report for text in ["Accuracy:", "Instructional response:", "standard_description", "Students needing this skill:"])

    tree = ast.parse(WARMUP_UI)
    outlook_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_warmup_outlook_url")
    ns = {"urlencode": urlencode, "quote": quote}
    exec(compile(ast.Module(body=[outlook_node], type_ignores=[]), "outlook_cleanup", "exec"), ns)
    url = ns["_warmup_outlook_url"]("me@school.org", "push@school.org", "Warm-Up Results — Block 2", "Line one\nLine two")
    parsed = parse_qs(urlparse(url).query)
    checks["outlook round trips content"] = parsed["to"] == ["me@school.org"] and parsed["cc"] == ["push@school.org"] and parsed["body"] == ["Line one\nLine two"]
    checks["outlook no plus encoding"] = "+" not in url and "%20" in url

    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        raise AssertionError("Failed: " + ", ".join(failed))
    print(f"v2.11.2 student Igniter + Outlook cleanup: {len(checks)}/{len(checks)} checks passed")


if __name__ == "__main__":
    run()
