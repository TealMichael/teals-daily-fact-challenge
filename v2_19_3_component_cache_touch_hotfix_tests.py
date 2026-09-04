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
check('v2.19.5 version', APP_VERSION=='2.19.5')
check('Fix component identity cache-busted', 'tdfc_alt_fix_v2194' in UI and '"tdfc_alt_fix"' not in UI)
check('Focus component identity cache-busted', 'tdfc_alt_focus_v2194' in UI and '"tdfc_alt_focus"' not in UI)
for label, src in [('Fix',FIX),('Focus',FOCUS)]:
    check(f'{label} pointer activation', "addEventListener('pointerup',go" in src)
    check(f'{label} touch activation', "addEventListener('touchend',go" in src)
    check(f'{label} click activation', "addEventListener('click',go)" in src)
    check(f'{label} repeated activation does not restart', 'if(!force&&started&&elapsed<c){resumeSequence();return}' in src)
    check(f'{label} replay can force restart', "startSequence(true)" in src)
    check(f'{label} sequence resume survives rerender', 'resumeSequence()' in src and 'coachStartedAt' in src)
print(f'v2.19.5 Component Cache/Touch Hotfix: PASS ({len(checks)}/{len(checks)} checks)')
