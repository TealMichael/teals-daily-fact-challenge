from pathlib import Path
import hashlib
import inspect
from types import SimpleNamespace, ModuleType
import sys

from fact_engine import APP_VERSION, CHALLENGE_VERSION, Fact

ROOT = Path(__file__).resolve().parent
BASE = Path('/mnt/data/tdfc_v2201_debug/Teals_Daily_Fact_Challenge_v2_20_1_FULL_CURRENT_APP/UPLOAD_TO_GITHUB')
APP = (ROOT / 'app.py').read_text()
STORE = (ROOT / 'supabase_fact_store.py').read_text()
RECOVERY = (ROOT / 'student_daily_save_recovery.py').read_text()

checks = {}
def check(name, condition):
    checks[name] = bool(condition)
    if not condition:
        raise AssertionError(name)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

check('version 2.20.3', APP_VERSION == '2.21.0')
check('challenge version untouched', CHALLENGE_VERSION == 'TDFC-DAILY-v1')
check('multiplication Daily component untouched', sha(ROOT/'daily_sprint_component'/'index.html') == sha(BASE/'daily_sprint_component'/'index.html'))
check('alternate Daily component untouched', sha(ROOT/'daily_alt_component'/'index.html') == sha(BASE/'daily_alt_component'/'index.html'))
check('guided practice component untouched', sha(ROOT/'guided_practice_component'/'index.html') == sha(BASE/'guided_practice_component'/'index.html'))
check('alt fix component untouched', sha(ROOT/'alt_fix_component'/'index.html') == sha(BASE/'alt_fix_component'/'index.html'))
check('alt focus component untouched', sha(ROOT/'alt_focus_component'/'index.html') == sha(BASE/'alt_focus_component'/'index.html'))
check('no SQL migration', not list(ROOT.glob('*2_20_2*.sql')))

# Retry now requests a fresh one-run Supabase client rather than merely rerunning
# the same cached resource that just failed.
check('recovery requests fresh store', 'st.session_state["tdfc_force_fresh_store_once"] = True' in RECOVERY)
check('get_store consumes fresh flag', 'st.session_state.pop("tdfc_force_fresh_store_once", False)' in APP)
check('fresh store bypasses cached load_store', 'return SupabaseFactStore.from_secrets(st.secrets)' in APP)
check('completed-screen retry requests fresh store', APP.count('st.session_state["tdfc_force_fresh_store_once"] = True') >= 2)

# The official Daily result is now committed before secondary evidence work.
check('multiplication save defers evidence', 'defer_evidence=True' in RECOVERY and 'store.complete_full_attempt(' in RECOVERY)
check('alternate save defers evidence', 'store.complete_custom_attempt(' in RECOVERY and RECOVERY.count('defer_evidence=True') >= 2)
check('store has two-request multiplication core', 'def persist_full_attempt_completion(' in STORE)
check('store has one-request alternate core', 'def persist_custom_attempt_completion(' in STORE)

mult_core = STORE[STORE.index('    def persist_full_attempt_completion('):STORE.index('    def persist_custom_attempt_completion(')]
alt_core = STORE[STORE.index('    def persist_custom_attempt_completion('):STORE.index('    def complete_full_attempt(')]
check('multiplication core has one answer upsert', mult_core.count('daily_answers').__eq__(1) and '.upsert(' in mult_core)
check('multiplication core avoids answer verification reread', 'get_answers(' not in mult_core)
check('multiplication core has one summary update', mult_core.count('daily_attempts') == 1 and '.update({' in mult_core)
check('alternate core has only attempt summary table', 'daily_answers' not in alt_core and alt_core.count('daily_attempts') == 1)
check('default multiplication API still repairs evidence', 'return self.ensure_daily_learning_evidence(attempt_id)' in STORE[STORE.index('    def complete_full_attempt('):STORE.index('    def complete_custom_attempt(')])
check('default alternate API still repairs evidence', 'return self.ensure_daily_learning_evidence(attempt_id)' in STORE[STORE.index('    def complete_custom_attempt('):STORE.index('    def ensure_daily_learning_evidence(')])

# Behavioral save wrapper check: the critical student path must pass the already
# loaded attempt and explicitly defer evidence. This keeps the official save tiny.
fake_streamlit_module = ModuleType('streamlit')
sys.modules.setdefault('streamlit', fake_streamlit_module)
import student_daily_save_recovery as recovery

class FakeSt:
    def __init__(self, button=False):
        self.session_state = {}
        self.query_params = {}
        self.button_value = button
    def error(self, *_): pass
    def caption(self, *_): pass
    def button(self, *_, **__): return self.button_value
    def rerun(self): raise RuntimeError('RERUN')
    def exception(self, *_): pass

class CaptureStore:
    def __init__(self, fail=False):
        self.fail = fail
        self.mult = []
        self.alt = []
    def complete_full_attempt(self, *args, **kwargs):
        self.mult.append((args, kwargs))
        if self.fail: raise ConnectionError('save failed')
        return SimpleNamespace(completed_at='done')
    def complete_custom_attempt(self, *args, **kwargs):
        self.alt.append((args, kwargs))
        if self.fail: raise ConnectionError('save failed')
        return SimpleNamespace(completed_at='done')

original_st = recovery.st
try:
    fake = FakeSt()
    recovery.st = fake
    facts = [Fact(2, i, 'core') for i in range(2, 12)]
    attempt = SimpleNamespace(attempt_id='m1')
    payload = {'status':'complete','answers':[f.product for f in facts], 'first_answers':[f.product for f in facts], 'response_seconds':[None]+[1.0]*9, 'timed_seconds':12.0}
    cap = CaptureStore()
    check('multiplication wrapper succeeds', recovery.save_multiplication_daily(cap, attempt, facts, payload) is True)
    check('multiplication passes attempt record', cap.mult[-1][1].get('attempt_record') is attempt)
    check('multiplication passes defer evidence', cap.mult[-1][1].get('defer_evidence') is True)

    alt_attempt = SimpleNamespace(attempt_id='a1')
    alt_payload = {'status':'complete','answers':list(range(10)), 'timed_seconds':12.0}
    cap2 = CaptureStore()
    check('alternate wrapper succeeds', recovery.save_alternate_daily(cap2, alt_attempt, alt_payload) is True)
    check('alternate passes attempt record', cap2.alt[-1][1].get('attempt_record') is alt_attempt)
    check('alternate passes defer evidence', cap2.alt[-1][1].get('defer_evidence') is True)

    # A clicked retry marks the next app run for a fresh Supabase store.
    fake_click = FakeSt(button=True)
    recovery.st = fake_click
    failing = CaptureStore(fail=True)
    try:
        recovery.save_multiplication_daily(failing, attempt, facts, payload)
    except RuntimeError as exc:
        check('retry button triggers rerun', str(exc) == 'RERUN')
    else:
        raise AssertionError('retry button did not rerun')
    check('retry button marks fresh connection', fake_click.session_state.get('tdfc_force_fresh_store_once') is True)
    check('failed payload remains preserved', recovery.pending_daily_payload(attempt.attempt_id) == payload)
finally:
    recovery.st = original_st

print(f'v2.20.3 Daily Save Resilience: PASS ({len(checks)}/{len(checks)} checks)')
