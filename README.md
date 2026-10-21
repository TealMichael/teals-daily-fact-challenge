# Teal’s Daily Fact Challenge v2.25.1

Weekly Planning Center and teacher-only Igniter Presentation Mode, built on the verified v2.25.0 classroom source. The original v2.25.0 improvements below are retained.

## New teacher tools

- **Weekly Planning** prepares Monday–Thursday two-question Igniters and Friday's five-question quiz for each class independently. Choose standards, generate suggestions, edit or swap questions, save a draft, then review and explicitly publish.
- Friday defaults to the preceding week's published Monday–Thursday instructional standards. If none are available, choose previously taught skills yourself. It never silently substitutes the current week's skills.
- **Display Igniter** projects the two published questions, with independently controlled answers hidden on every open and date change. Use Full screen or the clean theater view. Student answering, checking, and grading continue as before.
- Started real-student assignments cannot be replaced in the planner. Publication is atomic, detects conflicts, and retains before/after question snapshots.

**Installation:** run only `RUN_THIS_ONCE_IN_SUPABASE_v2_25_1.sql` for the new planner. Presentation alone does not need this migration. Keep existing Secrets and dependency versions. See `DEPLOYMENT_STEPS.txt` and the release package's `README_FIRST.md` before installation.

## Retained v2.25.0 classroom improvements

Classroom workflow improvements, built from your uploaded v2.24.5 full app.

## What students will notice

- Friday Quiz of the Week now has a five-answer review screen. Students can edit any answer before choosing **Submit Quiz**. Correct answers are not revealed during review.
- Back preserves the current answer in the same session, including an unfinished answer. Earlier saved answers still load when students return to a question.
- Enter no longer accidentally activates the Back button on Questions 2–5.
- Igniter and Friday quiz loading errors now have a **Try Again** button that keeps the student signed in and requests a fresh connection.
- Numeric grading accepts common pasted minus signs and fraction symbols, including `−3`, `½`, `2½`, and `3⁄4`. Negative mixed numbers such as `-0 1/2` are now graded correctly. Malformed commas such as `1,5` no longer silently turn into `15`.

## What the teacher will notice

- In the selected class on Today, students with saved Igniter or quiz answers count as Working before Daily 10.
- The roster shows stages such as **Igniter · 1/2 saved** and **Quiz of the Week · 4/5 saved**.
- Assigned Friday quizzes have Submitted / In progress / No answers saved counts and a shortcut to that class’s results.
- Friday visibility follows the student route: an assigned quiz replaces the Igniter summary.
- Failed lesson reads show unavailable counts instead of misleading totals. Quiz results keep Test Student separate from real class results and exports.


These retained v2.25.0 changes required no database update. The new v2.25.1 Weekly Planning Center requires the additive migration described above.
