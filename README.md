# Teal's Daily Fact Challenge

A classroom-first multiplication fact fluency game built around one short shared competition, a private adaptive learning routine, and a just-for-fun weekly curiosity reward.

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
- Students see only their own class **Top 10**, with **rank + nickname only**. Classmates' accuracy and times stay teacher-only, and lower exact ranks stay private.

### 2. Fix Your Misses

Every missed Daily fact is immediately taught with the correct equation, a multiplication array, repeated-addition meaning, a derived-fact strategy, and a required correct retry before moving on.

A correction retry is teaching—not a new mastery observation—so it does not artificially raise the student's profile.

### 3. Your Focus Practice

Each student receives **8 personalized retrievals** chosen from the mastery profile attached to that student account.

The app intentionally has **no placement test**. A new student begins with 45 core facts marked as `Learning`, with zero invented evidence. The profile gradually develops from normal Daily Challenge retrievals and first-try answers in assigned Focus Practice.

Focus Practice mixes facts currently needing support, facts still building, a small amount of new evidence gathering, stronger maintenance facts, and spaced repeats of priority facts rather than immediate drilling.

For new/mostly-unknown profiles, exploration is **relationship-aware**: 2s, 5s, and 10s are used as early anchor relationships, then derived facts move forward as their supporting anchors become Building/Fluent. There is still no placement test or giant opening assessment.

If a Focus answer is missed, the student sees visual/strategy teaching and must retry correctly. The retry teaches the fact but does not count as independent retrieval evidence.

### 4. ⭐ Day Complete

The finish screen now says **YOU'RE DONE FOR TODAY!** and checks off Daily 10, Fix Your Misses, and Focus Practice before presenting the Weekly Mystery as the earned reward. Completing the full learning routine earns one **Daily Star**, progress toward a private **Learning Streak**, and milestone celebrations at 3, 5, 10, 20, 30, 50 days and later 50-day milestones.

The reward is for **finishing the learning routine**, not for being fast or being on the leaderboard.

### 5. 🕵️ Weekly Mystery

The Weekly Mystery is a curiosity reward that appears only after the full learning routine is complete.

- One shared mystery is used across every class for the school week.
- Monday-Thursday: each completed routine earns the **next clue in order**.
- Students have **one guess for the entire week**. They can use it early or save it.
- A missed school day simply means the student has fewer early clues; clue numbering never has holes.
- Friday: completing the routine shows the full four-clue set, gives an unused guess one final chance, and then reveals the answer.
- Correct early guesses earn a private solve title such as **One-Clue Wonder** or **Sharp Detective**.
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

## Extra Practice

Practice remains unlimited and lets students choose **My Focus Facts**, Mixed Facts, or 2s through 12s.

Every Practice miss uses **teach → retry correctly → next**, with an array and derived-fact strategy. Extra/manual Practice is saved for history but does not currently change the formal mastery map; the formal profile is deliberately based on the common Daily Challenge and assigned Focus Practice.

## Teacher Dashboard

The private Teacher Dashboard supports roughly 90 students across multiple classes.

### Today

The teacher home view is organized around **🟢 Done / 🟡 Working / ⚪ Not started**. PINs and routine status stay visible in the main table; accuracy and timing are tucked into a teacher-only detail section. **Done** means Daily 10 + Fix Your Misses + Focus Practice are complete; using the Mystery guess is optional.

### Mastery & Focus

Teachers can see a full 45-fact class heatmap, facts showing the greatest observed need, an individual student's mastery map, and optional Focus overrides.

Override priority is:

**Student override → Class override → All-student override → Automatic personalization**

### Weekly Mystery

Teachers can preview the week's answer and all four clues, see unlock/guess/solve counts, and press **Pick Another Mystery** before any student earns a clue. Once the first clue is earned, the mystery locks for the week so students cannot receive a changed answer midstream.

### Classes & Rosters / Student Support

Every existing teacher function remains available, but the dashboard is reorganized into **Today → Classes & Rosters → Mastery & Focus → Weekly Mystery → Student Support**. Whole-class setup and roster management live together; one-student troubleshooting groups nickname/PIN, Daily reset, Focus override, move/status, and permanent-delete tools into clearly labeled sections.

## Daily fact generator

The shared Daily generator remains versioned as `TDFC-DAILY-v1`, so the previously audited Daily sequence does not change in v2.3.0.

Each Daily contains 10 unique underlying multiplication facts. Commutative mirrors cannot both appear. Normal core days contain 3 easier, 4 medium, and 3 harder facts. On selected extension days, one harder slot becomes one 11/12 fact.

## Data and privacy

- Student accounts use teacher-assigned nicknames and 4-digit classroom PINs.
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

**Current live v2.2 installation:** v2.3.0 is a code-only classroom clarity update. **No Supabase SQL is required.** Upload every file/folder in `UPLOAD_TO_GITHUB` to the existing GitHub repo and let Streamlit redeploy.

**If coming from v2.1:** run `RUN_THIS_ONCE_IN_SUPABASE_v2_2.sql` first, then upload the v2.3.0 app files.

**If already on v2.0 but not v2.1:** run `RUN_THIS_ONCE_IN_SUPABASE_v2_1.sql`, then `RUN_THIS_ONCE_IN_SUPABASE_v2_2.sql`.

**If still on v1:** the packaged `RUN_THIS_ONCE_IN_SUPABASE_v2.sql` is the combined migration and includes adaptive learning, teacher-visible PINs, and Weekly Mystery.

Do not rerun `SUPABASE_SCHEMA.sql` on an existing project. It is the full schema for a brand-new installation.

Make sure `daily_sprint_component/index.html` remains present in GitHub.

## Version notes

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
