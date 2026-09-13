# Teal's Daily Fact Challenge v2.21.0 — Quiz of the Week

v2.21.0 adds a Friday-only **Quiz of the Week** while preserving the verified v2.20.3 classroom app everywhere else.

## Friday student flow

When a teacher has saved a quiz for that class/date:

1. **Quiz of the Week** replaces the Friday Igniter.
2. The student completes exactly **5 quiz questions**.
3. The student continues into the existing **Daily 10** flow.
4. The existing Fix Your Misses / Focus Practice / Friday Mystery flow continues unchanged.

Monday–Thursday Igniters are unchanged. If no Quiz of the Week is assigned on a Friday, the existing Igniter remains the fallback.

## Quiz question types

The teacher can mix five questions using:

- Number
- Fraction
- Multiple choice
- Number + Label / Unit

Number and fraction grading uses exact rational comparison rather than string matching. Examples such as `3`, `3.0`, and `3.00` are equal, and equivalent fractions such as `3/4` and `6/8` are equal. Mixed numbers such as `2 1/3` are supported. Number + Label questions require both parts to be correct while preserving component-level results for teacher analysis.

## Teacher tools

A new **Quiz of the Week** teacher section includes:

- five-question Friday quiz builder
- copy-to-multiple-classes support
- real-student lock after a quiz begins
- Test Student preview that does not lock the quiz
- completion and question-level results
- anonymous Skyward bridge export
- local Student Key setup download

Only completed quizzes are included in the anonymous grade export; unfinished/absent students are omitted instead of receiving automatic zeros.

## Privacy / Skyward architecture

The app does **not** add or store student first names, last names, Skyward student numbers, email addresses, or roster files.

Quiz results remain associated with the app's existing random student UUID. For local grade transfer, the app derives a stable, meaningless Student Key and exports only:

- Student Key
- Assignment Name
- Due Date (`MMDDYYYY`)
- Category (`SUMM` or `FORM`)
- Max Score
- Score

The separate local Excel bridge performs the Student Key → real-name match on Michael's computer. Real roster information never needs to enter this app or an AI service.

## Database / deployment

**One new Supabase migration is required before deploying the app files:**

`RUN_THIS_ONCE_IN_SUPABASE_v2_21.sql`

It adds `weekly_quiz_sets` and `weekly_quiz_answers`. Both tables have RLS enabled and intentionally receive no anon/authenticated browser policies. No Streamlit Secret change is required. No AWTRIX reinstall is required.

## What did NOT change

The v2.20.3 production behavior remains the source of truth outside the new Quiz of the Week path. In particular, this release does not redesign or replace:

- Multiplication Daily browser component/keypad
- Alternate Daily browser component/keypad
- Daily question generation, scoring, hidden timer, or first-answer evidence
- Multiplication Guided Practice / Fix / Focus
- Alternate Fix Your Misses / Focus Practice teaching components
- Fact Coach or adaptive/mastery logic
- Perfect Score Club / Top 10
- Weekly Mystery engine
- student login / persistent login
- teacher recovery tools
- AWTRIX
- existing Warm-Up / Igniter data or Monday–Thursday behavior

## Verification

The release includes a dedicated `v2_21_0_quiz_of_week_tests.py` suite covering numeric/fraction equivalence, compound answers, five-question validation, anonymous keys, score scaling, quiz locking, Friday routing, database privacy, and byte-for-byte protection of high-risk student components. Existing critical regression suites were also rechecked against the intentional v2.21 routing addition.
