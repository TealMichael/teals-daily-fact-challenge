-- Teal's Daily Fact Challenge v2.10.0 — Quick Warm-Up trial
-- Run once in Supabase SQL Editor before deploying v2.10.0.

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
