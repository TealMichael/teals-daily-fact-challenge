-- Teal's Daily Fact Challenge v2.2
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
    is_test boolean not null default false,
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
    learning_evidence_applied_at timestamptz,
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
    first_student_answer integer,
    first_correct boolean,
    submitted_at timestamptz not null default now(),
    unique (attempt_id, question_number),
    constraint question_number_range check (question_number between 1 and 10),
    constraint factor_a_range check (a between 2 and 12),
    constraint factor_b_range check (b between 2 and 12),
    constraint product_is_correct check (correct_answer = a * b),
    constraint correctness_is_consistent check (correct = (student_answer = correct_answer)),
    constraint first_correctness_is_consistent check (
        (first_student_answer is null and first_correct is null)
        or
        (first_student_answer is not null and first_correct is not null and first_correct = (first_student_answer = correct_answer))
    )
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
    client_event_id text,
    created_at timestamptz not null default now(),
    constraint practice_factor_a_range check (a between 2 and 12),
    constraint practice_factor_b_range check (b between 2 and 12),
    constraint practice_product_is_correct check (correct_answer = a * b),
    constraint practice_correctness_is_consistent check (correct = (student_answer = correct_answer))
);

create index if not exists students_class_idx on public.students(class_id, active);
create index if not exists students_test_idx on public.students(is_test, class_id);
create index if not exists attempts_challenge_idx on public.daily_attempts(challenge_id, completed_at);
create index if not exists attempts_student_idx on public.daily_attempts(student_id, challenge_id);
create index if not exists answers_attempt_idx on public.daily_answers(attempt_id, question_number);
create index if not exists practice_student_idx on public.practice_answers(student_id, created_at desc);
create unique index if not exists practice_client_event_id_unique on public.practice_answers(client_event_id);

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

-- v2.2 Weekly Mystery reward layer (included here for brand-new projects)
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
    guess_day smallint not null,
    guess_text text not null,
    correct boolean not null,
    clue_count smallint not null,
    guessed_at timestamptz not null default now(),
    primary key (student_id, week_start, guess_day),
    constraint mystery_guess_day_range check (guess_day in (4, 5)),
    constraint mystery_guess_not_blank check (length(btrim(guess_text)) between 1 and 80),
    constraint mystery_guess_clue_count_range check (clue_count between 1 and 5)
);

create index if not exists mystery_unlock_week_idx on public.weekly_mystery_unlocks(week_start, unlocked_at);
create index if not exists mystery_guess_week_idx on public.weekly_mystery_guesses(week_start, correct, guessed_at);
create index if not exists mystery_guess_student_idx on public.weekly_mystery_guesses(student_id, guessed_at desc);
create index if not exists mystery_guess_student_day_idx on public.weekly_mystery_guesses(student_id, week_start, guess_day);

alter table public.weekly_mysteries enable row level security;
alter table public.weekly_mystery_unlocks enable row level security;
alter table public.weekly_mystery_guesses enable row level security;

-- v2.10 Quick Warm-Up trial (included here for brand-new projects)
create table if not exists public.warmup_sets (
    warmup_set_id uuid primary key default gen_random_uuid(),
    class_id uuid not null references public.classes(class_id) on delete cascade,
    warmup_date date not null,
    question_one jsonb not null,
    question_two jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (class_id, warmup_date),
    constraint warmup_question_one_object check (jsonb_typeof(question_one) = 'object'),
    constraint warmup_question_two_object check (jsonb_typeof(question_two) = 'object')
);

create table if not exists public.warmup_answers (
    warmup_answer_id uuid primary key default gen_random_uuid(),
    warmup_set_id uuid not null references public.warmup_sets(warmup_set_id) on delete cascade,
    student_id uuid not null references public.students(student_id) on delete cascade,
    class_id uuid not null references public.classes(class_id) on delete cascade,
    warmup_date date not null,
    question_slot smallint not null,
    question_type text not null,
    prompt text not null,
    standard_code text not null,
    standard_description text not null default '',
    student_answer text not null,
    correct_answer text not null,
    correct boolean not null,
    answered_at timestamptz not null default now(),
    unique (student_id, warmup_set_id, question_slot),
    constraint warmup_question_slot_range check (question_slot in (1, 2)),
    constraint warmup_question_type_allowed check (question_type in ('Short answer', 'Multiple choice')),
    constraint warmup_prompt_not_blank check (length(btrim(prompt)) between 1 and 1000),
    constraint warmup_standard_not_blank check (length(btrim(standard_code)) between 1 and 120)
);

create index if not exists warmup_sets_class_date_idx on public.warmup_sets(class_id, warmup_date);
create index if not exists warmup_answers_date_class_idx on public.warmup_answers(warmup_date, class_id, question_slot);
create index if not exists warmup_answers_student_idx on public.warmup_answers(student_id, warmup_date);

alter table public.warmup_sets enable row level security;
alter table public.warmup_answers enable row level security;

-- v2.12.0 AWTRIX Top 10 integration (included here for brand-new projects)
-- Teal's Daily Fact Challenge v2.12.0
-- AWTRIX Top 10 integration foundation.
-- Run once after the earlier migrations.
--
-- Security design:
--   * The two new tables remain fully behind RLS with no browser policies.
--   * The clock receives only a preformatted rank + nickname string.
--   * Scores, times, PINs, student IDs, and teacher data are never returned.
--   * Public RPC access requires BOTH the project's publishable/anon API key
--     and a separate revocable X-AWTRIX-Token header whose SHA-256 hash is
--     stored in awtrix_clock_config.

create extension if not exists pgcrypto;

create table if not exists public.awtrix_clock_config (
    config_id smallint primary key default 1,
    block1_class_id uuid references public.classes(class_id) on delete set null,
    block2_class_id uuid references public.classes(class_id) on delete set null,
    block3_class_id uuid references public.classes(class_id) on delete set null,
    token_hash text,
    token_hint text,
    updated_at timestamptz not null default now(),
    constraint awtrix_single_config check (config_id = 1),
    constraint awtrix_token_hash_shape check (token_hash is null or token_hash ~ '^[0-9a-f]{64}$')
);

create table if not exists public.awtrix_clock_commands (
    command_id bigint generated by default as identity primary key,
    block_number smallint not null,
    requested_at timestamptz not null default now(),
    constraint awtrix_block_number_range check (block_number between 1 and 3)
);

create index if not exists awtrix_clock_commands_requested_idx
    on public.awtrix_clock_commands(command_id desc, requested_at desc);

alter table public.awtrix_clock_config enable row level security;
alter table public.awtrix_clock_commands enable row level security;

insert into public.awtrix_clock_config(config_id)
values (1)
on conflict (config_id) do nothing;

-- Internal helper. It may inspect private classroom data, but it returns only
-- the student-safe text that is allowed on the physical clock.
create or replace function public.awtrix_top10_payload_for_block(p_block integer)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, pg_temp
as $$
declare
    v_class_id uuid;
    v_class_name text;
    v_challenge_id uuid;
    v_count integer := 0;
    v_names text;
    v_text text;
begin
    if p_block not between 1 and 3 then
        return jsonb_build_object('ok', false, 'error', 'invalid_block');
    end if;

    select case p_block
        when 1 then block1_class_id
        when 2 then block2_class_id
        when 3 then block3_class_id
    end
    into v_class_id
    from public.awtrix_clock_config
    where config_id = 1;

    if v_class_id is null then
        return jsonb_build_object('ok', false, 'error', 'block_not_mapped', 'block', p_block);
    end if;

    select class_name
    into v_class_name
    from public.classes
    where class_id = v_class_id;

    select challenge_id
    into v_challenge_id
    from public.daily_challenges
    where challenge_date = (now() at time zone 'America/Indiana/Indianapolis')::date
    limit 1;

    if v_challenge_id is not null then
        with ranked as (
            select
                row_number() over (
                    order by da.correct_count desc, da.timed_seconds asc, da.completed_at asc
                ) as rank,
                s.nickname
            from public.daily_attempts da
            join public.students s on s.student_id = da.student_id
            where da.challenge_id = v_challenge_id
              and da.completed_at is not null
              and s.class_id = v_class_id
              and s.active = true
              and coalesce(s.is_test, false) = false
        ), top_rows as (
            select rank, nickname
            from ranked
            where rank <= 10
            order by rank
        )
        select
            count(*)::integer,
            string_agg('#' || rank::text || ' ' || nickname, '   ' order by rank)
        into v_count, v_names
        from top_rows;
    end if;

    if v_count > 0 then
        v_text := 'BLOCK ' || p_block::text || ' TOP 10!   ' || v_names;
    else
        v_text := 'BLOCK ' || p_block::text || ' TOP 10!   NO FINISHERS YET';
    end if;

    return jsonb_build_object(
        'ok', true,
        'block', p_block,
        'class_name', coalesce(v_class_name, 'Class'),
        'count', v_count,
        'text', v_text
    );
end;
$$;

revoke all on function public.awtrix_top10_payload_for_block(integer) from public;
revoke all on function public.awtrix_top10_payload_for_block(integer) from anon;
revoke all on function public.awtrix_top10_payload_for_block(integer) from authenticated;

create or replace function public.awtrix_top10(p_block integer)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, extensions, pg_temp
as $$
declare
    v_headers jsonb;
    v_token text;
    v_expected_hash text;
begin
    v_headers := coalesce(nullif(current_setting('request.headers', true), ''), '{}')::jsonb;
    v_token := coalesce(v_headers ->> 'x-awtrix-token', '');

    select token_hash
    into v_expected_hash
    from public.awtrix_clock_config
    where config_id = 1;

    if v_expected_hash is null
       or v_token = ''
       or encode(digest(v_token, 'sha256'), 'hex') <> v_expected_hash then
        return jsonb_build_object('ok', false, 'error', 'unauthorized');
    end if;

    return public.awtrix_top10_payload_for_block(p_block);
end;
$$;

create or replace function public.awtrix_poll(p_after_id bigint default 0)
returns jsonb
language plpgsql
stable
security definer
set search_path = public, extensions, pg_temp
as $$
declare
    v_headers jsonb;
    v_token text;
    v_expected_hash text;
    v_command_id bigint;
    v_block integer;
    v_latest_id bigint := 0;
    v_payload jsonb;
begin
    v_headers := coalesce(nullif(current_setting('request.headers', true), ''), '{}')::jsonb;
    v_token := coalesce(v_headers ->> 'x-awtrix-token', '');

    select token_hash
    into v_expected_hash
    from public.awtrix_clock_config
    where config_id = 1;

    if v_expected_hash is null
       or v_token = ''
       or encode(digest(v_token, 'sha256'), 'hex') <> v_expected_hash then
        return jsonb_build_object('ok', false, 'error', 'unauthorized');
    end if;

    select coalesce(max(command_id), 0)
    into v_latest_id
    from public.awtrix_clock_commands;

    select command_id, block_number
    into v_command_id, v_block
    from public.awtrix_clock_commands
    where command_id > greatest(coalesce(p_after_id, 0), 0)
      and requested_at >= now() - interval '10 minutes'
    order by command_id desc
    limit 1;

    if v_command_id is null then
        return jsonb_build_object(
            'ok', true,
            'manual', false,
            'command_id', greatest(coalesce(p_after_id, 0), v_latest_id)
        );
    end if;

    v_payload := public.awtrix_top10_payload_for_block(v_block);
    return v_payload || jsonb_build_object(
        'manual', true,
        'command_id', v_command_id
    );
end;
$$;

revoke all on function public.awtrix_top10(integer) from public;
revoke all on function public.awtrix_poll(bigint) from public;
grant execute on function public.awtrix_top10(integer) to anon, authenticated;
grant execute on function public.awtrix_poll(bigint) to anon, authenticated;
