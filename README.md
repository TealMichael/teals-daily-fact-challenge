# Teal's Daily Fact Challenge v2.19.4 — Classroom Hardening

v2.19.4 is a student-safety and reliability pass after the first full-class trial of alternate Fix Your Misses / Focus Practice.

The release prevents a temporary Daily-mode read failure from silently starting a student in Multiplication, stabilizes rapid digit entry on the alternate Daily keypad, closes alternate Focus coverage gaps (including Mixed ×11/×12 and integer zero items), improves zero-case teaching models, auto-starts alternate coaching so WATCH IT cannot be a blocking gate, and rebuilds several Supabase student-list queries on retry.

Multiplication Daily, Guided Practice, Fact Coach, adaptive/mastery logic, TDFC-DAILY-v1, Weekly Mystery, dependencies, and AWTRIX remain protected and unchanged.

No Supabase SQL, Streamlit Secret, or AWTRIX change is required. Install the GitHub patch directly over v2.19.3.
