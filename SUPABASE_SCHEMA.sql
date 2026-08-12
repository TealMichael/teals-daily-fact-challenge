-- Teal's Daily Fact Challenge v2.1
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
    pin_code text,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    constraint nickname_not_blank check (length(btrim(nickname)) between 1 and 28),
    constraint pin_code_shape check (pin_code is null or pin_code ~ '^[0-9]{4}$'),
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


-- v2 adaptive learning additions (included here for brand-new projects)
alter table public.daily_answers
    add column if not exists response_seconds numeric(8,3);

alter table public.practice_answers
    add column if not exists response_seconds numeric(8,3),
    add column if not exists challenge_id uuid references public.daily_challenges(challenge_id) on delete cascade,
    add column if not exists activity_type text not null default 'free_practice',
    add column if not exists activity_index smallint,
    add column if not exists is_retry boolean not null default false;

alter table public.classes
    add column if not exists focus_override smallint;

alter table public.students
    add column if not exists focus_override smallint;

alter table public.classes
    drop constraint if exists class_focus_override_range;
alter table public.classes
    add constraint class_focus_override_range check (focus_override is null or focus_override between 2 and 10);

alter table public.students
    drop constraint if exists student_focus_override_range;
alter table public.students
    add constraint student_focus_override_range check (focus_override is null or focus_override between 2 and 10);

create table if not exists public.student_fact_mastery (
    student_id uuid not null references public.students(student_id) on delete cascade,
    a smallint not null,
    b smallint not null,
    evidence_count integer not null default 0,
    correct_count integer not null default 0,
    ema_accuracy numeric(8,6),
    ema_seconds numeric(8,3),
    correct_streak integer not null default 0,
    mastery_status text not null default 'Unknown',
    last_practiced_at timestamptz,
    updated_at timestamptz not null default now(),
    primary key (student_id, a, b),
    constraint mastery_core_canonical check (a between 2 and 10 and b between a and 10),
    constraint mastery_evidence_nonnegative check (evidence_count >= 0 and correct_count >= 0 and correct_count <= evidence_count),
    constraint mastery_status_allowed check (mastery_status in ('Unknown','Focus','Building','Fluent'))
);

create table if not exists public.daily_learning_progress (
    student_id uuid not null references public.students(student_id) on delete cascade,
    challenge_id uuid not null references public.daily_challenges(challenge_id) on delete cascade,
    focus_plan jsonb not null default '[]'::jsonb,
    fix_completed_at timestamptz,
    focus_completed_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (student_id, challenge_id),
    constraint focus_plan_is_array check (jsonb_typeof(focus_plan) = 'array')
);

create table if not exists public.app_settings (
    setting_key text primary key,
    setting_value jsonb,
    updated_at timestamptz not null default now()
);

create index if not exists mastery_student_idx on public.student_fact_mastery(student_id, mastery_status);
create index if not exists learning_progress_challenge_idx on public.daily_learning_progress(challenge_id, completed_at);
create index if not exists practice_learning_idx on public.practice_answers(student_id, challenge_id, activity_type, activity_index);
create unique index if not exists one_focus_first_try_per_slot
    on public.practice_answers(student_id, challenge_id, activity_index)
    where activity_type = 'focus' and is_retry = false and challenge_id is not null;

alter table public.daily_answers
    drop constraint if exists daily_response_seconds_nonnegative;
alter table public.daily_answers
    add constraint daily_response_seconds_nonnegative check (response_seconds is null or response_seconds >= 0);

alter table public.practice_answers
    drop constraint if exists practice_response_seconds_nonnegative;
alter table public.practice_answers
    add constraint practice_response_seconds_nonnegative check (response_seconds is null or response_seconds >= 0);

alter table public.student_fact_mastery enable row level security;
alter table public.daily_learning_progress enable row level security;
alter table public.app_settings enable row level security;
