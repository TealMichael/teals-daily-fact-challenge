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

- `app.py` — routing, shared session state, Student Daily/Practice, Teacher Today/roster/support/mystery shell.
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
