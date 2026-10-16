-- Teal's Daily Fact Challenge v2.17.0
-- Follow-Up Foundation for alternate Daily 10 modes.
-- Run once BEFORE deploying the v2.17 app files.
-- Backward-compatible with v2.16.4.

create table if not exists public.alternate_learning_progress (
    student_id uuid not null references public.students(student_id) on delete cascade,
    challenge_id uuid not null references public.daily_challenges(challenge_id) on delete cascade,
    daily_mode text not null,
    focus_plan jsonb not null default '[]'::jsonb,
    fix_completed_at timestamptz,
    focus_completed_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (student_id, challenge_id),
    constraint alternate_progress_mode_allowed check (
        daily_mode in ('Addition Facts','Subtraction Facts','Division Facts','Integers','Mixed')
    ),
    constraint alternate_focus_plan_is_array check (jsonb_typeof(focus_plan) = 'array')
);

create table if not exists public.alternate_learning_events (
    event_id uuid primary key default gen_random_uuid(),
    student_id uuid not null references public.students(student_id) on delete cascade,
    challenge_id uuid not null references public.daily_challenges(challenge_id) on delete cascade,
    attempt_id uuid not null references public.daily_attempts(attempt_id) on delete cascade,
    daily_mode text not null,
    activity_type text not null,
    activity_index smallint not null,
    domain text not null,
    skill_key text not null,
    skill_label text not null,
    item_key text not null,
    prompt text not null,
    student_answer integer not null,
    correct_answer integer not null,
    correct boolean not null,
    is_retry boolean not null default false,
    response_seconds numeric(10,3),
    client_event_id text not null,
    created_at timestamptz not null default now(),
    constraint alternate_event_mode_allowed check (
        daily_mode in ('Addition Facts','Subtraction Facts','Division Facts','Integers','Mixed')
    ),
    constraint alternate_event_activity_allowed check (activity_type in ('daily','fix_miss','focus')),
    constraint alternate_event_domain_allowed check (
        domain in ('Multiplication','Addition Facts','Subtraction Facts','Division Facts','Integers')
    ),
    constraint alternate_event_index_range check (activity_index between 1 and 20),
    constraint alternate_event_correctness_consistent check (correct = (student_answer = correct_answer)),
    constraint alternate_event_seconds_nonnegative check (response_seconds is null or response_seconds >= 0)
);

create unique index if not exists alternate_learning_events_client_event_id_unique
    on public.alternate_learning_events(client_event_id);
create index if not exists alternate_learning_progress_challenge_idx
    on public.alternate_learning_progress(challenge_id, completed_at);
create index if not exists alternate_learning_events_student_idx
    on public.alternate_learning_events(student_id, created_at desc);
create index if not exists alternate_learning_events_skill_idx
    on public.alternate_learning_events(student_id, domain, skill_key, created_at desc);

alter table public.alternate_learning_progress enable row level security;
alter table public.alternate_learning_events enable row level security;

-- Preserve the v2.13-v2.16 contract for already-finished alternate Dailies.
-- Students are never asked to return and complete a new follow-up for a past day.
insert into public.alternate_learning_progress (
    student_id, challenge_id, daily_mode, fix_completed_at, completed_at, created_at, updated_at
)
select
    da.student_id,
    da.challenge_id,
    da.daily_mode,
    da.completed_at,
    da.completed_at,
    coalesce(da.created_at, da.completed_at, now()),
    now()
from public.daily_attempts da
where da.completed_at is not null
  and da.daily_mode in ('Addition Facts','Subtraction Facts','Division Facts','Integers','Mixed')
on conflict (student_id, challenge_id) do nothing;
