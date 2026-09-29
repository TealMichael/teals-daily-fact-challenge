-- Teal's Daily Fact Challenge v2.23.0
-- Monday Standards Recovery + Standards Mastery evidence.
-- Run ONCE in Supabase SQL Editor BEFORE deploying the v2.23.0 app files.
--
-- PRIVACY CONTRACT:
-- This table stores only the app's existing anonymous UUIDs plus standards,
-- question/answer evidence, and dates. It stores no student names, Skyward IDs,
-- roster files, emails, or other new identifying information.

create table if not exists public.standard_recovery_answers (
    recovery_answer_id uuid primary key default gen_random_uuid(),
    source_quiz_id uuid not null references public.weekly_quiz_sets(quiz_id) on delete cascade,
    student_id uuid not null references public.students(student_id) on delete cascade,
    class_id uuid not null references public.classes(class_id) on delete cascade,
    recovery_date date not null,
    source_quiz_date date not null,
    standard_code text not null,
    standard_description text not null default '',
    bank_question_id text not null,
    question_type text not null,
    prompt text not null,
    student_response text not null,
    correct boolean not null,
    number_correct boolean not null,
    label_correct boolean not null default true,
    answered_at timestamptz not null default now(),
    unique (student_id, source_quiz_id, standard_code),
    constraint standard_recovery_standard_not_blank check (length(btrim(standard_code)) between 1 and 40),
    constraint standard_recovery_bank_id_not_blank check (length(btrim(bank_question_id)) between 1 and 80),
    constraint standard_recovery_type_allowed check (
        question_type in ('Number','Fraction','Multiple choice','Number + Label')
    ),
    constraint standard_recovery_prompt_not_blank check (length(btrim(prompt)) between 1 and 2000)
);

create index if not exists standard_recovery_student_quiz_idx
    on public.standard_recovery_answers(student_id, source_quiz_id, standard_code);
create index if not exists standard_recovery_class_date_idx
    on public.standard_recovery_answers(class_id, recovery_date);
create index if not exists standard_recovery_standard_date_idx
    on public.standard_recovery_answers(standard_code, recovery_date);

alter table public.standard_recovery_answers enable row level security;

-- Intentionally create NO anon/authenticated browser policies.
-- The Streamlit server uses the existing secret/service key. Student browsers
-- never receive direct database access to Recovery or standards evidence.
