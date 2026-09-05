# Teal's Daily Fact Challenge v2.19.7 — Follow-Up Lifecycle + Height Reliability

v2.19.7 repairs the complete non-multiplication follow-up interaction path used by Addition, Subtraction, Division, Integers, and Mixed. This is intentionally a controller/lifecycle repair rather than another isolated button patch.

## What was actually wrong

The alternate Fix Your Misses / Focus Practice components had drifted from multiplication underneath the UI. They used their own timestamp/resume state machine and rebuilt the teaching DOM during routine Streamlit render messages. That made a valid-looking **WATCH IT** button vulnerable to becoming stranded when the live component lifecycle did not match the isolated browser test.

The same alternate layout also kept later teaching content in the page with `opacity: 0`, which hid it visually but still reserved its height. Combined with scroll-height-based iframe sizing, this could leave a very long page with large amounts of blank white space.

## What changed

- **WATCH IT** now uses the same controller pattern as multiplication: one direct `startTeachSequence()` path.
- **REPLAY** calls that same controller and fully resets the visible teaching stages before replaying.
- **TRY AGAIN** remains unavailable until the teaching sequence reaches **YOUR TURN**, then transitions into the retry keypad.
- Routine same-session Streamlit render messages now preserve the live teaching DOM instead of rebuilding it and interrupting the active sequence.
- Legacy/unknown teaching phases are normalized safely back to the valid coaching state instead of showing a button that cannot run.
- Fix Your Misses now uses session-scoped browser state, matching multiplication's safer lifecycle rather than persistent local storage.
- Future teaching stages are `display: none` until SEE IT / CONNECT IT / YOUR TURN actually reach them, eliminating the giant invisible reserved area before WATCH IT.
- Iframe height is measured from the actual rendered root content, so it can **grow and shrink** instead of retaining stale viewport/scroll height.
- A root `ResizeObserver` keeps height synchronized as stages appear, replay, or transition.
- Fix and Focus component identities/state contracts were advanced so student browsers load the corrected components fresh.
- The v2.19.5 alternate Daily typed-answer display fix remains intact.

## What did NOT change

The multiplication Daily, multiplication Guided Practice / Fix Your Misses / Focus Practice component, multiplication Fact Coach, multiplication adaptive/mastery engine, Weekly Mystery, Supabase schema, dependencies, and AWTRIX are unchanged.

The protected multiplication files were verified byte-for-byte against the established source-of-truth hashes.

## Verification

- **86/86 Python regression test files passed** across three complete batches.
- New **v2.19.7 Follow-Up Lifecycle + Height** suite: **67/67 checks passed**.
- Updated alternate follow-up parity regression: **47/47 checks passed**.
- Classroom-hardening regression: **48/48 checks passed**.
- A real Chromium iframe audit exercised the actual component message lifecycle under deliberately noisy Streamlit-style same-session rerenders.
- Chromium audit passed on both desktop and touch emulation for **WATCH IT → REPLAY → TRY AGAIN → keypad → submit**.
- The exact reported Integer example `5 − (-5)` was exercised end-to-end.
- Browser audit verified that the teaching card starts compact, grows as stages appear, and **shrinks again on Replay** rather than retaining white space.
- Browser audit covered every generated alternate teaching visual family found in the 2026 question generators.
- Production pacing was separately exercised at the real 180 ms / 1350 ms / 2650 ms stage timing.
- All browser component JavaScript files pass syntax checking.
- All Python files compile successfully.

No Supabase SQL, Streamlit Secret, or AWTRIX change is required. Install directly over v2.19.6.
