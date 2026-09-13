-- Teal's Daily Fact Challenge v2.21.0
-- Quiz of the Week foundation.
-- Run ONCE in Supabase SQL Editor BEFORE deploying the v2.21.0 app files.
--
-- PRIVACY CONTRACT:
-- These tables contain no first name, last name, Skyward student number,
-- email address, roster file, or other new identifying roster field.
-- Student identity remains the app's existing random UUID. Skyward identity
-- matching happens only in Michael's local Excel bridge, outside this app.

create table if not exists public.weekly_quiz_sets (
    quiz_id uuid primary key default gen_random_uuid(),
    class_id uuid not null references public.classes(class_id) on delete cascade,
    quiz_date date not null,
    assignment_name text not null,
    category_code text not null default 'SUMM',
    max_score numeric(8,2) not null default 5,
    questions jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (class_id, quiz_date),
    constraint weekly_quiz_assignment_not_blank check (length(btrim(assignment_name)) between 1 and 120),
    constraint weekly_quiz_category_allowed check (category_code in ('SUMM','FORM')),
    constraint weekly_quiz_max_score_range check (max_score > 0 and max_score <= 100),
    constraint weekly_quiz_exactly_five_questions check (
        jsonb_typeof(questions) = 'array' and jsonb_array_length(questions) = 5
    )
);

create table if not exists public.weekly_quiz_answers (
    quiz_answer_id uuid primary key default gen_random_uuid(),
    quiz_id uuid not null references public.weekly_quiz_sets(quiz_id) on delete cascade,
    student_id uuid not null references public.students(student_id) on delete cascade,
    class_id uuid not null references public.classes(class_id) on delete cascade,
    quiz_date date not null,
    question_slot smallint not null,
    question_type text not null,
    prompt text not null,
    student_response text not null,
    correct boolean not null,
    number_correct boolean not null,
    label_correct boolean not null default true,
    answered_at timestamptz not null default now(),
    unique (student_id, quiz_id, question_slot),
    constraint weekly_quiz_slot_range check (question_slot between 1 and 5),
    constraint weekly_quiz_type_allowed check (
        question_type in ('Number','Fraction','Multiple choice','Number + Label')
    ),
    constraint weekly_quiz_prompt_not_blank check (length(btrim(prompt)) between 1 and 2000)
);

create index if not exists weekly_quiz_sets_class_date_idx
    on public.weekly_quiz_sets(class_id, quiz_date);
create index if not exists weekly_quiz_answers_quiz_student_idx
    on public.weekly_quiz_answers(quiz_id, student_id, question_slot);
create index if not exists weekly_quiz_answers_date_class_idx
    on public.weekly_quiz_answers(quiz_date, class_id);

alter table public.weekly_quiz_sets enable row level security;
alter table public.weekly_quiz_answers enable row level security;

-- Intentionally create NO anon/authenticated browser policies.
-- The Streamlit server uses the existing secret/service key just like the rest
-- of the protected classroom data. Nothing in this migration exposes quiz data
-- directly to student browsers, AWTRIX, or any AI service.
