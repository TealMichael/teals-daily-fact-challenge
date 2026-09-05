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
check('v2.19.5 version', APP_VERSION=='2.19.6')
check('Fix component identity cache-busted', 'tdfc_alt_fix_v2196' in UI and '"tdfc_alt_fix"' not in UI)
check('Focus component identity cache-busted', 'tdfc_alt_focus_v2196' in UI and '"tdfc_alt_focus"' not in UI)
for label, src in [('Fix',FIX),('Focus',FOCUS)]:
    check(f'{label} multiplication-style Watch click', "watch.addEventListener('click',startSequence)" in src)
    check(f'{label} multiplication-style Replay click', "replay.addEventListener('click',startSequence)" in src)
    check(f'{label} no pointer/touch double-binding drift', "addEventListener('pointerup'" not in src and "addEventListener('touchend'" not in src)
    check(f'{label} Watch and Replay truly restart', 'state.coachStartedAt=Date.now();save();resumeSequence()' in src)
    check(f'{label} sequence resume survives rerender', 'resumeSequence()' in src and 'coachStartedAt' in src)
print(f'v2.19.5 Component Cache/Touch Hotfix: PASS ({len(checks)}/{len(checks)} checks)')
