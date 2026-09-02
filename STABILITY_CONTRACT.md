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
3. Learning Data owns Fact Fluency + Warm-Up Standards Tracker only.
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
- `teacher_intelligence.py` — pure teacher-only Phase 2 interpretation helpers; no Streamlit routing or student writes.
- `teacher_intelligence_ui.py` — Next Steps, Weekly Recap, and Student Support learning snapshots only.
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

## v2.15 Phase 2 instructional-intelligence protections

- Phase 2 is teacher-facing interpretation only. It must not write mastery, assign Focus plans, alter Daily attempts, or change student-facing routines.
- Alternate Daily 10 modes may count in teacher completion summaries, but only Multiplication Daily answers may contribute to fact-level fluency intelligence.
- "Needs Help" and speed interpretations continue to use the existing conservative teacher band logic; a single miss or one slow classroom interruption must not create an intervention signal.
- Repeated-error signals are recent (roughly two weeks) so recovered errors do not remain on the teacher watch list indefinitely.
- Meaningful-progress signals require enough independent multiplication evidence in both comparison windows before showing an improvement claim.
- Fragile retrieval is a conservative watch signal, not a claim that a student lost mastery; the current database does not store historical mastery-status snapshots.
- Suggested groups are recommendations only and remain bounded/short. They do not automatically change any student Focus override.
- Weekly Recap must label estimated/newly-secured fluency momentum honestly rather than presenting it as an exact historical status transition.
- Teacher history reads must stay bulked/chunked so a class-level insight page does not create one database request per student or exceed PostgREST URL limits.
- `teacher_insights.py` and the existing Learning Data UI remain unchanged; Phase 2 lives beside them in `teacher_intelligence.py` and `teacher_intelligence_ui.py`.

## v2.16 Phase 3 planning/history protections

- Phase 3 remains teacher-only. Student Daily, Practice, Fix/Focus, Fact Coach, mastery, student Igniter, student Mystery, login/PIN, and AWTRIX behavior must not change.
- Warm-Up copy/template actions may never overwrite a Warm-Up after a real student has answered it; the existing Warm-Up lock remains authoritative.
- Warm-Up student preview must hide correct answers.
- Historical raw Warm-Up response text remains subject to the existing next-day cleanup policy; Class History may show correctness/standards evidence but must not claim old raw response text still exists.
- Daily 10 weekly planning reuses the existing per-class/date mode settings. Multiplication remains the default and `TDFC-DAILY-v1` remains unchanged.
- Alternate Daily 10 modes remain separate from multiplication fluency evidence in Class History and Phase 2 intelligence.
- Class History is read-only: viewing a past date must not reopen attempts, change mastery, edit Warm-Ups, or alter Mystery records.
- Current/next Mystery answers remain protected behind collapsed teacher-only details where they could be visible on a projector.


## v2.16.1 UI language polish protections

- Normal classroom screens should use teacher/student language rather than implementation language. Supabase, schema/migration, sandbox, engine, and diagnostic terminology should not appear in everyday workflows.
- Technical clock-install details remain available only inside the collapsed **One-time clock setup** area because they are needed for recovery/reinstallation.
- Copy edits must not change Daily generation/scoring, mastery, Warm-Up grading, Mystery rules, login/PIN behavior, Top 10 privacy, persistence, or AWTRIX behavior.
- Copy-polished student functions are protected structurally in `v2_16_1_ui_language_polish_tests.py`; changing visible strings must not silently change their control flow.


## v2.16.2 Weekly Mystery clue reliability protections (historical; alternate completion rule superseded by v2.17/v2.19)

- A Mystery clue is earned only for a school day whose required routine was actually completed. A genuinely skipped day must never be backfilled.
- The current day's clue is saved first when the student reaches the completed-routine Mystery reward. Optional prior-day repair work must not block today's reward.
- A missing prior-day clue receipt may be restored only when already-saved Daily/learning records prove that day was completed.
- At v2.16.2, alternate Daily modes qualified from the completed Daily because they had no follow-up routine. Current v2.19 alternate routines qualify only after their full Fix + Focus progress is complete; Multiplication continues to use its established learning progress.
- Weekly Mystery reads, clue writes, guess reads/writes, and student Mystery stats use transient HTTP retry protection. Lost mutation responses must be re-read safely before reporting failure.
- Mystery reliability repair must not change Mystery content, clue order, Thursday/Friday guess rules, raffle eligibility, `TDFC-DAILY-v1`, mastery evidence, Daily scoring, or AWTRIX behavior.


## v2.16.3 Daily touch keypad protections

- The Daily 10 number buttons must remain mounted while a student enters or deletes digits; digit entry updates only the answer display.
- A rapid second digit must not depend on a newly recreated keypad node or newly rebound button listener.
- The `0` button remains a normal digit key and multi-digit answers retain the existing three-digit limit and leading-zero normalization.
- Question-to-question transitions and Back navigation may rerender the question because those are deliberate navigation events.
- Hidden timing, first-answer evidence, official final-answer scoring, local Daily continuity, `TDFC-DAILY-v1`, and the no-feedback-during-Daily rule remain unchanged.
- Guided Practice, PIN entry, alternate Daily, Mystery, mastery, teacher tools, requirements, and AWTRIX remain byte-for-byte unchanged from v2.16.2.

## v2.16.4 Alternate Daily teacher-dashboard protections (historical; superseded by v2.17/v2.19)

- At v2.16.4, alternate modes ended after Daily 10. That historical behavior was intentionally superseded: v2.17 added Fix Your Misses and v2.19 adds Focus Practice.
- A completed alternate Daily counts as `Done` in Today metrics and in `Where everyone is` even though no multiplication learning-progress row exists.
- Multiplication keeps the established Daily → Fix Misses → Focus → Done routine unchanged.
- Teacher Today does not query multiplication learning progress to decide follow-up stages on alternate-mode days.
- Student Daily behavior, alternate Daily completion/Mystery reward, multiplication generation, mastery, Warm-Up, Mystery rules, AWTRIX, and database schema remain unchanged.


## v2.17 Follow-Up Foundation protections (foundation; completion contract extended by v2.19)

- Multiplication keeps its established Daily → Fix Your Misses → Focus Practice → Done contract and existing mastery/adaptive engine unchanged.
- v2.17 introduced Daily → Fix Your Misses for Addition, Subtraction, Division, Integers, and Mixed. v2.19 extends that foundation with Focus Practice before Done/Mystery.
- An alternate-mode day is not Mystery-complete until its required Fix Your Misses work is complete. Historical pre-v2.17 completed alternate Dailies are backfilled as complete by the v2.17 migration.
- Mixed-mode questions are recorded under their true domains. Mixed multiplication questions may create alternate-learning events but must never write into multiplication mastery evidence.
- Alternate learning uses `alternate_learning_progress` and `alternate_learning_events`; it must remain separate from `daily_learning_progress` and the multiplication mastery map.
- The original Daily 10 score, time, and Top 10 rank remain based only on the official ten-question attempt; Fix Your Misses speed/results do not rewrite the official Daily result.
- Alternate Fix Your Misses requires every originally missed question to be corrected before completion; the server/store validates the submitted corrections rather than trusting the browser component.
- The alternate Fix keypad keeps number buttons mounted during digit entry, preserving the rapid-touch reliability pattern established in v2.16.3.
- v2.17 is the foundation only. Full domain-specific teaching models and adaptive alternate Focus Practice belong to later releases and must not be simulated by writing into multiplication systems.

## v2.18 Teaching Models protections (teaching layer; Focus layer added by v2.19)

- Multiplication is the gold-standard source of truth and remains frozen: the multiplication Daily component, Guided Practice component, answer pad, Fact Coach, adaptive/mastery engine, `TDFC-DAILY-v1`, requirements, and AWTRIX must remain byte-identical to v2.17.0.
- v2.18 changes the teaching presentation of alternate Fix Your Misses only. It does not change official Daily score/time, Top 10 ranking, alternate follow-up storage, Mystery completion rules, or multiplication mastery evidence.
- Every alternate miss starts in a coaching/model stage before the retry, mirroring the established multiplication Fix Your Misses rhythm.
- Teaching plans are deterministic. The same question must select the same strategy/model every time.
- Addition models use mathematically valid make-10, doubles/near-doubles, count-on, or zero relationships.
- Subtraction models use a valid part-whole / related-addition relationship.
- Division models use valid equal groups and explicitly connect to the inverse multiplication fact.
- Integer models use signed number-line movement; subtracting a negative must reverse direction correctly.
- Mixed routes each item by its true domain. Mixed multiplication may read `fact_coach.coach_plan()` for the established strategy, but its events remain in alternate-learning storage and never enter multiplication mastery.
- The alternate teaching keypad keeps its buttons mounted during digit entry and supports negative integer answers.
- v2.18 introduces no new Supabase migration. Adaptive alternate Focus Practice remains reserved for v2.19.

## v2.19 Adaptive Focus Practice protections

- Multiplication remains the frozen gold-standard implementation. The multiplication Daily component, Guided Practice, answer pad, Fact Coach, adaptive/mastery engine, `TDFC-DAILY-v1`, requirements, Weekly Mystery engine, and AWTRIX script remain byte-identical to the v2.18/v2.17 protected baseline.
- Addition Facts, Subtraction Facts, Division Facts, Integers, and Mixed now use the full Daily 10 → Fix Your Misses → Focus Practice → Done/Mystery routine.
- Alternate Focus Practice contains exactly eight planned questions. A perfect Daily may skip an empty Fix step, but it does not skip Focus Practice.
- Adaptive priority uses independent retrieval evidence only. Original Daily answers and first Focus attempts may influence future plans; Fix Your Misses corrections and coached Focus retries must not inflate mastery/need signals.
- Current Daily misses are the strongest same-day Focus signal. Older independent evidence is recency-weighted so old struggles do not follow a student indefinitely.
- Mixed Focus routing uses each item's true domain. Mixed multiplication may use the established multiplication teaching strategy, but all of its Focus evidence remains in `alternate_learning_events` and never enters multiplication mastery.
- The browser cannot decide whether Focus is complete. The store validates the saved eight-question plan, first-attempt-before-retry ordering, server-computed correctness, and required corrected retries before setting `focus_completed_at` / `completed_at`.
- Official Daily score, elapsed time, and Top 10 rank remain based on the original ten-question Daily attempt. Focus Practice does not rewrite the official Daily result.
- Teacher Today shows the same stage vocabulary for every mode: Daily 10 → Fix Your Misses → Focus Practice → Done.
- Student Support may show alternate Focus progress/targets, but multiplication mastery and alternate-learning evidence remain separate systems.
- v2.19 uses the Focus fields and event activity slot already created by the v2.17 migration. There is no v2.19 Supabase migration and no retroactive reopening of already-completed alternate routines.
