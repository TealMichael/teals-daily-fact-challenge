-- Teal's Daily Fact Challenge v2.5 Student Experience migration
-- You already ran v2, v2.1, and v2.2. Run this entire file ONCE in a NEW SQL Editor query.
-- This changes Weekly Mystery guesses from one-per-week to one Thursday + one Friday.

alter table public.weekly_mystery_guesses
    add column if not exists guess_day smallint;

-- Preserve any earlier Mystery guesses. Old Friday-style guesses used clue_count 5;
-- everything else is treated as the Thursday slot.
update public.weekly_mystery_guesses
set guess_day = case when clue_count >= 5 then 5 else 4 end
where guess_day is null;

alter table public.weekly_mystery_guesses
    alter column guess_day set not null;

alter table public.weekly_mystery_guesses
    drop constraint if exists weekly_mystery_guesses_pkey;

alter table public.weekly_mystery_guesses
    drop constraint if exists mystery_guess_day_range;

alter table public.weekly_mystery_guesses
    add constraint mystery_guess_day_range check (guess_day in (4, 5));

alter table public.weekly_mystery_guesses
    add primary key (student_id, week_start, guess_day);

create index if not exists mystery_guess_student_day_idx
    on public.weekly_mystery_guesses(student_id, week_start, guess_day);
