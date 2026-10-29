"""Offline v2.29.2 presentation checks. No classroom data or network required.

Run from UPLOAD_TO_GITHUB: python3 -B v2_29_2_presentation_fit_tests.py
"""

import ast
import html
from pathlib import Path
import re


HERE = Path(__file__).parent
source = (HERE / "igniter_presentation.py").read_text(encoding="utf-8")
parsed = ast.parse(source)
names = {"math_text", "_unlettered_option", "_presentation_prompt", "question_html"}
nodes = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
namespace = {"html": html, "re": re}
exec(compile(ast.Module(body=nodes, type_ignores=[]), "igniter_presentation.py", "exec"), namespace)
question_html = namespace["question_html"]


def test_duplicated_multiple_choice_list_is_only_displayed_once():
    q = {
        "question_type": "Multiple choice",
        "prompt": "Which expression is equivalent to 4(x + 3)?\nA. 4x + 3\nB. 4x + 12\nC. x + 12\nD. 7x",
        "options": ["A. 4x + 3", "B. 4x + 12", "C. x + 12", "D. 7x"],
    }
    rendered = question_html(q)
    assert "Which expression is equivalent to 4(x + 3)?" in rendered
    assert rendered.count("4x + 12") == 1
    assert rendered.count("4x + 3") == 1
    assert '<li>4x + 3</li><li>4x + 12</li>' in rendered
    assert "A. A." not in rendered and "B. B." not in rendered
    assert q["prompt"].endswith("D. 7x")  # Presentation never edits published data.


def test_preformatted_and_plain_options_both_get_one_label():
    prefixed = {"question_type": "Multiple choice", "prompt": "Pick one.",
                "options": ["A. A. 15", "B) 20", "C. 25", "D. 30"]}
    rendered = question_html(prefixed)
    assert '<li>15</li><li>20</li><li>25</li><li>30</li>' in rendered


def test_mismatched_or_non_choice_prompt_is_preserved():
    q = {"question_type": "Multiple choice", "prompt": "Compare answers.\nA. 3\nB. 4",
         "options": ["A. 5", "B. 6"]}
    rendered = question_html(q)
    assert "A. 3<br>B. 4" in rendered  # Unrelated prompt content isn't stripped.
    assert '<li>5</li><li>6</li>' in rendered
    regular = {"question_type": "Number + Label", "prompt": "What is 9 × 4 × 6?",
               "label_options": ["units", "cubic units"]}
    assert "What is 9 × 4 × 6?" in question_html(regular)
    assert "Include a unit" in question_html(regular)


def test_slide_is_bounded_and_left_routine_uses_its_height():
    css = (HERE / "igniter_presentation_assets" / "presentation.css").read_text()
    js = (HERE / "igniter_presentation_assets" / "presentation.js").read_text()
    assert "height:calc(100dvh - 12px)" in css
    assert "grid-template-rows:minmax(0,1fr) minmax(0,1fr)" in css
    assert "justify-content:space-around" in css and "flex-direction:column;justify-content" in css
    assert "fitQuestionText" in js and "ResizeObserver" in js
    assert "answer.hidden = !answer.hidden; update(); requestAnimationFrame(fitQuestionText)" in js


def test_version():
    assert 'APP_VERSION = "2.29.2"' in (HERE / "fact_engine.py").read_text()


if __name__ == "__main__":
    test_duplicated_multiple_choice_list_is_only_displayed_once()
    test_preformatted_and_plain_options_both_get_one_label()
    test_mismatched_or_non_choice_prompt_is_preserved()
    test_slide_is_bounded_and_left_routine_uses_its_height()
    test_version()
    print("v2.29.2 presentation: 5 offline checks passed")
