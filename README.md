# Teal's Daily Fact Challenge v2.22.1 — Question Bank Startup Hotfix

This cumulative release is built directly from the validated v2.21.3 FULL CURRENT APP.

## v2.22.1 hotfix

- Prevents the Indiana Standards Question Bank from crashing app startup if GitHub temporarily has the pre-v2.22 `indiana_math_standards.py` during deployment.
- Essential-standard metadata is now read directly from the packaged question-bank data.
- No Supabase SQL or Secrets changes.

## New in v2.22.0
- Adds a permanent **Indiana Standards Question Bank** to Teacher Tools.
- Includes **750 ready-to-use questions**: exactly 10 for each of the 75 Grade 5, 6, and 7 Indiana math standards represented in the app.
- Grade totals: 260 Grade 5 questions, 250 Grade 6 questions, and 240 Grade 7 questions.
- Marks the 42 Essential standards and supports an Essential-only filter.
- Browse by Grade → Domain → Standard, then move Previous / Random / Next or open all 10 questions for a standard.
- One-click handoff sends a bank question into either **Igniter** or **Quiz of the Week**.
- Bank questions are copied into the normal editor, so the teacher can revise wording, numbers, answer choices, labels, or images before saving.
- Includes lightweight permanent built-in diagrams for selected visual questions. These files live in the app package and do not use Supabase Storage or the 7-day temporary-image system.
- Supports the existing shared answer types: Number, Fraction, Multiple choice, and Number + Label.

## Important behavior
- Choosing a bank question does **not** immediately publish it. The question is loaded into the existing Igniter/Quiz editor and still requires the normal Save action.
- A bank question is copied, not linked. Editing a copied question never changes the permanent bank and later bank updates cannot alter previously saved student work.
- Teacher-uploaded images still use the existing private Supabase temporary-image flow and 7-day post-question-date cleanup.
- The Question Bank itself is static app content and does not store student information or require Supabase reads/writes.

## Unchanged
- Daily 10, Fix Your Misses, Focus Practice, teaching models, Weekly Mystery, Top 10, Perfect Score Club, AWTRIX, login/session behavior, Friday Quiz flow, anonymous Skyward export, and the local-only identity bridge remain unchanged.
- Quiz Back/edit navigation from v2.21.3 remains intact.
- Temporary question-image behavior from v2.21.2 remains intact.
- No new Supabase migration or Secrets change is required.

## Privacy
No student first/last names, Skyward IDs, or roster files belong in the app or AI. The private local Excel Skyward bridges remain the only Student Key ↔ real-name mapping.
