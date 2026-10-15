from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = (ROOT / "interactive_math_questions.py").read_text(encoding="utf-8")
engine = (ROOT / "fact_engine.py").read_text(encoding="utf-8")
checks = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


check("release version", 'APP_VERSION = "2.24.5"' in engine)
check("tile handlers rebound", 'tiles().forEach((tile) =>' in source and 'wireTile(tile);' in source)
check("property mouse handlers", 'tile.ondragstart =' in source and 'tile.ondragend =' in source)
check("property pointer handlers", 'tile.onpointerdown =' in source and 'tile.onpointermove =' in source and 'tile.onpointerup =' in source)
check("property click handler", 'tile.onclick =' in source)
check("property keyboard handler", 'tile.onkeydown =' in source)
check("no stale tile listeners", 'tile.addEventListener(' not in source)
check("list current-render handlers", 'list.ondragover =' in source and 'list.ondrop =' in source)
check("selection restored", 'selectedTile = list.querySelector(".tdfc-order-tile.is-selected")' in source)
check("order persists", 'setStateValue("order", currentOrder())' in source)
check("visible fallback remains", 'tdfc-order-left' in source and 'tdfc-order-right' in source)
check("touch path remains", 'if (event.pointerType === "mouse") return;' in source)
check("keyboard remains", 'event.key === "ArrowLeft"' in source and 'event.key === "ArrowRight"' in source)
check("no identity data", 'student_id' not in source and 'student_name' not in source)

for filename in ("student_igniter_ui.py", "student_weekly_quiz_ui.py", "student_recovery_ui.py"):
    ui = (ROOT / filename).read_text(encoding="utf-8")
    check(f"{filename} uses shared Order Tiles widget", "render_order_tiles(" in ui)

print(f"v2_24_4_order_tiles_rerender_hotfix_tests: PASS ({len(checks)}/{len(checks)})")
