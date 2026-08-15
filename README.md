# Teal's Daily Fact Challenge

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

**Daily 10 → Fix Your Misses → Your Focus Practice → ⭐ Day Complete → 🕵️ Weekly Mystery**

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

If a Focus answer is missed, the same **Interactive Fact Coach** opens immediately inside the browser session. The student sees the relationship, answers one easier anchor when useful, watches the parts combine, then retries the original fact correctly. The original Focus attempt remains the mastery observation; scaffolded anchor work and corrected retries never masquerade as independent mastery.

Focus Practice still runs the entire 8-retrieval session **browser-locally**. Question-to-question movement, touch-keypad input, Fact Coach animation, anchor prompts, required retries, and spacing all happen without Streamlit reruns. The app sends one detailed evidence batch only after the whole Focus step is complete, preserving first-try accuracy, response time, retries, and teacher/mastery data.

### 4. ⭐ Day Complete

The finish screen is intentionally short: **YOU'RE DONE FOR TODAY!**, the three learning steps checked off, the student's Star/streak, and then the earned Weekly Mystery. Growth and Daily review remain available in collapsed optional sections instead of crowding the finish.

Completing the full learning routine earns one **Daily Star**, progress toward a private **Learning Streak**, and milestone celebrations at 3, 5, 10, 20, 30, 50 days and later 50-day milestones. The reward is for **finishing the learning routine**, not for being fast or being on the leaderboard.

### 5. 🕵️ Weekly Mystery

The Weekly Mystery is a curiosity reward that appears only after the full learning routine is complete.

- One shared mystery is used across every class for the school week.
- **Monday-Friday:** each completed routine earns one clue. Friday now earns a fifth clue before the final guess/reveal.
- Students **cannot guess Monday-Wednesday**.
- **Thursday:** a completed routine unlocks **Guess #1 of 2**.
- **Friday:** a completed routine earns **Clue #5**, unlocks **Guess #2 of 2**, then the answer is revealed.
- Missed clue days are **never backfilled**. A student who completes only Monday, Thursday, and Friday finishes with exactly three clues. Skipped Tuesday/Wednesday clues are never auto-granted.
- Thursday and Friday guesses are separate; an unused Thursday guess does not roll into Friday.
- Mystery solves are private and never affect Daily rank, mastery, Stars, or streaks.

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

The Mastery page is organized around teacher decisions rather than raw counts. It includes **evidence coverage**, **Best Teaching Opportunities**, **Students Who May Need Support**, **Students Showing Momentum**, a filterable 45-fact class matrix, detailed fact inspection, teaching-strategy connections, quick family Focus assignment, and a richer individual-student explanation of why a fact is Learning/Focus/Building/Fluent.

The page explicitly distinguishes observed evidence from **⚪ Learning/unknown**, so early incomplete data is not mistaken for lack of knowledge. A collapsed **How the app teaches & uses data** section explains the Daily → correction → adaptive retrieval model and the exact mastery thresholds.

Override priority remains:

**Student override → Class override → All-student override → Automatic personalization**

### Weekly Mystery

Teachers can preview the current week's answer and all five clues, see unlock/guess/solve counts, and swap the current mystery only before the first student earns a clue. Once the first clue is earned, the current week remains locked.

A new **Next Week's Mystery** planning area lets the teacher preview the automatic selection, choose another curated mystery, or customize the answer, all five daily clues, learning paragraph, fun fact, and accepted aliases before Monday. The saved plan uses the existing private `app_settings` table and automatically becomes the active mystery when the new school week begins; it never changes the current week.

### Classes & Rosters / Student Support

Every existing teacher function remains available, but the dashboard is reorganized into **Today → Classes & Rosters → Mastery & Focus → Weekly Mystery → Student Support**. Whole-class setup and roster management live together; one-student troubleshooting groups nickname/PIN, Daily reset, Focus override, move/status, and permanent-delete tools into clearly labeled sections.

## Daily fact generator

The shared Daily generator remains versioned as `TDFC-DAILY-v1`, so the previously audited Daily sequence does not change in v2.8.

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
- Does not change Daily 10 generation, adaptive Focus selection, mastery thresholds, leaderboard rules, Teacher Tools, Stars, streaks, or Mystery clue/guess rules.

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
- Preserves adaptive mastery, no-placement-test learning, classroom-load retries/batching, fast Focus Practice, teacher tools, 30-day login, Stars, and school-day streaks.

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
- **Move selected student(s)** preserves PIN, mastery, Stars, streak, Daily history, Focus work, and Mystery history.
- **Delete selected student(s)** supports permanent bulk cleanup with an explicit confirmation checkbox.
- Existing individual Student Tools remain available.
- Code-only update: no database migration or new Streamlit secret.

### v2.2.0 — Weekly Mystery

Adds the post-routine **Weekly Mystery** motivation loop. Monday-Thursday full completion unlocks clues, each student has one guess for the entire week, and Friday provides the final guess/reveal. Includes an 80-mystery local bank, private solve stats, and a Teacher Dashboard preview/replacement control that locks after the first clue is earned.

The multiplication learning model, Daily generator, accuracy-first Top 10, Focus personalization, mastery evidence, Stars, streaks, and visible teacher PIN system are unchanged.

### v2.1.0 — Research Alignment + Teacher PIN Visibility

Tightened early adaptive exploration around 2s/5s/10s anchor relationships and retained teacher-readable classroom PINs in teacher-only views.

### v2.0.0 — Adaptive Learning Routine

Added **Daily 10 → Fix Your Misses → Your Focus Practice → Done**, persistent individualized mastery with no placement test, eight-fact adaptive Focus sessions, required correction retries, hidden competition timing, Daily Stars and school-day Learning Streaks, private growth views, teacher heatmaps, and Focus overrides.

### v1.0.0 — Full classroom beta

Initial shared Daily 10, class Top 10, student nickname/PIN accounts, visual Practice, teacher roster/dashboard tools, and Supabase persistence.
