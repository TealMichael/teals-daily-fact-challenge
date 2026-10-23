Teal's Daily Fact Challenge — v2.26.0 Today Scroll Hotfix

One-file update for a classroom installation already running v2.26.0.

The new compact Today page no longer contains the old tall title. The app's
global top padding was only 0.7rem, which allowed Streamlit's fixed header
to cover the top controls (including Log out), even at the top of the scroll.

This fix gives the Today screen enough top clearance without changing
other teacher pages, student pages, or the Igniter presentation window.

INSTALL:
1. Open your existing GitHub repository at the root containing app.py.
2. Choose Add file > Upload files.
3. Upload ONLY the app.py file beside this README, replacing the existing one.
4. Commit: v2.26.0 hotfix - Restore Today page top scrolling
5. Wait for Streamlit to update, refresh the page, and verify you can see
   the complete Log out button above the teacher navigation.

No Supabase SQL, Secrets, requirements, or version-number changes.

Rollback: revert the hotfix commit if needed. No student data changes.
