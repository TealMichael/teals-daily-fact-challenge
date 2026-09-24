# Teal's Daily Fact Challenge v2.21.2 — Temporary Question Images

This cumulative release is built directly from the validated v2.21.1 FULL CURRENT APP.

## New in v2.21.2
- Optional image upload on every Igniter question.
- Optional image upload on every Quiz of the Week question.
- PNG, JPG/JPEG, and WEBP accepted.
- Images are automatically resized/compressed and stored as WEBP.
- Private Supabase Storage bucket; students receive only short-lived signed image URLs.
- Image metadata contains no student data.
- Images expire automatically after the scheduled question date + 7 days.
- Expired image cleanup is best-effort and cannot block the normal classroom workflow.
- Existing question text/answers/results stay available after the temporary image is gone.

## Privacy
The established privacy architecture is unchanged. No student first/last names, Skyward IDs, or roster files belong in the app or AI. The local Excel Skyward bridge remains the only identity mapping.

## Install
Run `RUN_THIS_ONCE_IN_SUPABASE_v2_21_2.sql` once, then deploy the files. See `DEPLOYMENT_STEPS.txt`.
