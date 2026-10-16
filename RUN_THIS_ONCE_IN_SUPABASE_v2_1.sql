-- Teal's Daily Fact Challenge v2.1 teacher PIN visibility migration
-- If you already ran the v2 adaptive-learning migration, run this small file once.

alter table public.students
    add column if not exists pin_code text;

alter table public.students
    drop constraint if exists pin_code_shape;
alter table public.students
    add constraint pin_code_shape check (pin_code is null or pin_code ~ '^[0-9]{4}$');

-- Existing student PINs were stored only as one-way hashes and cannot be recovered.
-- The Teacher Dashboard will offer one-click replacement PIN generation for any
-- older account whose pin_code is still null. New/reset PINs remain visible there.
