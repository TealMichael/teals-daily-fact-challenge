-- Teal's Daily Fact Challenge v1.0
-- Run this entire file once in the Supabase SQL Editor for a NEW project.
-- The Streamlit app uses the server-side SUPABASE_SECRET_KEY. No browser gets
-- direct database credentials.

create extension if not exists pgcrypto;

create table if not exists public.classes (
    class_id uuid primary key default gen_random_uuid(),
    class_name text not null,
    class_name_key text not null unique,
    class_code text not null unique,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    constraint class_name_not_blank check (length(btrim(class_name)) between 1 and 40),
    constraint class_code_shape check (class_code ~ '^[A-Z2-9]{6}$')
);

create table if not exists public.students (
    student_id uuid primary key default gen_random_uuid(),
    class_id uuid not null references public.classes(class_id) on delete cascade,
    nickname text not null,
    nickname_key text not null,
    pin_hash text not null,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    constraint nickname_not_blank check (length(btrim(nickname)) between 1 and 28),
    unique (class_id, nickname_key)
);

create table if not exists public.daily_challenges (
    challenge_id uuid primary key default gen_random_uuid(),
    challenge_date date not null unique,
    challenge_version text not null,
    facts jsonb not null,
    created_at timestamptz not null default now(),
    constraint exactly_ten_facts check (jsonb_typeof(facts) = 'array' and jsonb_array_length(facts) = 10)
);

create table if not exists public.daily_attempts (
    attempt_id uuid primary key default gen_random_uuid(),
    student_id uuid not null references public.students(student_id) on delete cascade,
    challenge_id uuid not null references public.daily_challenges(challenge_id) on delete cascade,
    created_at timestamptz not null default now(),
    timed_started_at timestamptz,
    completed_at timestamptz,
    correct_count smallint,
    timed_seconds numeric(10,3),
    unique (student_id, challenge_id),
    constraint correct_count_range check (correct_count is null or correct_count between 0 and 10),
    constraint timed_seconds_nonnegative check (timed_seconds is null or timed_seconds >= 0),
    constraint completion_summary_consistent check (
        (completed_at is null and correct_count is null and timed_seconds is null)
        or
        (completed_at is not null and timed_started_at is not null and correct_count is not null and timed_seconds is not null)
    )
);

create table if not exists public.daily_answers (
    answer_id uuid primary key default gen_random_uuid(),
    attempt_id uuid not null references public.daily_attempts(attempt_id) on delete cascade,
    question_number smallint not null,
    a smallint not null,
    b smallint not null,
    student_answer integer not null,
    correct_answer integer not null,
    correct boolean not null,
    submitted_at timestamptz not null default now(),
    unique (attempt_id, question_number),
    constraint question_number_range check (question_number between 1 and 10),
    constraint factor_a_range check (a between 2 and 12),
    constraint factor_b_range check (b between 2 and 12),
    constraint product_is_correct check (correct_answer = a * b),
    constraint correctness_is_consistent check (correct = (student_answer = correct_answer))
);

create table if not exists public.practice_answers (
    practice_answer_id uuid primary key default gen_random_uuid(),
    student_id uuid references public.students(student_id) on delete set null,
    focus text not null,
    a smallint not null,
    b smallint not null,
    student_answer integer not null,
    correct_answer integer not null,
    correct boolean not null,
    created_at timestamptz not null default now(),
    constraint practice_factor_a_range check (a between 2 and 12),
    constraint practice_factor_b_range check (b between 2 and 12),
    constraint practice_product_is_correct check (correct_answer = a * b),
    constraint practice_correctness_is_consistent check (correct = (student_answer = correct_answer))
);

create index if not exists students_class_idx on public.students(class_id, active);
create index if not exists attempts_challenge_idx on public.daily_attempts(challenge_id, completed_at);
create index if not exists attempts_student_idx on public.daily_attempts(student_id, challenge_id);
create index if not exists answers_attempt_idx on public.daily_answers(attempt_id, question_number);
create index if not exists practice_student_idx on public.practice_answers(student_id, created_at desc);

-- Lock all tables behind RLS. The supplied app uses the server-side secret key,
-- which bypasses RLS. No anon/authenticated browser policy is created.
alter table public.classes enable row level security;
alter table public.students enable row level security;
alter table public.daily_challenges enable row level security;
alter table public.daily_attempts enable row level security;
alter table public.daily_answers enable row level security;
alter table public.practice_answers enable row level security;
