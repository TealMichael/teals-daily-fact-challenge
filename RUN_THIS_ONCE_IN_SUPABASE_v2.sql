-- Teal's Daily Fact Challenge v2.0 adaptive learning migration
-- Run this entire file ONCE in the existing v1 Supabase project.

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
