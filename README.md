# Teal's Daily Fact Challenge v2.24.4 — Order Tiles Repeat-Interaction Hotfix

v2.24.4 keeps all v2.24.3 behavior and fixes a Streamlit Components v2 rerender bug in **Order Tiles**.

## Fixed
- First drag works but later drags stop responding.
- Move buttons stop affecting the order after component state reruns.
- Selected tile state is restored after a normal component rerender.

The shared fix applies to Igniter, Quiz of the Week, and Monday Recovery.

No Supabase SQL and no Secrets changes are required for v2.24.4. The v2.24.2 SQL constraint hotfix remains part of the cumulative build and should already have been run once.
