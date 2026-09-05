from pathlib import Path
from fact_engine import APP_VERSION
ROOT=Path(__file__).resolve().parent
UI=(ROOT/'student_alt_daily_ui.py').read_text()
FIX=(ROOT/'alt_fix_component'/'index.html').read_text()
FOCUS=(ROOT/'alt_focus_component'/'index.html').read_text()
checks=[]
def check(name, cond):
    assert cond, name
    checks.append(name)
check('current version', APP_VERSION=='2.19.7')
check('Fix component identity cache-busted', 'tdfc_alt_fix_v2197' in UI and '"tdfc_alt_fix"' not in UI)
check('Focus component identity cache-busted', 'tdfc_alt_focus_v2197' in UI and '"tdfc_alt_focus"' not in UI)
for label, src in [('Fix',FIX),('Focus',FOCUS)]:
    check(f'{label} multiplication-style Watch click', "watch.addEventListener('click',startTeachSequence)" in src)
    check(f'{label} multiplication-style Replay click', "replay.addEventListener('click',startTeachSequence)" in src)
    check(f'{label} no pointer/touch double-binding drift', "addEventListener('pointerup'" not in src and "addEventListener('touchend'" not in src)
    check(f'{label} Watch and Replay share one controller', "function startTeachSequence()" in src)
    check(f'{label} routine parent rerender preserves live DOM', "else{args=newArgs;setHeight()}" in src.replace(' ',''))
print(f'Component Cache/Touch Regression: PASS ({len(checks)}/{len(checks)} checks)')
