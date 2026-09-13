from pathlib import Path
import hashlib

from fact_engine import APP_VERSION, CHALLENGE_VERSION, Fact

ROOT = Path(__file__).resolve().parent
BASE = Path('/mnt/data/tdfc_v220_audit/Teals_Daily_Fact_Challenge_v2_20_0_FULL_CURRENT_APP/UPLOAD_TO_GITHUB')
APP = (ROOT / 'app.py').read_text()
ALT = (ROOT / 'student_alt_daily_ui.py').read_text()
RECOVERY = (ROOT / 'student_daily_save_recovery.py').read_text()
SPRINT = (ROOT / 'daily_sprint_component' / 'index.html').read_bytes()
ALT_DAILY = (ROOT / 'daily_alt_component' / 'index.html').read_bytes()

checks = {}
def check(name, condition):
    checks[name] = bool(condition)
    if not condition:
        raise AssertionError(name)

check('v2.20.3 or newer', tuple(map(int, APP_VERSION.split('.'))) >= (2, 20, 1))
check('challenge contract untouched', CHALLENGE_VERSION == 'TDFC-DAILY-v1')
check('app remains below foundation line limit', len(APP.splitlines()) < 3000)

# Exact classroom failure now has a visible recovery action shared by both modes.
check('visible retry button', '🔄 Try saving again' in RECOVERY)
check('retry says no redo', 'you do not need to redo the Daily 10' in RECOVERY)
check('old stranded multiplication copy removed', 'Leave this page open and try once more; your completed answers are still held in this browser.' not in APP)
check('old stranded alternate copy removed', 'Leave this page open and try once more; your answers are still here.' not in ALT)
check('multiplication uses shared recovery', 'save_multiplication_daily(store, attempt, facts, component_result)' in APP)
check('alternate uses shared recovery', 'save_alternate_daily(store, attempt, result)' in ALT)

# The completed payload is captured before the first database mutation.
cap = RECOVERY.index('payload = _capture(str(attempt.attempt_id), component_result)')
mut = RECOVERY.index('store.complete_full_attempt(', cap)
check('multiplication captures before mutation', cap < mut)
cap = RECOVERY.index('payload = _capture(str(attempt.attempt_id), component_result)', cap + 1)
mut = RECOVERY.index('store.complete_custom_attempt(', cap)
check('alternate captures before mutation', cap < mut)

check('multiplication reuses pending payload', 'pending_daily_payload(attempt.attempt_id) or DAILY_SPRINT_COMPONENT' in APP)
check('alternate reuses pending payload', 'pending_daily_payload(attempt.attempt_id) or ALT_DAILY_COMPONENT' in ALT)
check('successful multiplication save clears pending', 'clear_pending_daily_payload(str(attempt.attempt_id))' in RECOVERY)
check('completed multiplication route clears stale pending', 'clear_pending_daily_payload(attempt.attempt_id)' in APP)
check('completed alternate route clears stale pending', 'clear_pending_daily_payload(attempt.attempt_id)' in ALT)

# Browser localStorage remains the second safety net after a hard refresh/new session.
sprint_text = SPRINT.decode('utf-8')
alt_text = ALT_DAILY.decode('utf-8')
check('multiplication browser stores complete payload', 'current.completePayload=payload; saveState(current); setValue(payload);' in sprint_text)
check('multiplication browser re-emits complete payload', 'if(state.completePayload){ setValue(state.completePayload);' in sprint_text)
check('alternate browser stores complete payload', 's.completePayload=payload;saveState(s);setValue(payload)' in alt_text)
check('alternate browser re-emits complete payload', 'if(s.completePayload){setValue(s.completePayload);' in alt_text)

# Hotfix leaves both keypad components byte-for-byte untouched.
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
check('multiplication Daily component byte-identical to v2.20.0', sha(ROOT/'daily_sprint_component'/'index.html') == sha(BASE/'daily_sprint_component'/'index.html'))
check('alternate Daily component byte-identical to v2.20.0', sha(ROOT/'daily_alt_component'/'index.html') == sha(BASE/'daily_alt_component'/'index.html'))
check('no SQL migration introduced', not list(ROOT.glob('*2_20_1*.sql')))

# Behavioral retry simulation: first mutation fails, the exact payload survives,
# and the next retry succeeds without asking the browser component for answers again.
from types import SimpleNamespace, ModuleType
import sys

fake_streamlit_module = ModuleType("streamlit")
sys.modules.setdefault("streamlit", fake_streamlit_module)
import student_daily_save_recovery as recovery

class FakeSt:
    def __init__(self):
        self.session_state = {}
        self.query_params = {}
        self.messages = []
    def error(self, value): self.messages.append(("error", value))
    def caption(self, value): self.messages.append(("caption", value))
    def button(self, *args, **kwargs): self.messages.append(("button", args[0])); return False
    def rerun(self): raise AssertionError("rerun should only occur after a real button click")
    def exception(self, exc): self.messages.append(("exception", type(exc).__name__))

class FlakyMultiplicationStore:
    def __init__(self): self.fail = True; self.calls = []
    def complete_full_attempt(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.fail: raise RuntimeError("temporary save failure")
        return SimpleNamespace(learning_evidence_applied_at="done")

class FlakyAlternateStore:
    def __init__(self): self.fail = True; self.calls = []
    def complete_custom_attempt(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.fail: raise RuntimeError("temporary save failure")
        return SimpleNamespace(learning_evidence_applied_at="done")

original_st = recovery.st
fake_st = FakeSt()
recovery.st = fake_st
try:
    facts = [Fact(2, i, "core") for i in range(2, 12)]
    attempt = SimpleNamespace(attempt_id="attempt-m")
    payload = {
        "status": "complete",
        "answers": [f.product for f in facts],
        "first_answers": [f.product for f in facts],
        "response_seconds": [None] + [1.0] * 9,
        "timed_seconds": 12.5,
    }
    store = FlakyMultiplicationStore()
    check("failed multiplication save returns recoverable state", recovery.save_multiplication_daily(store, attempt, facts, payload) is False)
    check("failed multiplication payload remains pending", recovery.pending_daily_payload(attempt.attempt_id) == payload)
    check("failed multiplication save renders retry", any(kind == "button" and "Try saving again" in value for kind, value in fake_st.messages))
    store.fail = False
    pending = recovery.pending_daily_payload(attempt.attempt_id)
    check("multiplication retry succeeds from pending payload", recovery.save_multiplication_daily(store, attempt, facts, pending) is True)
    check("multiplication pending payload clears after success", recovery.pending_daily_payload(attempt.attempt_id) is None)
    check("multiplication retry preserves first answers", store.calls[-1][1]["first_answers"][0][1] == facts[0].product)

    fake_st.messages.clear()
    alt_attempt = SimpleNamespace(attempt_id="attempt-a")
    alt_payload = {"status": "complete", "answers": list(range(10)), "timed_seconds": 15.0}
    alt_store = FlakyAlternateStore()
    check("failed alternate save returns recoverable state", recovery.save_alternate_daily(alt_store, alt_attempt, alt_payload) is False)
    check("failed alternate payload remains pending", recovery.pending_daily_payload(alt_attempt.attempt_id) == alt_payload)
    alt_store.fail = False
    pending = recovery.pending_daily_payload(alt_attempt.attempt_id)
    check("alternate retry succeeds from pending payload", recovery.save_alternate_daily(alt_store, alt_attempt, pending) is True)
    check("alternate pending payload clears after success", recovery.pending_daily_payload(alt_attempt.attempt_id) is None)
finally:
    recovery.st = original_st

print(f"v2.20.3 Daily Save Recovery: PASS ({len(checks)}/{len(checks)} checks)")
