# Teal's Daily Fact Challenge v2.14.1 — Teacher Today Polish

**Teacher-side polish only:** Today no longer asks the teacher to maintain attendance exceptions. The action area is renamed **Quick follow-ups**, shows the actual student nicknames that still need each step, and Today → Warm-Up now preserves the selected class instead of returning to Block 1.

The rest of the v2.14 Teacher Command Center remains intact: all-class snapshot, grouped **Today | Warm-Up | Learning | Manage** navigation, resilient teacher data refresh, confirmed Daily reopening, and Archive/Restore controls. Student sign-in, Daily, Practice, alternate Daily, Igniter, Fact Coach, adaptive/mastery behavior, persistent login/PIN components, Daily scoring, `TDFC-DAILY-v1`, Weekly Mystery student flow, and AWTRIX behavior remain protected. **No Supabase SQL, new Streamlit Secret, or AWTRIX reinstall is required.**

---

# Teal's Daily Fact Challenge

> **v2.14.0 — Teacher Command Center:** introduced the Phase 1 all-class Today command center, grouped teacher navigation, quick teacher routes, safer exception controls, and stronger teacher-side data-failure isolation without changing student-facing gameplay.

> **v2.13.2 — Class List ReadError Hotfix:** adds transient retry protection to teacher class-list reads so brief Supabase `httpx.ReadError` resets do not crash class-based teacher screens. No SQL, scoring, mastery, Warm-Up content, Mystery, AWTRIX, login, or student behavior changes.

> **v2.13.1 — Delayed Raffle + Teacher Dashboard Cleanup:** lets the teacher finish an undrawn prior-week Weekly Mystery raffle on Monday or later, without changing the new week's Mystery. The Teacher Dashboard now prioritizes Today and Warm-Up, removes Daily 10 Setup from the top-level navigation, and tucks the exact same setup tool inside Classes & Rosters. No database migration, Streamlit Secret, AWTRIX reinstall, Daily 10 logic, mastery logic, Igniter behavior, or student workflow changes are required.

> **v2.13.0 — Weekly Daily 10 + Igniter Update:** adds per-class/date Daily 10 modes (Multiplication default, Addition, Subtraction, Division, Integers, Mixed), Block 4 app support, and expanded Igniter answer/grading tools. Alternate Daily modes share the normal class Top 10 but write zero multiplication mastery evidence. The proven v2.12 Hotfix 3 multiplication components and AWTRIX script remain protected and unchanged. Run `RUN_THIS_ONCE_IN_SUPABASE_v2_13.sql` once **before** deploying the app files. No new Streamlit Secret or AWTRIX reinstall is required.

> **v2.12.0 Hotfix 2:** restores the previously proven Teacher Today / projector API-resilience behavior after the AWTRIX branch merge. A transient Daily-status PostgREST failure no longer crashes Teacher Today or blocks independently loaded Igniter results. No AWTRIX, student-flow, scoring, mastery, or SQL changes.

> **v2.12.0 Hotfix 1:** fixes the live AWTRIX Supabase `digest()` search path and preserves the Clock mapping save confirmation across Streamlit reruns. No clock script reinstall is required.


## v2.12.0 — AWTRIX Top 10 Clock Integration · Phase 1

This release adds a student-safe bridge between the Daily Fact Challenge and a Ulanzi TC001 running AWTRIX NG, while leaving the existing Daily, Practice, mastery, Igniter, Mystery, and teacher-data workflows unchanged.

- Adds Teacher → **🖥️ Clock** to map the app's three classes to **Block 1, Block 2, and Block 3**.
- Adds a separate revocable clock token. Only its SHA-256 hash is stored in Supabase; the full token is shown only when generated/rotated.
- Adds **📟 Send Top 10 to Clock Now** for teacher-controlled testing/replay. The same control is also available from Teacher → Today for the selected class.
- Adds `AWTRIX_FactTop10.berry`, a second **headless** AWTRIX script. Keep the existing classroom schedule script unchanged.
- Automatic Top 10 windows are the final five minutes of each class block: Mon–Thu **10:35, 1:05, 3:25** windows and Friday **10:25, 12:55, 3:00** windows.
- The clock receives **rank + assigned nickname only**. It never receives real student names, scores, completion times, PINs, student IDs, or teacher-only data.
- The full display string begins with `BLOCK X TOP 10!`, lists #1 through #10, and scrolls the complete sequence **twice** before returning to the clock.
- If the existing Class Schedule banner is already on screen, the Top 10 queues behind it instead of replacing it.
- The clock makes ordinary outbound HTTPS requests, so it does not need a direct local connection to the Streamlit server or teacher laptop. School Wi-Fi or a phone hotspot can provide the connection.
- Requires the one-time `RUN_THIS_ONCE_IN_SUPABASE_v2_12.sql` migration. No new Streamlit Secret is required; `SUPABASE_PUBLISHABLE_KEY` is optional convenience only. Never put `SUPABASE_SECRET_KEY` on the clock.

---

## v2.11.2 — Data Trust Pass

This patch keeps the student Daily experience and official Daily scoring unchanged while tightening four data-trust areas:

- Teacher **Needs Help** now requires repeated independent misses; one isolated miss cannot create a red flag.
- Teacher **Accurate, Still Slow** now requires sustained accurate-but-slow evidence; one classroom pause is not enough.
- Daily 10 now preserves the **first submitted answer** separately for mastery evidence while the official Daily score still uses the student's final answer.
- Completed Daily attempts now have an idempotent repair marker so mastery/learning-progress evidence can recover after a connection interruption.

Run `RUN_THIS_ONCE_IN_SUPABASE_v2_11_2_DATA_TRUST.sql` once before deploying this code. The migration is backward-compatible with the currently installed v2.11.2 app.

---

## v2.11.2 — Post-Daily Student Flow UI Patch

- Keeps the v2.11.2 resilient foundation unchanged except for the student midpoint UI after Daily 10.
- The displayed app version intentionally remains `2.11.2` so this small patch does not force version-only edits across the historical regression suite.
- Removes the midpoint result-card / Top 10 / routine-strip clutter so the required next step is immediately visible.
- Shows a compact `Daily 10 complete!` message followed by `Next: Fix Your Misses` or `Next: Focus Practice`.
- Defers Top 10 standings until the true end-of-day reward screen.
- Keeps `Review your Daily 10` available as a collapsed optional section below the active learning step.
- No scoring, mastery, Daily generation, Mystery, teacher-data, Supabase schema, or resilience rules changed.

## v2.11.2 — Resilient Stability / Foundation Pass

- **No intentional student or teacher UI/behavior changes.** This is the Stability/Foundation work rebuilt from the proven classroom **v2.11.0.3** resilience hotfix.
- Preserves the v2.11.0.1–v2.11.0.3 protections: visible shell before database startup work, safer remembered-login recovery, bounded Supabase waits/retries, recoverable Daily-load retry, privacy-safe timing/connection diagnostics, pinned dependencies, and Supabase 2.28.3-compatible writes.
- Splits three high-change surfaces out of the monolithic `app.py`: **student Igniter**, **Teacher Warm-Up/Igniter**, and **Teacher Learning Data**. Shared display helpers live in `ui_helpers.py`.
- Reduces `app.py` from roughly **3,960 lines to 2,935 lines** while preserving the current routing and workflows.
- Adds/updates `STABILITY_CONTRACT.md` so future releases explicitly protect both classroom behavior and the proven resilience behavior.
- `release_guard.py` now runs the highest-value workflow/data/privacy tests **plus all three resilience/compatibility regressions** before packaging.
- Keeps the corrected regression assumption that a collapsed Streamlit expander is visually collapsed but is not truly lazy execution.
- The Supabase store, pinned dependency versions, adaptive engine, teacher insight logic, Fact Coach, Weekly Mystery logic, persistent-login token logic, Indiana standards catalog, all SQL, and all five browser components are unchanged from v2.11.0.3.
- `fact_engine.py` changes only the displayed app version to `2.11.2`.
- **No Supabase migration and no new Streamlit Secret.**

## v2.11.0 — Afterschool Teacher Data Update

- Replaces the crowded teacher **Mastery & Focus** entry with **📈 Learning Data**, built around two clear views: **⚡ Fact Fluency** and **📚 Standards Tracker**.
- Fact Fluency translates the existing mastery engine into teacher-friendly language: **Knows It**, **Accurate, Still Slow**, **Needs Help**, and neutral **Still Learning**.
- **Students to Pull** prioritizes repeated independent accuracy misses. Accurate-but-slow facts can trigger a fluency check, but ordinary Building/developing evidence alone no longer labels a student as needing intervention.
- Adds compact class metrics, the most common fact needs, and a one-table all-student snapshot with facts known, slow facts, accuracy needs, evidence coverage, and typical correct-recall time.
- Preserves fact lookup, student lookup, the full 45-fact map, and teacher Focus overrides behind collapsed detail/advanced controls.
- Adds an **Igniter Standards Tracker** using the standards already stored with Warm-Up answers. Teachers can choose a standard previously assessed this school year and see class evidence plus each student's oldest-to-newest correct/incorrect history.
- Student drill-down shows the exact dates, Igniter question number, prompt, and result that make up the standard history. The UI explicitly treats these as **evidence checks**, not automatic mastery of an entire Indiana standard.
- Adds the same true **🔄 Refresh data** control to Teacher → Warm-Up that Teacher → Today uses, preserving the selected class/date while rebuilding the Supabase connection before current results are read.
- Fixes student Igniter feedback after both questions: **✅ Correct!** or **❌ Not quite. The answer is ...** appears before a separate neutral **Igniter complete** transition.
- Warm-Up history reads now page through Supabase results so school-year standards evidence is not silently truncated by a default row limit.
- No schema migration and no new Streamlit Secret. Existing v2.10 Warm-Up tables are sufficient.

## v2.10.1.1 — Student Igniter + Outlook Cleanup

- Pre-login now shows student sign-in plus Teacher access only; Today / Practice appear after student login.
- Removed the premature Daily Challenge heading from the login screen.
- Student-facing Quick Warm-Up is now simply **Igniter Question 1** and **Igniter Question 2**.
- Removed student-facing Spiral/Yesterday labels, progress-bar clutter, and literal Markdown markers.
- Added a clean **Igniter complete → Start Daily 10** transition.
- Simplified the Warm-Up Outlook report to questions, standards, students to pull, missed-both priority group, and unfinished-student check-in.
- Outlook draft URLs now use clean `%20` space encoding instead of `+`.
- No database schema or learning/mastery rules changed.


## v2.10.1 — Indiana Standards + Warm-Up Small Groups + Outlook

- Replaces typed Warm-Up standard codes with a **searchable Indiana Mathematics standards picker for Grades 4–7**, using teacher-friendly summaries of the 2023 content standards. Recently used standards float to the top; **Other / Custom standard** remains available.
- Saves the standard code and description with each Warm-Up response and adds **Grade** to the weekly CSV export.
- Adds automatic **Warm-Up instructional groups** from current real-student results: Priority (missed both), Spiral support, Yesterday support, and a separate Not Finished list.
- **Unfinished students are never counted as incorrect or placed in a reteach group** until they complete both questions.
- Adds a clear instructional suggestion based on the size of each completed-student miss group: quick check-in, small-group reteach, or whole-class clarification.
- Teacher → Today can open **🎯 Show Warm-Up groups & email** using the data already loaded for that class. Teacher → Warm-Up shows the same actionable groups with the deeper standards view.
- Adds private email settings: **one primary school email for every class** plus an optional **class-specific push-in teacher** address.
- **📧 Prepare Warm-Up Email** creates a previewable Microsoft 365/Outlook draft containing completion count, both standards/questions, accuracy, small groups, priority students, and the explicit line **“These students didn't finish, so please check in with them!”**
- Nothing is sent automatically. The app opens the prepared report in Outlook so the teacher can review and press Send.
- Test Student remains excluded from real grouping, email results, class accuracy, and weekly CSV.
- A teacher-only **sandbox Outlook preview** lets you test the email workflow using Test Student; it is marked SANDBOX and addressed only to the primary teacher, never the push-in teacher.
- No database-schema change. If v2.10.0 is already installed, **do not rerun the v2.10 SQL migration**.

## v2.10.0.1 — Warm-Up Store Cache Hotfix

- Makes the cached Supabase store version-aware so a hot deployment cannot reuse a pre-Warm-Up store object.
- Detects and rebuilds a stale store that is missing v2.10 Warm-Up methods.
- Isolates Warm-Up read failures so Teacher → Today remains usable even if the trial feature has a backend problem.
- No new SQL migration.


### v2.10.0 — Quick Warm-Up Trial

- Adds an optional **🧠 Quick Warm-Up** before the Daily 10: exactly two untimed curriculum questions, **Spiral Review** + **Yesterday Check**.
- Each question requires an **Indiana standard code** and can include an optional standard description.
- Trial question types are **Short answer** and **Multiple choice**. Short-answer grading handles numeric equivalents such as `14.40 = 14.4` and `1/2 = 0.5`, plus teacher-entered accepted alternates.
- Warm-Up responses are stored in their own tables and never affect multiplication mastery, Daily accuracy, timer, or Top 10.
- If no Warm-Up is assigned for a class/date, students go straight to the Daily 10.
- Teacher → **🧠 Warm-Up** can plan a class/date, copy the same Warm-Up to all active classes, see question accuracy and students who need another look, and download a Monday–Friday standards-tagged CSV.
- A class/date Warm-Up locks after the first **real** student response so historical standards data always stays attached to the exact questions students saw.
- **🧪 Test Student runs the same Warm-Up first** but remains sandbox-only: it does not lock the plan and is excluded from real class results and weekly CSV exports.
- Teacher → Today shows a compact Warm-Up completion / Spiral accuracy / Yesterday accuracy snapshot when a Warm-Up is assigned.
- Requires the one-time `RUN_THIS_ONCE_IN_SUPABASE_v2_10.sql` migration. No new Streamlit Secret is required.


### v2.9.3.1 — Teacher Refresh Data Hotfix

- Fixes Teacher → Today and projector **🔄 Refresh data** so the button performs a true fresh Supabase read instead of only rerunning the Streamlit page.
- The refresh callback now clears the cached Supabase client **before** Streamlit reruns, so the next top-level store load creates a brand-new connection before any teacher status, progress, streak, or Top 10 queries execute.
- The selected teacher section and selected class remain in place; teacher authentication is not cleared.
- A successful refresh is marked only after the fresh reads complete, with a confirmation toast and updated timestamp.
- The projector Top 10 uses the same hard-refresh behavior.
- No student flow, Daily generator, mastery logic, Mystery/raffle, Fact Coach, roster data, or database schema changed. **No SQL migration and no new Streamlit Secret are required.**

### v2.9.3 — Finish Screen + Completion Language Cleanup

- The finished student screen now follows the clearer order: **YOU'RE DONE → Mystery/raffle → Current Top 10 status → Learning Streak → goodbye**.
- Students who are currently in the Top 10 see their current place again at the end of the full routine. Students outside the Top 10 are congratulated without exposing a lower exact class rank.
- The final Top 10 card reuses the leaderboard snapshot already loaded for the Daily, so this clarity improvement adds **no extra Supabase round trip**.
- The unused **Daily Stars** concept is retired from the student UI. Students now see the meaningful reward already in use: their **Learning Streak**.
- Teacher → Today renames the old Stars column to **Days Completed**, which says exactly what the underlying count means. Historical completion data is preserved; no student records are reset or migrated.
- No Daily generator, mastery logic, Mystery/raffle behavior, Fact Coach, Top 10 privacy, PIN/login, or database schema changed. **No SQL migration and no new Streamlit Secret are required.**

### v2.9.2 — Teacher Usability + Fact Coach Quality Pass

- **Mastery & Focus is rebuilt around four teacher questions:** What Should I Teach?, Who Needs Help?, Look Up a Fact, and Look Up a Student. Only the chosen view is shown; the giant analytics wall is gone.
- The default teaching view ranks practical fact-family targets, suggests a specific fact/strategy to start with, and lists students to pull for a small group.
- The full class fact matrix and class-wide Focus overrides are still available, but now live behind a clearly labeled **advanced** control instead of crowding the normal page.
- **Student Support is rebuilt around four action buttons:** Account & PIN, Fix today's Daily, Adjust Focus Practice, and Move / Status. The old switch/accordion stack and duplicate Bulk Move shortcut are removed from this page; bulk roster tools remain in Classes & Rosters. Permanent deletion is isolated in a clear Danger Zone.
- **Weekly Mystery raffle is now per class.** Each active class gets its own Friday winner, its own eligible pool, its own saved winner, and its own confirmed redraw. Test Student remains excluded.
- Fact Coach wording now says **Start with a fact you know** everywhere; the old “Easy fact first” label is gone.
- The **struggling-student Fact Coach quality pass** slows the teaching beats slightly, makes additive splits explicit (for example, BUILD 7 GROUPS: 5 + 2), and gives direct strategies a visible one-line cue.
- Take-away strategies now name the exact removed quantity and pause long enough to see it. For `9 × 9`, students see `9 × 10 = 90`, tap one full group of 9, then see **YOU TOOK AWAY 9** and `90 − 9` before moving on. ×8 uses the same clarity with two removed groups.
- Fact Coach remains silent, browser-local, and unchanged as mastery evidence: scaffolded anchors and correction retries still do not count as independent mastery.
- No Daily generator, mastery threshold, Top 10 privacy, PIN/login, or database-schema behavior changed. **No SQL migration and no new Streamlit Secret are required.**

### v2.9.1 — Performance + Student Clarity Pass

- **Teacher Dashboard loads only the section you open.** The old Streamlit tab layout executed Today, Rosters, Mastery, Mystery, Student Support, and Test Student on every teacher rerun. v2.9.1 uses one section selector and renders only the chosen area.
- **Teacher → Today reuses one roster snapshot** for Daily status, learning progress, streak/completion summaries, PIN display, and the Top 10. The Top 10 is derived from the already-loaded Daily status instead of running another leaderboard query.
- **Projector Top 10 also reuses the loaded status snapshot** instead of making a second leaderboard round trip.
- **Mastery & Focus loads the class mastery dataset once** and derives summary counts locally instead of fetching summary + detail separately. Manual Focus override database reads now happen only when the teacher opens those controls.
- **Optional My Focus Facts Practice builds an 8-fact local queue.** The app no longer reloads the student's mastery/override profile between every optional Practice fact.
- Removed the growing all-time **saved Practice score query** from the student Practice screen. Practice is cleaner and that database read can no longer get slower as the school year grows.
- The finished-screen **My Growth** data is now genuinely lazy: it loads only when the student turns it on.
- Student navigation is simplified to **Today | Practice**, with Teacher access moved to a smaller secondary button.
- The routine strip now labels the final item **★ Mystery Reward** rather than making it look like required Step 4.
- Daily timing directions and Focus Practice copy are shorter and more fifth-grade friendly. Rare save-error messages now tell students simply to try the step again and show their teacher if it repeats.
- No Daily generator, mastery threshold, Fact Coach strategy, leaderboard privacy, Mystery, raffle, Test Student, login, or database-schema behavior changed. **No SQL migration and no new Streamlit Secret are required.**

### v2.9.0 — Weekly Mystery Raffle + Typo-Friendly Guessing + Test Student Sandbox

- Every real student who solves the Weekly Mystery correctly gets **one equal raffle entry**. Thursday and Friday solvers have the same chance; solving earlier does not create extra entries.
- Teacher → Weekly Mystery now includes a **Weekly Mystery Prize Raffle** with eligible-student list, Friday draw button, saved winner, and confirmed redraw option.
- Mystery guesses now accept capitalization/punctuation differences, existing aliases, and **small plausible spelling mistakes** such as `Abraham Lincon` or `Abraham Linclon`. Short answers remain intentionally strict and unrelated guesses are not fuzzy-matched into a win.
- Correct student Mystery screens explicitly say **You're in this week's prize raffle!**
- Adds Teacher → **🧪 Test Student**, a real Supabase-backed sandbox account that can run the entire student routine repeatedly. It is automatically excluded from real rosters, Top 10, mastery heatmaps, class completion, Mystery stats, mystery locking, and raffle entries.
- **Reset Test Student** wipes only the hidden sandbox account and immediately recreates it for another full end-to-end test.
- Requires the one-time `RUN_THIS_ONCE_IN_SUPABASE_v2_9.sql` migration to add the private `is_test` student flag. No new Streamlit Secret is required.

### v2.8.4 — Clear Take-Away Fact Coach

Take-away lessons now explain the mathematical reason before the tap: start with the ×10 anchor, remove one or two equal groups, and show which original fact remains. The anchor question uses the same orientation students just saw.

### v2.8.3 — Click-to-Remove Fact Coach

- Take-away strategies now include one meaningful student touch before the anchor question.
- ×9 lessons show 10 groups and require the student to tap the 1 group being removed.
- Take-away ×8 lessons require the student to tap both removable groups when the coach selects the 10−2 strategy.
- The anchor keypad stays locked until the required group(s) have been removed.
- The interaction is browser-local, silent, and creates no extra Streamlit/Supabase traffic or mastery evidence.
- Includes the v2.8.2.1 live-day Daily continuity protection and all v2.7 teacher tools.


A classroom-first multiplication fact fluency game built around one short shared competition, a private adaptive learning routine, and a just-for-fun weekly curiosity reward.


### v2.8.1 teacher-dashboard hotfix

- Fixes the **Mastery & Focus → Full Class Fact Map** default filter crash. The previous code treated the label `All facts` as if it were a numeric fact-family label because it ended in the letter `s`.
- Fact-map family filters now use an explicit `2s`–`10s` mapping, so **All facts** and **Focus facts only** can never be parsed as numbers.
- Keeps the complete v2.8.1 Silent Visual Fact Coach and all v2.7 teacher-dashboard features unchanged.
- Code-only hotfix: no Supabase migration and no new Streamlit Secret.

## The daily student routine

Every signed-in student follows the same learning path:

**Optional Quick Warm-Up (when assigned) → Daily 10 → Fix Your Misses → Your Focus Practice → ✅ Day Complete → 🕵️ Weekly Mystery**

### 1. Daily 10

- Every class gets the **same balanced 10 facts in the same order** each day.
- The core is **2s-10s**. Selected days include one 11/12 extension fact; never more than one.
- Fact 1 counts for accuracy but is untimed. Submitting Fact 1 starts the timed sprint for Facts 2-10.
- The timer runs **quietly in the background**. Students do not watch a ticking stopwatch.
- Accuracy ranks first; time breaks ties.
- No right/wrong feedback is shown until the Daily 10 is complete.
- Students answer with a large **phone-style touch number pad**. Digit taps stay entirely in the browser; the physical keyboard remains an optional fallback.
- The class **Top 10 appears immediately after the Daily 10** using the already-cached standings, then gets out of the way during Fix/Focus. It shows **rank + nickname only**. Classmates' accuracy and times stay teacher-only, and lower exact ranks stay private.

### 2. Fix Your Misses

Every missed Daily fact is taught by the **Silent Visual Fact Coach**. The coach is deliberately low-reading and game-like: the **array movement carries the explanation**, while full written strategy text sits behind an optional `Why?` disclosure.

**SEE IT → BREAK IT → YOUR TURN → PUT IT TOGETHER → TRY AGAIN**

For example, a missed `7 × 7` becomes: the whole 7-by-7 array appears first → five rows visibly change to one color and two rows to another → answer the scaffolded anchor `5 × 7 = ?` → watch `2 × 7 = 14` and `35 + 14 = 49` reveal in stages → retry `7 × 7`. The student must finish the correction before moving on.

The coach chooses the relationship that best fits the fact: doubles for ×2/×4, 2+1 for ×3, 5+1 for ×6, 5+2 for ×7, 10−2 for ×8, 10−1 for ×9, and 10+1/10+2 for the occasional 11/12 extension. When a clearer strategy rotates the factors, the coach explicitly teaches the commutative connection before returning to the original orientation.

Fix Your Misses remains one **browser-local guided session**. Array animation, anchor retrieval, combine/reveal, retry attempts, and movement from one missed fact to the next happen on the student's device with no Streamlit page rebuild between stages. When the step is complete, the full item-level evidence is saved to Supabase in one idempotent batch.

The scaffolded anchor answer (for example `5 × 7 = 35`) is **teaching practice, not mastery evidence**. The original Daily miss remains the independent observation, and the final corrected retry remains correction evidence, so Fact Coach cannot artificially raise the student's mastery profile.

### 3. Your Focus Practice

Each student receives **8 personalized retrievals** chosen from the mastery profile attached to that student account.

The app intentionally has **no placement test**. A new student begins with 45 core facts marked as `Learning`, with zero invented evidence. The profile gradually develops from normal Daily Challenge retrievals and first-try answers in assigned Focus Practice.

Focus Practice mixes facts currently needing support, facts still building, a small amount of new evidence gathering, stronger maintenance facts, and spaced repeats of priority facts rather than immediate drilling.

For new/mostly-unknown profiles, exploration is **relationship-aware**: 2s, 5s, and 10s are used as early anchor relationships, then derived facts move forward as their supporting anchors become Building/Fluent. There is still no placement test or giant opening assessment.

If a Focus answer is missed, the same **Interactive Fact Coach** opens immediately inside the browser session. The student sees the relationship, answers one familiar anchor when useful, watches the parts combine, then retries the original fact correctly. The original Focus attempt remains the mastery observation; scaffolded anchor work and corrected retries never masquerade as independent mastery.

Focus Practice still runs the entire 8-retrieval session **browser-locally**. Question-to-question movement, touch-keypad input, Fact Coach animation, anchor prompts, required retries, and spacing all happen without Streamlit reruns. The app sends one detailed evidence batch only after the whole Focus step is complete, preserving first-try accuracy, response time, retries, and teacher/mastery data.

### 4. ✅ Day Complete

The finish screen is intentionally short: **YOU'RE DONE FOR TODAY!**, the three learning steps checked off, the student's Learning Streak, and then the earned Weekly Mystery. Growth and Daily review remain optional instead of crowding the finish. Growth data is loaded only when the student asks to see it.

Completing the full learning routine builds the student's private **Learning Streak** and plain **Days Completed** history. Milestone streak celebrations appear at 3, 5, 10, 20, 30, 50 days and later 50-day milestones. The recognition is for **finishing the learning routine**, not for being fast or being on the leaderboard.

### 5. 🕵️ Weekly Mystery

The Weekly Mystery is a curiosity reward that appears only after the full learning routine is complete.

- One shared mystery is used across every class for the school week.
- **Monday-Friday:** each completed routine earns one clue. Friday now earns a fifth clue before the final guess/reveal.
- Students **cannot guess Monday-Wednesday**.
- **Thursday:** a completed routine unlocks **Guess #1 of 2**.
- **Friday:** a completed routine earns **Clue #5**, unlocks **Guess #2 of 2**, then the answer is revealed.
- Missed clue days are **never backfilled**. A student who completes only Monday, Thursday, and Friday finishes with exactly three clues. Skipped Tuesday/Wednesday clues are never auto-granted.
- Thursday and Friday guesses are separate; an unused Thursday guess does not roll into Friday.
- Mystery solves are private and never affect Daily rank, mastery, completed-day history, or streaks.

The built-in bank contains **80 curated mysteries** across Places, Animals, Foods, Sports, Science & Nature, History & People, Music & Entertainment, and Games/Toys/Objects. It is local to the app, so clue delivery never relies on a live web search.

## Persistent mastery

The core mastery map contains the 45 commutative facts from 2×2 through 10×10. `6×7` and `7×6` are one underlying fact.

Student-facing statuses are intentionally simple:

- 🟢 **Fluent**
- 🟡 **Building**
- 🔴 **Focus**
- ⚪ **Learning**

Accuracy is primary. Response time is used only after accurate retrieval has been established; speed never rescues weak accuracy.

The map is stored in Supabase and follows the student's nickname/PIN account across devices and future logins.

## Optional 30-day remembered sign-in

On an assigned Chromebook or iPad, a student can check **Keep me signed in on this device for 30 days** when entering the nickname + PIN. The browser stores a signed login token, **not the student's PIN**, and the app re-checks the current student record before restoring the account.

- Remembered login expires after 30 days.
- **Sign out** clears it immediately.
- Resetting the student's PIN invalidates the older remembered login.
- Deactivating or deleting the student also prevents restoration.
- Students should leave the box unchecked on a shared device.

## Extra Practice

Practice remains unlimited and lets students choose **My Focus Facts**, Mixed Facts, or 2s through 12s.

Every optional Practice miss now uses the same **Interactive Fact Coach** as the required learning routine, so students get one consistent teaching language everywhere: visual structure → anchor relationship → combine → retry. Extra/manual Practice is saved for history but does not change the formal mastery map; the formal profile remains deliberately based on the common Daily Challenge and assigned Focus Practice.

## Teacher Dashboard

The private Teacher Dashboard supports roughly 90 students across multiple classes.

### Today

The teacher home view is organized around **🟢 Done / 🟡 Working / ⚪ Not started** and now includes a teacher-safe **Live/Final Top 10**. A **🔄 Refresh data** button updates current Supabase results without logging the teacher out or changing the selected class. Teachers can open a large **Display Top 10** view for projection; it contains rank + nickname only, never PINs, scores, or times. Standings automatically become Final when everyone finishes the Daily 10, or the teacher can mark them Final manually.

PINs and routine status remain visible in the private teacher table; accuracy and timing stay in a collapsed teacher-only detail section. **Done** means Daily 10 + Fix Your Misses + Focus Practice are complete; using the Mystery guess is optional.

### Mastery & Focus

The normal Mastery page now asks the teacher one question at a time: **📚 What Should I Teach? · 👥 Who Needs Help? · 🔍 Look Up a Fact · 👤 Look Up a Student**. The default teaching view ranks the most useful fact-family targets, names a specific fact/strategy to start with, and identifies students who may benefit from a small group.

Fact lookup shows one fact's Fluent/Building/Focus/Learning counts, independent accuracy, strategy connection, and students to pull. Student lookup shows the student's current status counts, most important Focus facts, today's Focus plan, recent momentum, and optional evidence details. **⚪ Learning** remains neutral: it means the app does not yet have enough independent evidence.

The filterable 45-fact class map and class/global Focus overrides remain available under **Show advanced fact map & class-wide Focus controls**, so the data is preserved without making the everyday page hard to use. Student-specific Focus overrides remain in Student Support.

Override priority remains:

**Student override → Class override → All-student override → Automatic personalization**

### Weekly Mystery

Teachers can preview the current week's answer and all five clues, see unlock/guess/solve counts, and swap the current mystery only before the first student earns a clue. Once the first clue is earned, the current week remains locked.

Correct solvers receive one equal entry in **their own class's Friday prize raffle**. Teacher → Weekly Mystery shows one raffle card per active class, so Block 1, Block 2, Block 3, and any future class each draw and save an independent winner. Thursday and Friday solvers remain equally weighted, typo-tolerant accepted answers still apply, and the hidden Test Student is excluded.

A **Next Week's Mystery** planning area lets the teacher preview the automatic selection, choose another curated mystery, or customize the answer, all five daily clues, learning paragraph, fun fact, and accepted aliases before Monday. The saved plan uses the existing private `app_settings` table and automatically becomes the active mystery when the new school week begins; it never changes the current week.

### Classes & Rosters / Student Support

Every existing teacher function remains available. The dashboard uses a section selector so only **Today, Classes & Rosters, Mastery & Focus, Weekly Mystery, Student Support, or Test Student** loads at a time. Whole-class setup, bulk move, bulk delete, and roster management stay in Classes & Rosters.

Student Support now starts with one selected student and four clear actions: **Account & PIN, Fix today's Daily, Adjust Focus Practice, and Move / Status**. Permanent deletion is separated into a Danger Zone instead of appearing beside routine classroom tools.

## Daily fact generator

The shared Daily generator remains versioned as `TDFC-DAILY-v1`, so the previously audited Daily sequence does not change in v2.9.2.

Each Daily contains 10 unique underlying multiplication facts. Commutative mirrors cannot both appear. Normal core days contain 3 easier, 4 medium, and 3 harder facts. On selected extension days, one harder slot becomes one 11/12 fact.

## Data and privacy

- Student accounts use teacher-assigned nicknames and 4-digit classroom PINs.
- Optional 30-day remembered sign-in stores only a server-signed browser token; the PIN itself is not stored in browser local storage.
- Teacher-only views retain a readable copy of classroom PINs while authentication still verifies the salted scrypt hash.
- Student-facing pages never show classmates' PINs.
- No student email, school ID, or legal name is required.
- Supabase Row Level Security is enabled on all app tables with no public browser policies.
- The Streamlit server uses the private `SUPABASE_SECRET_KEY`; students never receive database credentials.
- Weekly guesses are private to the student and teacher data layer; there is no class guessing leaderboard.
- There is intentionally **no social sharing feature**.

## Streamlit Secrets

```toml
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "YOUR-SERVER-SECRET-KEY"
TEACHER_PASSWORD = "CHOOSE-A-PRIVATE-TEACHER-PASSWORD"
```

## Updating an existing installation

**Updating from v2.8.x:** run `RUN_THIS_ONCE_IN_SUPABASE_v2_9.sql` once in a **new Supabase SQL query**, then upload every file/folder in `UPLOAD_TO_GITHUB`. This adds only the hidden Test Student flag; the raffle uses the existing private `app_settings` table. No new Streamlit Secret is required.

**Updating from v2.8.0:** v2.8.1 is **code only**. There is no new Supabase SQL migration and no new Streamlit Secret. Upload every file/folder in `UPLOAD_TO_GITHUB` and let Streamlit redeploy. The existing v2.6 browser-batch schema already stores every independent/correction event Fact Coach needs.

**Updating from v2.7.0:** upload the v2.8.1 app files; there is no additional SQL migration beyond the migrations your installation has already completed.

**Updating from v2.5.x or earlier:** first apply any migration your installation has not yet run (including `RUN_THIS_ONCE_IN_SUPABASE_v2_6.sql` for Guided Practice), then upload the v2.8.1 app files. Do **not** rerun migrations you already completed.

Make sure all five browser-component folders are present in GitHub:

- `daily_sprint_component/index.html`
- `guided_practice_component/index.html`
- `answer_pad_component/index.html`
- `persistent_login_component/index.html`
- `pin_entry_component/index.html`

`SUPABASE_SCHEMA.sql` represents the current full schema for a brand-new installation.

## Version notes

### v2.8.1 — Silent Visual Fact Coach

- Reworks the Interactive Fact Coach for students who benefit from **less reading and more visual movement**.
- Makes the array itself carry the explanation: the whole array appears first, then groups visibly change color or fade to show the relationship.
- Uses short game-like prompts: **SEE IT → BREAK IT → YOUR TURN → PUT IT TOGETHER → TRY AGAIN**.
- Keeps the full written strategy behind an optional **Why?** disclosure instead of requiring students to read it before progressing.
- Stops rebuilding the coaching card on every keypad digit, so animations can finish uninterrupted and touch input stays browser-fast.
- Adds staged visual equation reveals and silent visual celebration for correct anchor facts and final combinations.
- Keeps all Fact Coach interactions **silent**—no sound effects or audio cues in a classroom.
- Preserves all v2.8 mastery/data rules: scaffolded anchor answers remain coached practice only; independent Daily/Focus evidence and corrected retries stay distinct.
- No Supabase migration or new Streamlit secret is required.

### v2.8.0 — Interactive Fact Coach

- Adds one reusable **Interactive Fact Coach** across Fix Your Misses, assigned Focus Practice, and optional Practice.
- Standardizes the corrective routine as **See it → Connect it → Solve it → Retry it** instead of a passive static explanation.
- Animates multiplication arrays quickly to emphasize equal-group structure rather than slow counting.
- Uses mathematically matched relationships: ×2 doubles; ×3 uses 2+1; ×4 doubles a ×2 anchor; ×6 uses 5+1; ×7 uses 5+2; ×8 uses 10−2; ×9 uses 10−1; 11/12 extensions use 10+1/10+2.
- `7 × 7` now specifically asks the student to retrieve `5 × 7 = 35`, then shows `2 × 7 = 14`, combines `35 + 14 = 49`, and requires a final `7 × 7` retry.
- When the clearest model rotates the factors (for example `7 × 4` → `4 × 7`), the coach explicitly names the commutative relationship and returns the final retry to the student's original fact.
- Scaffolded anchor answers remain **coached practice only** and are never inserted into mastery evidence; Daily/Focus first attempts remain the independent data used by the adaptive profile.
- Keeps the entire coach browser-local until the guided step ends, preserving v2.6 classroom-speed and no-page-jump behavior.
- Aligns teacher-facing strategy connections with the same Fact Coach relationships students are actually taught.
- Extends the same coach to optional Practice without letting optional Practice alter formal mastery.
- No Supabase migration or new Streamlit secret is required when updating from v2.7.0.

### v2.7.0 — Teacher Intelligence & Weekly Planning

- Adds a real Friday **Clue #5**. Students earn one clue for each completed Monday-Friday routine; skipped days are never backfilled. Friday's earned clue appears before Guess #2/reveal.
- Adds **🔄 Refresh data** to the Teacher Today view and projector view so teachers can pull fresh class status without losing the authenticated Streamlit session.
- Adds teacher **Live Top 10 / Final Top 10** with rank + nickname only, manual Final control, automatic Final when the class has finished the Daily 10, and a large student-safe **Display Top 10** presentation view.
- Labels the student post-Daily board **Current Top 10** and explicitly explains that standings can change as classmates finish.
- Rebuilds **Mastery & Focus** around instructional decisions: evidence coverage, teaching opportunities, support needs, student momentum, a filterable class fact matrix, fact-level evidence/strategy details, quick Focus-family assignment, and richer individual student explanations.
- Adds a teacher-facing explanation of how Daily retrieval, correction, Focus Practice, accuracy, timing, and mastery statuses work; no placement test is introduced.
- Adds **Next Week's Mystery** planning: preview the automatic choice, switch to another curated mystery, or customize the answer, all five clues, learning paragraph, fun fact, and aliases before Monday. Current-week locks remain protected.
- Renames the Teacher Dashboard **Lock** button to **Log out**.
- Uses the existing `app_settings` table for teacher planning/final-board settings, so **no Supabase migration is required** from v2.6.x.


### v2.6.2 — Final Screen Polish

- Removes the duplicate Daily/Fix/Focus/Mystery progress strip on the completed-day screen.
- Keeps the Top 10 where it belongs: immediately after the Daily 10 rather than re-adding it to the final screen.
- Collapses the repeated Mystery headings into one clear **Today’s Mystery Reward** section.
- Code-only update: no Supabase migration or new Streamlit secret.

### v2.6.1 — Finished Screen Growth Hotfix

- Restores the student **🌱 My Growth** card that was accidentally omitted from the v2.6 app file.
- Prevents a missing display helper or other programming error from being mislabeled as **“The classroom connection is busy.”**
- The yellow classroom-busy message is now reserved for real transient HTTP/connection failures such as read errors, timeouts, resets, or dropped connections.
- Unexpected finished-screen display errors use separate wording while still protecting the already-saved Daily result.
- No learning logic, Guided Practice behavior, Mystery rules, leaderboard rules, Teacher Tools, or database schema changes.
- No Supabase migration or new Streamlit secret is required when updating from v2.6.

### v2.6 — Guided Practice Performance Pass

- Rebuilds **Step 2: Fix Your Misses** and **Step 3: Your Focus Practice** as one browser-local guided-practice engine.
- Removes the Streamlit rerun/page-jump between every Step 2/3 answer; students stay in one smooth session just like the Daily 10.
- Keeps the research-aligned learning loop intact: retrieval first, immediate correction after a miss, array/meaning, derived-fact strategy, and required correct retry.
- Preserves teacher evidence for each fact: first answer, correctness, response time, retry/correction rows, and persistent mastery inputs.
- Saves the completed guided session as one idempotent Supabase batch instead of one network trip per question.
- Uses browser session storage to preserve an in-progress guided session through an iframe refresh and deterministic event IDs to make network retries safe.
- Adds `RUN_THIS_ONCE_IN_SUPABASE_v2_6.sql`, which adds the private event-id field used for idempotent batch saving.
- Replaces Abraham Lincoln's Mystery learning paragraph with the teacher-approved kid-friendly version about his log-cabin birth, limited formal schooling, love of reading, and “Honest Abe” nickname.
- Does not change Daily 10 generation, adaptive Focus selection, mastery thresholds, leaderboard rules, Teacher Tools, completed-day history, streaks, or Mystery clue/guess rules.

### v2.5.1.3 — PIN Check/Login Hotfix

- Makes the green ✓ on the student PIN keypad the **actual sign-in control** instead of a disabled status indicator.
- Student flow is now: choose class → enter nickname → choose 30-day option if wanted → enter four PIN digits → tap ✓ → sign in.
- Removes the separate Streamlit **Sign in** button so there is only one obvious login action.
- PIN digits remain browser-local until ✓ is tapped; no Supabase or Streamlit work occurs per digit.
- Wrong nickname/PIN clears the PIN pad and gives the student a clean retry.
- Keeps the no-HTML-input PIN design, so iPadOS strong-password suggestions remain suppressed.
- No database migration or new Streamlit secret is required.


### v2.5.1.2 — Student PIN State Persistence Hotfix

- Fixes the classroom PIN pad resetting after every digit on Streamlit rerenders.
- Partial PIN digits now remain entirely browser-local until all four digits are entered.
- Repeated Streamlit render messages can no longer overwrite an in-progress PIN with the still-empty parent value.
- Keeps the no-password-field design, so iPadOS does not offer a generated strong password.

### v2.5.1.1 — Student PIN Tap Hotfix

- Fixes a student-login regression where the custom classroom PIN keypad rendered but number taps did not reliably update the four PIN dots.
- The PIN component now renders its buttons once and uses one permanent delegated click handler instead of rebuilding the keypad DOM after every digit.
- Keeps the iPad-friendly design: no browser password field, no strong-password suggestion, masked PIN dots, physical-keyboard fallback, and no Supabase/Streamlit work while individual digits are tapped.
- No Supabase migration or new Streamlit secret is required.

### v2.5.1 — Classroom iPad Hotfix
- The shared answer keypad now measures its real browser height and resizes automatically, preventing the bottom row from being clipped on iPads, Chromebooks, and desktop browsers.
- Student PIN entry is now a custom four-digit masked touch pad with no HTML password/input field, preventing iPad strong-password suggestions while keeping the teacher password protected.
- Correct Weekly Mystery guesses now trigger a one-time celebration with balloons, a large solve banner, a solve title, and a short learning section.
- Every one of the 80 curated mysteries now includes a kid-friendly learning paragraph plus its existing fun fact.
- Abraham Lincoln's reveal received a dedicated learning paragraph (later revised in v2.6 to the teacher-approved kid-friendly wording).
- No database migration is required when updating from v2.5.0.

### v2.5.0 — Student Experience Pass

- Replaces multiplication answer typing with a large phone-style touch number pad in Daily 10, Fix Your Misses, assigned Focus Practice, and optional Practice.
- Number-pad digit taps are browser-local; they do not rerun Streamlit or call Supabase. Only ✓ submits an answer. Physical keyboard entry remains supported as a fallback.
- Restores the class Top 10 immediately after the Daily 10 using the cached leaderboard snapshot; it appears once and does not reload during every Fix/Focus rerun.
- Keeps student Top 10 privacy at **rank + nickname only**; scores/times remain teacher-only.
- Simplifies Day Complete so the finish message + Mystery reward dominate, with Growth and Daily Review collapsed as optional detail.
- Changes Weekly Mystery to the classroom rule: earned clues Monday-Thursday, no guessing Monday-Wednesday, Guess #1 Thursday, Guess #2 Friday, then reveal.
- Skipped clue days are never backfilled on Thursday or Friday.
- Adds the one-time `RUN_THIS_ONCE_IN_SUPABASE_v2_5.sql` migration so Thursday and Friday guesses have separate persistent database slots.
- Preserves adaptive mastery, no-placement-test learning, classroom-load retries/batching, fast Focus Practice, teacher tools, 30-day login, completed-day history, and school-day streaks.

### v2.4.0 — 30-Day Remembered Student Login

- Adds an optional **Keep me signed in on this device for 30 days** checkbox to student login.
- Uses a signed browser token rather than storing the 4-digit PIN itself.
- Automatically restores the student's current nickname/class on the same device while the token is valid.
- **Sign out** clears the remembered login immediately.
- A teacher PIN reset invalidates the older remembered login; deleted/deactivated accounts also cannot restore.
- Intended for assigned student devices; the login screen explicitly says to leave the box unchecked on shared devices.
- Preserves v2.3 classroom clarity, v2.2.6 Focus speed improvements, and v2.2.5 classroom-load reliability work.
- Code-only update: no database migration and no new Streamlit secret.

### v2.3.0 — Classroom Clarity Pass

- Adds a persistent four-part student progress strip: **Daily 10 → Fix Misses → Focus → Mystery reward**.
- Replaces the subtle finish state with an unmistakable **YOU'RE DONE FOR TODAY!** screen and an explicit **All done. See you next Challenge day!** ending.
- Makes it clear that the Mystery clue is **earned after the learning work** and that using the one weekly guess is optional.
- Adds an explicit **I'm waiting for another clue · Done for today ✓** choice so students never wonder whether they have another required step.
- Hardens Top 10 privacy: after Supabase performs the private accuracy/time ranking, the student-side leaderboard context discards all score/time fields and keeps only **student ID + nickname + rank**.
- Reorganizes Teacher Mode into **Today, Classes & Rosters, Mastery & Focus, Weekly Mystery, Student Support** without removing any teacher function.
- Today now emphasizes **Done / Working / Not started**; teacher-only accuracy and timing are moved into a secondary detail section.
- Classes & Rosters groups class creation, student creation/PINs, roster exports, moves, bulk delete, and clear-roster tools.
- Student Support groups one-student nickname/PIN, Daily reset, Focus override, move/status, and permanent-delete tools.
- Preserves the v2.2.5 classroom-load retry/batching work and v2.2.6 Focus Practice performance improvements.
- Code-only update: no database migration or new Streamlit secret.

### v2.2.6 — Focus Practice Speed Hotfix

- Confirms the classroom slowdown was partly caused by the Top 10 being reloaded on every Streamlit rerun during Focus Practice. The leaderboard snapshot is now loaded once and reused until Day Complete.
- Focus Practice activity rows and teacher-focus settings are cached for the current student session instead of being re-read after every answer.
- Reuses the already-loaded learning-progress record when building the Focus plan.
- First-try Focus answers now save with one normal insert instead of a pre-read plus insert; duplicate submissions still fall back safely to the existing stored answer.
- Focus mastery evidence is accumulated from the eight stored first attempts and applied in one idempotent batch at the end of Focus Practice instead of two mastery requests after every answer.
- The learning model, 8-item Focus plan, correction behavior, Daily ranking, Weekly Mystery, and Teacher Tools are unchanged.
- Code-only update: no database migration or new Streamlit secret.

### v2.2.5 — Classroom Load Reliability Hotfix

- Adds automatic retry/backoff for transient Supabase/httpx read failures such as the classroom `httpx.ReadError` seen when many students finish together.
- Batches the 10 Daily mastery updates into roughly **2 database requests instead of about 20 per student** while preserving the same mastery math.
- Reuses one leaderboard snapshot on the completed-Daily screen instead of repeatedly loading the same class data in a single rerun.
- If the database is briefly busy after a completed Daily, students now see a friendly **Try again** message rather than a giant Streamlit traceback; completed Daily work does not need to be repeated.
- Keeps v2.2.4 student leaderboard privacy intact.
- Teacher Tools UI is intentionally untouched; its cleanup remains deferred until after classroom feedback.
- Code-only update: no database migration or new Streamlit secret.

### v2.2.4 — Student Leaderboard Privacy Hotfix

- Student Top 10 now shows **rank + nickname only**.
- Classmates' accuracy and timed-sprint values are no longer visible to students.
- Student result summary no longer displays the timed sprint or a numeric accuracy score; it keeps Top 10 status and the instructional **Facts to Fix** count.
- Accuracy and timing remain fully available in the Teacher Dashboard and still determine ranking privately: accuracy first, time as the tiebreaker.
- Teacher UI layout is intentionally unchanged in this hotfix; the planned Teacher Tools cleanup remains deferred until after classroom feedback.
- Code-only update: no database migration or new Streamlit secret.

### v2.2.3 — Fast Roster Delete Hotfix

- **Delete selected student(s)** now sends one true bulk database delete instead of deleting each selected student one at a time.
- Adds **Clear this entire roster** under each class for fast cleanup when a whole roster was entered by mistake.
- Whole-roster clear keeps the class itself but permanently removes every student in it and their linked history.
- Whole-roster clear requires typing `DELETE <class name>` before the button enables.
- Single-student permanent delete was also reduced to one database request.
- Code-only update: no database migration or new Streamlit secret.

### v2.2.2 — Visible Roster Management Hotfix

- Adds an obvious **Roster Management** section directly under each class roster in **Classes & Students**.
- Select one or many students at once.
- **Move selected student(s)** preserves PIN, mastery, completed-day history, streak, Daily history, Focus work, and Mystery history.
- **Delete selected student(s)** supports permanent bulk cleanup with an explicit confirmation checkbox.
- Existing individual Student Tools remain available.
- Code-only update: no database migration or new Streamlit secret.

### v2.2.0 — Weekly Mystery

Adds the post-routine **Weekly Mystery** motivation loop. Monday-Thursday full completion unlocks clues, each student has one guess for the entire week, and Friday provides the final guess/reveal. Includes an 80-mystery local bank, private solve stats, and a Teacher Dashboard preview/replacement control that locks after the first clue is earned.

The multiplication learning model, Daily generator, accuracy-first Top 10, Focus personalization, mastery evidence, completed-day history, streaks, and visible teacher PIN system are unchanged.

### v2.1.0 — Research Alignment + Teacher PIN Visibility

Tightened early adaptive exploration around 2s/5s/10s anchor relationships and retained teacher-readable classroom PINs in teacher-only views.

### v2.0.0 — Adaptive Learning Routine

Added **Daily 10 → Fix Your Misses → Your Focus Practice → Done**, persistent individualized mastery with no placement test, eight-fact adaptive Focus sessions, required correction retries, hidden competition timing, completed-day history and school-day Learning Streaks, private growth views, teacher heatmaps, and Focus overrides.

### v1.0.0 — Full classroom beta

Initial shared Daily 10, class Top 10, student nickname/PIN accounts, visual Practice, teacher roster/dashboard tools, and Supabase persistence.

### v2.12.0 Hotfix 3 — Top 10 chime
The separate `AWTRIX_FactTop10.berry` script now adds a short three-note RTTTL chime (`c,e,g`) when either an automatic or teacher-manual Top 10 notification begins. The melody plays once per notification; it does not loop or repeat before each student. AWTRIX global Sound must be enabled. The Class Schedule script is unchanged.

