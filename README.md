# Teal's Daily Fact Challenge v2.22.2 — Inline Question Bank Picker

This cumulative release is built directly from the working v2.22.1 FULL CURRENT APP.

## New in v2.22.2
- Adds **📚 Add from Indiana Question Bank** directly inside every Igniter question editor and every Quiz of the Week question editor.
- Choose **Grade 5 / 6 / 7 → Standard → Question 1–10 or Random** without leaving the builder.
- Loading affects only the selected question slot. Other unsaved question drafts remain intact.
- The selected bank question is copied into the normal editor, where wording, answers, choices, units, standards, and images can still be edited.
- Nothing is published merely by loading from the bank. The normal **Save Warm-Up** / **Save Quiz of the Week** action remains required.
- If a slot already has draft text, the picker clearly uses **Replace current question** for that slot.
- The standalone Question Bank browser remains available for browsing all 750 questions.
- Includes a mixed/partial-deployment guard so the core builders continue loading if the inline picker is temporarily unavailable during a GitHub file rollout.

## Indiana Standards Question Bank
- **750 ready-to-use questions**: 10 for each of 75 Grade 5, 6, and 7 Indiana math standards represented in the app.
- Grade totals: 260 Grade 5, 250 Grade 6, 240 Grade 7.
- 42 Essential standards / 420 Essential questions.
- Permanent built-in diagrams do not use Supabase Storage or the temporary-image quota.
- Supported shared types: Number, Fraction, Multiple choice, and Number + Label.

## Unchanged
- Daily 10, Fix Your Misses, Focus Practice, teaching models, Weekly Mystery, Top 10, Perfect Score Club, AWTRIX, login/session behavior, Friday Quiz grading/navigation, anonymous Skyward export, and the local-only identity bridge remain unchanged.
- Teacher-uploaded question images still use the existing private Supabase temporary-image flow and 7-day post-question-date cleanup.
- No new Supabase migration or Secrets change is required.

## Privacy
No student first/last names, Skyward IDs, or roster files belong in the app or AI. The private local Excel Skyward bridges remain the only Student Key ↔ real-name mapping.
