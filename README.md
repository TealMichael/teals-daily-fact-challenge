# Teal's Daily Fact Challenge

A classroom-first multiplication fact fluency game built around one short shared competition and a private adaptive learning routine.

## The daily student routine

Every signed-in student follows the same four-part path:

**Daily 10 → Fix Your Misses → Your Focus Practice → ⭐ Done**

### 1. Daily 10

- Every class gets the **same balanced 10 facts in the same order** each day.
- The core is **2s-10s**. Selected days include one 11/12 extension fact; never more than one.
- Fact 1 counts for accuracy but is untimed. Submitting Fact 1 starts the timed sprint for Facts 2-10.
- The timer runs **quietly in the background**. Students do not watch a ticking stopwatch.
- Accuracy ranks first; time breaks ties.
- No right/wrong feedback is shown until the Daily 10 is complete.
- Students see only their own class **Top 10**. Lower exact ranks stay private.

### 2. Fix Your Misses

Every missed Daily fact is immediately taught with:

- the correct equation;
- a multiplication array;
- repeated-addition meaning;
- a derived-fact strategy;
- a required correct retry before moving on.

A correction retry is teaching—not a new mastery observation—so it does not artificially raise the student's profile.

### 3. Your Focus Practice

Each student receives **8 personalized retrievals** chosen from the mastery profile that belongs to that student account.

The app intentionally has **no placement test**. A new student begins with 45 core facts marked as `Learning`, with zero invented evidence. The profile gradually develops from normal Daily Challenge retrievals and first-try answers in assigned Focus Practice.

Focus Practice mixes:

- facts currently needing support;
- facts that are still building;
- a small amount of new/unknown evidence gathering;
- maintenance facts that are already stronger;
- spaced repeats of priority facts rather than immediate drilling of the same fact.

For brand-new/mostly-unknown profiles, v2.1 makes that exploration **relationship-aware**: 2s, 5s, and 10s are used as early anchor relationships, then unknown derived facts move forward as their supporting anchors become Building/Fluent. This happens gradually through normal use; there is still no placement test or giant opening assessment.

If a Focus answer is missed, the student sees the visual/strategy teaching and must retry correctly. The retry teaches the fact but does not count as independent retrieval evidence.

### 4. ⭐ Day Complete

Completing the full routine earns:

- one **Daily Star**;
- progress toward a private **Learning Streak**;
- milestone celebrations at 3, 5, 10, 20, 30, 50 days and later 50-day milestones.

The reward is for **finishing the learning routine**, not for being fast or being on the leaderboard.

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

Practice remains unlimited and lets students choose:

- 🎯 **My Focus Facts** (signed-in students)
- Mixed Facts
- 2s through 12s

Every Practice miss uses **teach → retry correctly → next**, with an array and derived-fact strategy. The teaching library includes doubles, double-twice, 5-groups plus more, 10-groups minus groups, and decomposition strategies so facts are connected to relationships instead of treated as isolated memorization.

Extra/manual Practice is saved for history but does not currently change the formal mastery map. The formal profile is deliberately based on the common Daily Challenge and assigned Focus Practice so the evidence stays consistent.

## Teacher Dashboard

The private Teacher Dashboard supports roughly 90 students across multiple classes.

### Today

Teachers can see:

- Daily 10 completion;
- full learning-routine completion;
- accuracy and timed-sprint results;
- private streak and total-star information;
- every student's current routine step;
- the student-visible class Top 10.

### Mastery & Focus

Teachers can see:

- a full 45-fact class heatmap;
- the facts currently showing the greatest observed need;
- an individual student's private mastery map;
- an optional Focus override for everybody;
- an optional class Focus override.

Override priority is:

**Student override → Class override → All-student override → Automatic personalization**

### Student Tools

Teachers can:

- see each student's classroom PIN beside the nickname throughout teacher-only roster/progress tools;
- rename a nickname;
- reset/change a PIN;
- deactivate/reactivate an account;
- reset today's Daily after a legitimate technology problem;
- temporarily override one student's Focus family.

## Daily fact generator

The shared Daily generator remains versioned as `TDFC-DAILY-v1`, so the previously audited daily sequence does not change in v2.

Each Daily contains 10 unique underlying multiplication facts. Commutative mirrors cannot both appear. Normal core days contain 3 easier, 4 medium, and 3 harder facts. On selected extension days, one harder slot becomes one 11/12 fact.

## Data and privacy

- Student accounts use teacher-assigned nicknames and 4-digit classroom PINs.
- v2.1 intentionally stores a teacher-readable copy of each PIN (`pin_code`) so classroom PINs remain visible in the password-protected Teacher Dashboard. Authentication still verifies the salted scrypt hash.
- Student-facing pages never show classmates' PINs.
- No student email, school ID, or legal name is required.
- Supabase Row Level Security is enabled on all app tables with no public browser policies.
- The Streamlit server uses the private `SUPABASE_SECRET_KEY`.
- Students never receive direct database credentials.
- There is intentionally **no social sharing feature**.

## Streamlit Secrets

```toml
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "YOUR-SERVER-SECRET-KEY"
TEACHER_PASSWORD = "CHOOSE-A-PRIVATE-TEACHER-PASSWORD"
```

## Updating an existing installation

**If you are still on v1:** run `RUN_THIS_ONCE_IN_SUPABASE_v2.sql`. In this package it includes the full adaptive-learning upgrade plus the v2.1 visible-PIN field.

**If you already ran the v2.0 migration:** run only `RUN_THIS_ONCE_IN_SUPABASE_v2_1.sql`.

Existing student PINs created before v2.1 cannot be recovered from their old one-way hashes. The Teacher Dashboard offers a one-click replacement-PIN tool for those legacy accounts; after that, the new classroom PIN remains visible beside the nickname.

Then upload **every file and folder** from the new `UPLOAD_TO_GITHUB` folder to the GitHub repository root. Make sure the `daily_sprint_component` folder is present in GitHub.

## Version notes

### v2.1.0 — Research Alignment + Teacher PIN Visibility

Tightens the adaptive learning sequence around multiplication relationships: early unknown exploration now favors 2s/5s/10s anchors, then derived facts become higher-priority as supporting anchors are learned. Adds a clearer ×3 derived-fact strategy while preserving arrays, retrieval-first practice, correction retries, spacing, the hidden Daily timer, and the no-placement-test model.

Teacher-only views now keep each student's 4-digit classroom PIN visible beside the nickname. Authentication still uses the salted hash internally; a readable copy is retained solely for classroom management. Existing legacy accounts can receive one-click replacement PINs because their original hashes are not reversible.

### v2.0.0 — Adaptive Learning Routine

Adds the research-informed full routine **Daily 10 → Fix Your Misses → Your Focus Practice → Done**, persistent individualized mastery with no placement test, eight-fact adaptive Focus sessions, required correction retries, a hidden competition stopwatch, Daily Stars and school-day Learning Streaks, private student growth views, a teacher class heatmap, Focus overrides, and upgraded derived-fact teaching strategies.

The shared Daily 10 generator and accuracy-first Top-10 ranking remain unchanged.

### v1.0.0 — Full classroom beta

Initial shared Daily 10, class Top 10, student nickname/PIN accounts, visual Practice, teacher roster/dashboard tools, and Supabase persistence.
