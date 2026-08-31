# Teal's Daily Fact Challenge — Stability Contract

This contract was rebased in v2.11.2 on the proven v2.11.0.3 classroom build to reduce regression and UI drift as the app grows.

## Protected student workflow

1. Students sign in before Today / Practice navigation is shown.
2. If an Igniter is assigned, it appears before the Daily 10.
3. Igniter correctness feedback is explicit and separate from completion.
4. Daily 10 remains accuracy-first; time is only a tie-breaker.
5. Fix Your Misses records correction work without replacing the original miss.
6. Focus Practice remains personalized and browser-local between questions.
7. Mystery reward remains optional and separate from completion of learning work.
8. Student leaderboards show rank + nickname only, never teacher-only scores/times.
9. Test Student remains excluded from real roster/class/mastery/leaderboard/Mystery/raffle/export evidence.

## Protected teacher workflow

1. Teacher sections render one active section at a time.
2. Refresh Data must clear the cached Supabase store before fresh reads.
3. Learning Data owns Fact Fluency + Igniter Standards Tracker only.
4. Warm-Up planning/results is isolated from Student Daily and Learning Data code.
5. Unfinished Igniter work is never counted as incorrect or placed into reteach groups.
6. Outlook reports are prepared for teacher review; the app does not auto-send email.
7. Historical Igniter standards evidence is described as evidence, not automatic mastery.
8. Teacher Today Warm-Up groups/email and Student Support Focus controls must remain callable after module refactors.
9. A failure to remember Recently Used standards must never make a successfully saved Igniter appear unsaved.

## Protected resilience behavior

1. The visible app shell renders before database-dependent remembered-login work.
2. Temporary remembered-login network failures do not erase a valid 30-day login token.
3. Supabase request waits remain bounded and hard timeouts do not stack unlimited retries.
4. A temporary Daily-load failure keeps the student signed in, preserves completed Igniter work, and offers Try Again.
5. Supabase mutation writes remain compatible with the pinned `supabase==2.28.3` client.
6. Connection/timing diagnostics never log student names, PINs, questions, or answers.

## Module boundaries

- `app.py` — routing, shared session state, Student Daily/Practice, teacher roster/support/mystery shell.
- `teacher_today_ui.py` — teacher-only Today Command Center, all-class snapshot, roster-based quick follow-ups, and teacher quick routes.
- `teacher_command_center.py` — pure teacher-only Today/attendance summary helpers; no student routing.
- `student_igniter_ui.py` — student Igniter only.
- `teacher_warmup_ui.py` — teacher Igniter planning/results/email/export only.
- `teacher_learning_ui.py` — Fact Fluency + Standards Tracker only.
- `teacher_clock_ui.py` — teacher-only AWTRIX class mapping, token setup, and manual Top 10 queue controls only.
- `ui_helpers.py` — small shared presentation helpers.
- `fact_engine.py`, `adaptive_engine.py`, `teacher_insights.py` — domain logic; no Streamlit page routing.
- `fact_store.py`, `supabase_fact_store.py` — persistence boundary.

## Release rule

Future releases should run `python release_guard.py` plus the full `*_tests.py` suite before packaging. A feature should not be considered complete merely because source text exists; behavior-oriented checks should be preferred whenever practical.

## Data-trust protections added after the foundation pass

- Teacher **Needs Help** must require repeated independent misses; one isolated miss must never create a red intervention flag.
- Teacher **Accurate, Still Slow** must require sustained evidence; one classroom pause must not create a yellow speed concern.
- The Daily browser may let a student revisit an answer, but persistent mastery evidence must preserve the **first submitted answer** separately from the official/final Daily score.
- A completed Daily must be repairable if the network fails between saving the official attempt and applying mastery/learning-progress evidence. The repair path must be idempotent.
- Historical pre-patch Daily answers may fall back to their stored official answer as the best available first-answer evidence.

## Physical clock / AWTRIX protections added in v2.12.0

1. The physical clock receives **rank + assigned nickname only**. Never send real names, scores, completion times, PINs, student IDs, teacher data, or answer-level student data to AWTRIX.
2. `SUPABASE_SECRET_KEY` must never be stored on or sent to the clock. The clock uses only a public Supabase client key plus a separate scoped/revocable clock token.
3. The clock token is stored in Supabase only as a SHA-256 hash; rotating it invalidates the previous clock token.
4. AWTRIX clock tables remain RLS-protected with no direct browser policies. Only the narrow clock RPC functions may be executed by public client roles.
5. The existing classroom `Class Schedule` script remains independent. Fact Challenge integration is a second headless script so leaderboard work does not alter schedule banners.
6. Automatic Top 10 timing lives on the clock and may use outbound HTTPS only; the cloud app must not depend on reaching a private classroom IP address.
7. Top 10 ordering must remain the same accuracy-first Daily leaderboard contract: correct count first, time only as tie-breaker, then completion timestamp. Test Student remains excluded.
8. The teacher must retain a manual **Send Top 10 to Clock Now** control so the integration can be tested/replayed independently of automatic schedule timing.

## v2.12 classroom-clock safety additions
- AWTRIX/clock work stays teacher-only; it must not add database/network work to Student Sign In, Igniter, Daily 10, Fix Misses, Focus Practice, or Practice.
- A transient `daily_status()` / PostgREST failure must not crash Teacher Today or block access to independently loaded Igniter results. Projector mode must keep Back/Refresh usable.
- Clock integration must continue to expose only the student-safe Top 10 payload and must never place the Supabase secret/service key on the physical clock.

## v2.12.0 Hotfix 3 — Top 10 chime contract
- The Fact Top 10 AWTRIX script may play one short RTTTL chime when a Top 10 notification first appears.
- The chime is attached to both automatic and teacher-manual Top 10 notifications.
- It must not loop and must not play before each ranked nickname.
- The separate Class Schedule script and its sounds remain untouched.
- Student app flow and student database workload remain unchanged by clock sound behavior.


## v2.14 Teacher Command Center protections

- The student-facing sign-in, Daily, Practice, Igniter, alternate Daily, browser components, Fact Coach, adaptive engine, and persistent-login paths remain unchanged from v2.13.2.
- Legacy teacher-attendance helper functions may remain for backward compatibility, but v2.14.1 Today intentionally does not require daily attendance maintenance; class counts use the active roster directly.
- A student who already completed the Daily 10 cannot be marked absent, preventing attendance metadata from silently changing a completed student-facing Top 10 result.
- Reopening a Daily remains an explicit teacher action with confirmation and uses the existing reset/rebuild path.
- Archiving a student uses the existing inactive-account behavior and preserves history/PIN for restoration.
- Primary teacher navigation keeps Today, Warm-Up, Learning, Weekly Mystery, and Manage one tap away; Classes & Rosters, Clock, and Test Student remain grouped under Manage.
## v2.14.2 Weekly Mystery raffle safety protections

- A saved raffle result is historical data and must remain visible after all classes have been drawn; the UI must not depend only on whether a raffle is still pending.
- The initial Draw Winner action must display the saved winner before any navigation/rerun can move the teacher away from the result.
- Saved winner nickname/class metadata remains recoverable from `app_settings` even if later roster/eligibility state changes.
- Teacher Weekly Mystery is projector-safe by default: mystery answers and clues for both the active week and planned next week remain inside collapsed teacher-only panels.
- Delayed prior-week raffle drawing must never reveal the new week's mystery merely because the last pending raffle becomes complete.

## v2.14.3 Weekly Mystery / teacher navigation protections

- Teacher Weekly Mystery should show the active/current week before prior-week raffle history.
- Prior-week saved raffle winners remain visible at the bottom even after every class drawing is complete.
- Removing explanatory safety banners must never remove the actual projector-safety behavior: current and next-week answers/clues stay in collapsed teacher-only panels.
- Weekly Mystery is a primary teacher navigation destination; Manage contains only Classes & Rosters, Clock, and Test Student.
- This polish remains teacher-only and must not change student Mystery, Daily 10, mastery, login/PIN, or AWTRIX behavior.
