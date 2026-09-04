# Teal's Daily Fact Challenge v2.19.5 — Alternate Daily Keypad Display Hotfix

v2.19.5 fixes a student-visible alternate Daily 10 keypad bug discovered in Mixed Facts: number taps were being stored internally and could be submitted, but the answer display continued to show “Tap your answer.”

Root cause: the browser helper that updates the visible answer looked for an element with `id="entry"`, but the rendered alternate-Daily answer box did not have that id. The hotfix restores that binding and cache-busts only the alternate Daily component so student devices fetch the corrected browser code.

The same alternate Daily component is shared by Addition, Subtraction, Division, Integers, and Mixed, so this prevents the hidden-entry symptom across all non-multiplication Daily modes.

Multiplication Daily, Guided Practice, Fact Coach, adaptive/mastery logic, Fix Your Misses, Focus Practice, Weekly Mystery, dependencies, Supabase schema, and AWTRIX are unchanged.

No Supabase SQL, Streamlit Secret, or AWTRIX change is required. Install the GitHub patch directly over v2.19.4.
