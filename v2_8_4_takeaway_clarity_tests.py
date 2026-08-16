from pathlib import Path
from fact_engine import APP_VERSION
from fact_coach import coach_plan

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "guided_practice_component" / "index.html").read_text()

checks = {
    "version 2.8.4": APP_VERSION == "2.9.2",
    "takeaway explanation has start line": "START WITH ${anchorLine}" in HTML,
    "takeaway prompt names group size": "${removeCount} ${noun} OF ${size}" in HTML,
    "takeaway explanation names target fact": "THAT LEAVES ${item.a} × ${item.b}" in HTML,
    "subtractive anchor can preserve original orientation": "anchorDisplay(item, p)" in HTML,
    "7x9 still uses ten-minus-one": coach_plan(7, 9).strategy_id == "ten_minus_one",
    "7x9 still anchors at 70": coach_plan(7, 9).anchor_answer == 70,
    "8x8 still uses ten-minus-two": coach_plan(8, 8).strategy_id == "ten_minus_two",
    "no extra server calls": "fetch(" not in HTML,
    "still silent": "<audio" not in HTML.lower() and "speechSynthesis" not in HTML,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError("Failed: " + ", ".join(failed))
print(f"v2.8.4 take-away clarity regression: {len(checks)}/{len(checks)} checks passed")
