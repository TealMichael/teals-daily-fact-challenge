from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = (ROOT / "interactive_math_questions.py").read_text(encoding="utf-8")
engine = (ROOT / "fact_engine.py").read_text(encoding="utf-8")
checks = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


check("release version", 'APP_VERSION = "2.24.4"' in engine)
check("native desktop drag", 'tile.draggable = true' in source and 'ondragstart' in source and 'ondragover' in source and 'ondragend' in source)
check("touch pointer drag", 'onpointerdown' in source and 'onpointermove' in source and 'onpointerup' in source)
check("mouse uses native path", 'if (event.pointerType === "mouse") return;' in source)
check("hit-test positioning", 'elementFromPoint' in source and 'reorderAtPoint' in source)
check("old row midpoint trap removed", 'if (clientY < rowMid ||' not in source)
check("visible move fallback", 'tdfc-order-left' in source and 'tdfc-order-right' in source and 'Move ← / →' in source)
check("selection fallback", 'is-selected' in source and 'selectTile' in source)
check("order persists", 'setStateValue("order", currentOrder())' in source)
check("keyboard remains", 'event.key === "ArrowLeft"' in source and 'event.key === "ArrowRight"' in source)
check("touch action preserved", 'touch-action: none' in source)
check("no identity data", 'student_id' not in source and 'student_name' not in source)

for filename in ("student_igniter_ui.py", "student_weekly_quiz_ui.py", "student_recovery_ui.py"):
    ui = (ROOT / filename).read_text(encoding="utf-8")
    check(f"{filename} uses shared Order Tiles widget", "render_order_tiles(" in ui)

print(f"v2_24_3_order_tiles_drag_hotfix_tests: PASS ({len(checks)}/{len(checks)})")
