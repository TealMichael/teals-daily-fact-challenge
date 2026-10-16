# Teal's Sunday Pick'em — v1.0.8 Hotfix 8.1: Pulse Placement

**Baseline:** v1.0.8 Pick'em Pulse (October 16, 2026)  
**Scope:** One targeted pregame layout refinement; no new gameplay features.

## Change
- When a real player's full five-player lineup is ready, show the existing **Your Pick'em Pulse** card immediately below **Sunday Status** and above **Your Five Are Ready**.
- Keep the existing heading, five-player rows, injury disclaimer, and Edit Lineup button in their current relative order.
- Do not show pregame Pulse while a lineup is incomplete, a starter is unavailable, an emergency backup is needed, or in Gate 2 demo mode.
- Increment the weekly UI reload marker and build cache identity so Streamlit Cloud picks up the change on a warm deployment.

## Unchanged
- All Pick'em Pulse story content, measurable goal rules, live and final Pulse, and reactions.
- Official lineup selections and locks, injury backups, scoring, NFL refreshes, AWTRIX broadcasts, season standings, navigation, and newsletter.
- No Supabase migrations, Streamlit/GitHub Secrets, workflow edits, dependency changes, or device updates.

## Local verification
- `pytest -q`: **377 passed** (373 previous + 4 placement/warm-redeploy tests).
- `python -m compileall -q .`: PASS.
- `python release_guard.py`: PASS.
- Live Streamlit confirmation must be performed after GitHub deployment.

## GitHub browser installation
1. Unzip the `GITHUB_BROWSER` package on your Mac.
2. Inside `01_UPLOAD_TO_REPOSITORY_ROOT`, select all **four** files (not their containing folder). In the **main/root directory** of your existing GitHub repository, select **Add file → Upload files**, then commit to `main`.
3. Open the existing `tests` folder in GitHub. Upload the **one** file inside `02_UPLOAD_INSIDE_EXISTING_TESTS_FOLDER`, then commit to `main`.
4. In GitHub **Actions**, confirm **Pickem Quality Gate** passes. Streamlit should redeploy automatically.
5. On the Sunday tab before lineup lock, confirm the order: **Week heading → Sunday Status → Pick'em Pulse → Your Five → disclaimer → Edit Lineup**. Verify an incomplete/injury-affected lineup still prioritizes the repair action.

**Root commit message:** `v1.0.8 hotfix8.1 — move Pick'em Pulse above the lineup`  
**Tests commit message:** `test: verify pregame Pulse placement and warm redeploy`  
**Optional GitHub tag:** `v1.0.8-hotfix8.1` (create only after both commits pass)

## Rollback
Revert the new test commit first and root commit second, or restore the previous v1.0.8 Pick'em Pulse versions of `app.py`, `config.py`, and `weekly_ui.py` on GitHub. No database rollback is necessary. Do not delete or reset user data.
