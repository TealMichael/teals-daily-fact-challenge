# Teal's Daily Fact Challenge v2.19.6 — Alternate Follow-Up Interaction Parity

v2.19.6 fixes the student interaction flow used after non-multiplication Daily 10 work (Addition, Subtraction, Division, Integers, and Mixed).

The alternate teaching model had drifted from the proven multiplication behavior in two important ways: it auto-played as soon as the screen rendered, and the Fix/Focus browser components could remain stale on student devices even after code fixes. That made REPLAY and TRY AGAIN appear unresponsive in the classroom.

## What changed

- Teaching models now wait for the student to tap **WATCH IT**, matching multiplication.
- **WATCH IT** and **REPLAY** now use the same single-click restart path as multiplication.
- **REPLAY** visibly restarts the teaching sequence from the beginning.
- **TRY AGAIN** remains locked until the teaching sequence reaches YOUR TURN, then reliably opens the retry keypad.
- Fix Your Misses and Focus Practice component identities were cache-busted so student devices receive the corrected browser code.
- Old alternate Fix/Focus browser state is intentionally invalidated for this release so a stale in-progress model cannot keep the old behavior.
- The v2.19.5 alternate Daily keypad display fix remains intact.

## What did NOT change

The multiplication Daily, multiplication Guided Practice / Fix Your Misses / Focus Practice component, multiplication Fact Coach, multiplication adaptive/mastery engine, Weekly Mystery, Supabase schema, dependencies, and AWTRIX are unchanged.

The protected multiplication files were verified byte-for-byte against the v2.19.5 source-of-truth hashes.

## Verification

- 85/85 Python regression test files passed.
- New v2.19.6 alternate follow-up parity suite: 47/47 checks passed.
- Real browser interaction audit passed on desktop and touch emulation for Daily keypad, Fix Your Misses, and Focus Practice.
- Browser audit covered Addition, Subtraction, Division, positive/negative Integer cases, and a Mixed multiplication item.
- WATCH IT no-autoplay behavior, REPLAY restart, TRY AGAIN transition, keypad digits, minus, Delete, and green-check submit were exercised.
- Same-session rerender recovery was exercised during a teaching sequence.
- All 8 browser component JavaScript files passed syntax checking.
- All 115 Python files compiled successfully.

No Supabase SQL, Streamlit Secret, or AWTRIX change is required. Install directly over v2.19.5.
