# Teal's Daily Fact Challenge v2.24.5 — Teacher Supabase Resilience Hotfix

v2.24.5 keeps all v2.24.4 behavior and hardens the teacher Warm-Up against short-lived Supabase/PostgREST API failures while loading the class list.

## What changed
- Retries structured PostgREST infrastructure errors such as transient database/pool/schema-cache availability failures.
- Keeps a last-known-good anonymous class-list cache in the cached server-side store and uses it only for transient failures.
- Replaces the full red Streamlit traceback on the Warm-Up page with a friendly retry control that forces a fresh Supabase client.
- Does not swallow permanent SQL/schema/auth errors.

No new Supabase SQL or Secrets changes are required.
