-- Teal's Daily Fact Challenge v2.24.2
-- Interactive Math database constraint hotfix.
-- Run ONCE in Supabase SQL Editor. Safe to rerun if needed.
--
-- Why this is needed:
-- v2.24.0 added Compare Values and Order Tiles as first-class question types,
-- but the existing answer-table CHECK constraints still allowed only the older
-- question types. The app could grade the answer correctly but Supabase rejected
-- the saved answer, leaving the student unable to continue.
--
-- This migration only broadens existing question_type CHECK constraints.
-- It does not add student-identifying fields or change any saved answer data.

alter table public.warmup_answers
    drop constraint if exists warmup_question_type_allowed;
alter table public.warmup_answers
    add constraint warmup_question_type_allowed check (
        question_type in (
            'Short answer',
            'Number',
            'Fraction',
            'Multiple choice',
            'Number + Label',
            'Compare Values',
            'Order Tiles',
            'Expanded Form',
            'Equivalent Number',
            'Multi-Part — 2 answers'
        )
    );

alter table public.weekly_quiz_answers
    drop constraint if exists weekly_quiz_type_allowed;
alter table public.weekly_quiz_answers
    add constraint weekly_quiz_type_allowed check (
        question_type in (
            'Number',
            'Fraction',
            'Multiple choice',
            'Number + Label',
            'Compare Values',
            'Order Tiles'
        )
    );

alter table public.standard_recovery_answers
    drop constraint if exists standard_recovery_type_allowed;
alter table public.standard_recovery_answers
    add constraint standard_recovery_type_allowed check (
        question_type in (
            'Number',
            'Fraction',
            'Multiple choice',
            'Number + Label',
            'Compare Values',
            'Order Tiles'
        )
    );
