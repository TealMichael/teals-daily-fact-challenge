-- Teal's Daily Fact Challenge v2.9
-- Teacher Test Student sandbox support. Run once after v2.8.x.

alter table public.students
    add column if not exists is_test boolean not null default false;

create index if not exists students_test_idx on public.students(is_test, class_id);
