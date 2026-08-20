from pathlib import Path
from fact_coach import coach_plan
from fact_engine import APP_VERSION

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "guided_practice_component" / "index.html").read_text()

checks = {
    "version 2.8.3": APP_VERSION == "2.11.0.1",
    "removable rows are marked": 'data-remove-row=' in HTML,
    "student remove prompt exists": 'TAP ${removeCount} ${noun} OF ${size} TO TAKE' in HTML,
    "remove-ready state exists": 'remove-ready' in HTML,
    "tapRemoveRow handler exists": 'function tapRemoveRow' in HTML,
    "tap handler is bound": "tapRemoveRow(cell.dataset.removeRow)" in HTML,
    "removed row fades after tap": 'removed-by-tap' in HTML,
    "anchor waits for removal": 'if (needsRemovalTap) return;' in HTML,
    "coach unlocks after required taps": "card.classList.add('seq-turn','sequence-complete')" in HTML,
    "one more group feedback exists": "MORE ${remaining === 1 ? `GROUP OF ${size}` : `GROUPS OF ${size}`}" in HTML,
    "interaction gives positive visual feedback": 'YOU TOOK AWAY ${removedValue}' in HTML,
    "no fetch calls added": 'fetch(' not in HTML,
    "no audio element": '<audio' not in HTML.lower(),
    "no speech synthesis": 'speechSynthesis' not in HTML,
}

p9 = coach_plan(7, 9)
p8 = coach_plan(8, 8)
checks.update({
    "7x9 uses subtraction visual": p9.visual_mode == "split_subtract",
    "7x9 removes one group": p9.second_groups == 1,
    "8x8 uses subtraction visual": p8.visual_mode == "split_subtract",
    "8x8 removes two groups": p8.second_groups == 2,
    "7x9 anchor remains 10x7": (p9.anchor_a, p9.anchor_b, p9.anchor_answer) == (10, 7, 70),
    "8x8 anchor remains 10x8": (p8.anchor_a, p8.anchor_b, p8.anchor_answer) == (10, 8, 80),
})

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise AssertionError("Failed: " + ", ".join(failed))
print(f"v2.8.3 click-to-remove Fact Coach regression: {len(checks)}/{len(checks)} checks passed")
