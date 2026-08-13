-- Teal's Daily Fact Challenge v2.2 combined migration: adaptive learning + visible PINs + Weekly Mystery
-- Run this entire file ONCE if the existing live database is still on v1.

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
    add column if not exists focus_override smallint,
    add column if not exists pin_code text;

alter table public.students
    drop constraint if exists pin_code_shape;
alter table public.students
    add constraint pin_code_shape check (pin_code is null or pin_code ~ '^[0-9]{4}$');

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

-- v2.2 Weekly Mystery additions (combined here for installations coming from v1)
create table if not exists public.weekly_mysteries (
    week_start date primary key,
    mystery_key text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint mystery_week_is_monday check (extract(isodow from week_start) = 1),
    constraint mystery_key_not_blank check (length(btrim(mystery_key)) between 1 and 80)
);

create table if not exists public.weekly_mystery_unlocks (
    student_id uuid not null references public.students(student_id) on delete cascade,
    week_start date not null references public.weekly_mysteries(week_start) on delete cascade,
    day_number smallint not null,
    challenge_id uuid not null references public.daily_challenges(challenge_id) on delete cascade,
    unlocked_at timestamptz not null default now(),
    primary key (student_id, week_start, day_number),
    constraint mystery_unlock_day_range check (day_number between 1 and 5)
);

create table if not exists public.weekly_mystery_guesses (
    student_id uuid not null references public.students(student_id) on delete cascade,
    week_start date not null references public.weekly_mysteries(week_start) on delete cascade,
    guess_text text not null,
    correct boolean not null,
    clue_count smallint not null,
    guessed_at timestamptz not null default now(),
    primary key (student_id, week_start),
    constraint mystery_guess_not_blank check (length(btrim(guess_text)) between 1 and 80),
    constraint mystery_guess_clue_count_range check (clue_count between 1 and 5)
);

create index if not exists mystery_unlock_week_idx
    on public.weekly_mystery_unlocks(week_start, unlocked_at);
create index if not exists mystery_guess_week_idx
    on public.weekly_mystery_guesses(week_start, correct, guessed_at);
create index if not exists mystery_guess_student_idx
    on public.weekly_mystery_guesses(student_id, guessed_at desc);

alter table public.weekly_mysteries enable row level security;
alter table public.weekly_mystery_unlocks enable row level security;
alter table public.weekly_mystery_guesses enable row level security;
