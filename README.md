# Teal's Daily Fact Challenge v2.23.0 — Monday Standards Recovery

This cumulative release is built directly from the working v2.22.2 FULL CURRENT APP.

## New in v2.23.0
- Quiz of the Week questions can be tagged to a Grade 5, 6, or 7 Indiana Math standard.
- Built-in Question Bank questions automatically tag their standard when loaded into the Quiz builder.
- Monday student flow becomes: **Igniter → Monday Recovery (when needed) → Daily 10**.
- Recovery uses the prior Friday Quiz, gives one new bank question per distinct missed tagged standard, and caps the session at 3 questions.
- Multiple missed Friday questions on one standard still create only one Recovery item.
- The exact built-in bank question(s) seen Friday are excluded from Monday Recovery.
- Recovery answers feed the Teacher Standards Mastery Tracker as another evidence source.
- Standards Tracker now combines **Igniter + Quiz of the Week + Recovery** evidence.
- A single correct Recovery answer cannot by itself make a standard Proficient or Strong.
- Recovery is supplemental/fail-open so it cannot strand students before Daily 10.

## Required Supabase step
Run `RUN_THIS_ONCE_IN_SUPABASE_v2_23.sql` once before deploying the app files. It adds the private `standard_recovery_answers` table and indexes.

No Secrets changes are required.

## Privacy
The Recovery table stores only existing anonymous app UUIDs and standards/question evidence. No student names, Skyward IDs, emails, or roster files are stored.

## Unchanged
Daily 10, Fix Your Misses, Focus Practice, teaching models, Weekly Mystery, Top 10, Perfect Score Club, AWTRIX, login/session behavior, Quiz navigation, temporary image cleanup, anonymous Skyward export, and local-only bridge workbooks remain unchanged.
