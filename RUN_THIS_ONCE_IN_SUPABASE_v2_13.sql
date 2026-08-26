-- Teal's Daily Fact Challenge v2.13.0
-- Run once BEFORE deploying the v2.13 app files.
-- Backward-compatible with v2.12.0 Hotfix 3.

alter table public.daily_attempts
    add column if not exists daily_mode text not null default 'Multiplication',
    add column if not exists custom_questions jsonb,
    add column if not exists custom_answers jsonb;

alter table public.daily_attempts
    drop constraint if exists daily_mode_allowed;
alter table public.daily_attempts
    add constraint daily_mode_allowed check (
        daily_mode in ('Multiplication','Addition Facts','Subtraction Facts','Division Facts','Integers','Mixed')
    );

alter table public.daily_attempts
    drop constraint if exists custom_questions_is_ten_array;
alter table public.daily_attempts
    add constraint custom_questions_is_ten_array check (
        custom_questions is null
        or (jsonb_typeof(custom_questions) = 'array' and jsonb_array_length(custom_questions) = 10)
    );

alter table public.daily_attempts
    drop constraint if exists custom_answers_is_ten_array;
alter table public.daily_attempts
    add constraint custom_answers_is_ten_array check (
        custom_answers is null
        or (jsonb_typeof(custom_answers) = 'array' and jsonb_array_length(custom_answers) = 10)
    );

alter table public.warmup_answers
    drop constraint if exists warmup_question_type_allowed;
alter table public.warmup_answers
    add constraint warmup_question_type_allowed check (
        question_type in (
            'Short answer',
            'Multiple choice',
            'Expanded Form',
            'Equivalent Number',
            'Multi-Part — 2 answers'
        )
    );
