from pathlib import Path
from types import SimpleNamespace, ModuleType
import sys

from fact_engine import APP_VERSION, CHALLENGE_VERSION, Fact

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
ALT = (ROOT / 'student_alt_daily_ui.py').read_text(encoding='utf-8')
RECOVERY = (ROOT / 'student_daily_save_recovery.py').read_text(encoding='utf-8')

checks = {}
def check(name, condition):
    checks[name] = bool(condition)
    if not condition:
        raise AssertionError(name)

check('version 2.20.3', APP_VERSION == '2.21.0')
check('challenge version untouched', CHALLENGE_VERSION == 'TDFC-DAILY-v1')
check('render path reconciles pending server state', 'attempt = reconcile_pending_daily_attempt(store, attempt)' in APP)
check('recovery scopes pending student', 'student_id' in RECOVERY and 'pending_daily_save_meta' in RECOVERY)
check('recovery scopes pending challenge', 'challenge_id' in RECOVERY and 'pending_daily_save_meta' in RECOVERY)
check('recovery uses fresh server lookup', 'fresh_store.get_attempt_for_student(student_id, challenge_id)' in RECOVERY)
check('server completion clears stale pending', 'if getattr(server_attempt, "completed_at", None) is not None:' in RECOVERY)
check('teacher-reset mismatch clears stale pending', 'str(server_attempt.attempt_id) != aid' in RECOVERY)
check('normal component key remains backward compatible', 'return base if generation <= 0 else' in RECOVERY)
check('multiplication uses recovery-aware attempt key', 'attempt_key=daily_component_attempt_key(' in APP)
check('alternate uses recovery-aware attempt key', 'attempt_key=daily_component_attempt_key(' in ALT)
check('stuck fallback exists', 'Start Daily 10 over on this device' in RECOVERY)
check('fallback only after repeated failure', 'allow_restart and failures > 1' in RECOVERY)
check('no browser component edits required', 'recovery_generation' not in (ROOT/'daily_sprint_component'/'index.html').read_text())
check('no SQL migration', not list(ROOT.glob('*2_20_3*.sql')))

fake_streamlit_module = ModuleType('streamlit')
sys.modules.setdefault('streamlit', fake_streamlit_module)
import student_daily_save_recovery as recovery

class FakeSt:
    def __init__(self, clicked=None):
        self.session_state = {}
        self.query_params = {}
        self.clicked = clicked
        self.messages = []
        self.secrets = {}
    def error(self, text): self.messages.append(('error', text))
    def caption(self, text): self.messages.append(('caption', text))
    def button(self, label, **kwargs):
        self.messages.append(('button', label))
        return label == self.clicked
    def rerun(self): raise RuntimeError('RERUN')
    def exception(self, exc): self.messages.append(('exception', type(exc).__name__))

class SaveStore:
    def __init__(self, fail=True):
        self.fail = fail
        self.full_calls = 0
        self.custom_calls = 0
    def complete_full_attempt(self, *args, **kwargs):
        self.full_calls += 1
        if self.fail: raise RuntimeError('write failed')
        return SimpleNamespace(completed_at='done')
    def complete_custom_attempt(self, *args, **kwargs):
        self.custom_calls += 1
        if self.fail: raise RuntimeError('write failed')
        return SimpleNamespace(completed_at='done')
    def get_attempt_for_student(self, student_id, challenge_id):
        return None

orig_st = recovery.st
orig_fresh = recovery._fresh_server_attempt
try:
    fake = FakeSt()
    recovery.st = fake
    attempt = SimpleNamespace(attempt_id='a1', student_id='s1', challenge_id='c1', completed_at=None)
    payload = {'status':'complete', 'answers':list(range(10)), 'timed_seconds':12.0}
    recovery._capture('a1', payload)
    recovery._scope_pending_daily_payload(attempt)

    # A stale payload for another signed-in student is discarded immediately.
    check('matching scoped payload is returned', recovery.pending_daily_payload('a1', student_id='s1', challenge_id='c1') == payload)
    check('student mismatch discards pending', recovery.pending_daily_payload('a1', student_id='s2', challenge_id='c1') is None)
    check('student mismatch actually clears session copy', recovery.pending_daily_payload('a1') is None)

    # Rebuild pending and prove an already-saved server attempt self-heals.
    recovery._capture('a1', payload)
    recovery._scope_pending_daily_payload(attempt)
    completed = SimpleNamespace(attempt_id='a1', student_id='s1', challenge_id='c1', completed_at='server-done')
    recovery._fresh_server_attempt = lambda store, att: (completed, True)
    reconciled = recovery.reconcile_pending_daily_attempt(SaveStore(), attempt)
    check('reconcile returns completed server attempt', reconciled is completed)
    check('reconcile clears stale completed payload', recovery.pending_daily_payload('a1') is None)

    # Normal generation zero must keep the exact historic browser key so deploys
    # do not erase a student who is midway through today's Daily.
    key0 = recovery.daily_component_attempt_key('s1', 'c1', 'a1')
    check('generation zero preserves historic key', key0 == 's1:c1:a1')
    recovery._restart_daily_on_this_device('a1')
    key1 = recovery.daily_component_attempt_key('s1', 'c1', 'a1')
    check('device restart switches browser storage generation', key1 == 's1:c1:a1:recovery-1')

    # Ambiguous save failure: if the server actually committed, treat it as success
    # rather than showing an endless retry page.
    fake.session_state.clear()
    recovery._fresh_server_attempt = lambda store, att: (completed, True)
    facts = [Fact(2, i, 'core') for i in range(2, 12)]
    mult_payload = {
        'status':'complete', 'answers':[f.product for f in facts],
        'first_answers':[f.product for f in facts],
        'response_seconds':[None] + [1.0]*9, 'timed_seconds':10.0,
    }
    bad_store = SaveStore(fail=True)
    check('ambiguous multiplication commit self-heals as success', recovery.save_multiplication_daily(bad_store, attempt, facts, mult_payload) is True)
    check('ambiguous multiplication success clears pending', recovery.pending_daily_payload('a1') is None)

    # Confirmed-incomplete repeated failures expose a true escape from a poisoned
    # device payload; first failure should not encourage a redo.
    fake.session_state.clear()
    incomplete = SimpleNamespace(attempt_id='a1', student_id='s1', challenge_id='c1', completed_at=None)
    recovery._fresh_server_attempt = lambda store, att: (incomplete, True)
    recovery.save_multiplication_daily(bad_store, attempt, facts, mult_payload)
    check('first failure does not offer restart', not any(v == '↩️ Start Daily 10 over on this device' for k,v in fake.messages if k=='button'))
    fake.messages.clear()
    recovery.save_multiplication_daily(bad_store, attempt, facts, mult_payload)
    check('second confirmed failure offers restart escape', any(v == '↩️ Start Daily 10 over on this device' for k,v in fake.messages if k=='button'))
finally:
    recovery.st = orig_st
    recovery._fresh_server_attempt = orig_fresh

print(f'v2.20.3 Stale Device Recovery: PASS ({len(checks)}/{len(checks)} checks)')
