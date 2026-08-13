-- Teal's Daily Fact Challenge v2.2 Weekly Mystery migration
-- You already ran v2 and v2.1. Run this entire file ONCE in a NEW SQL Editor query.

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
