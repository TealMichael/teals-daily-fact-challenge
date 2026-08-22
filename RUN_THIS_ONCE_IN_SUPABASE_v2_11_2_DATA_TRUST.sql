-- Teal's Daily Fact Challenge — Data Trust Pass (items 1–4)
-- Safe to run once before deploying the matching code patch.
-- Existing app versions can continue to run because all new columns are nullable.

alter table public.daily_answers
    add column if not exists first_student_answer integer,
    add column if not exists first_correct boolean;

-- Existing historical answers predate first-submission capture. Treat their stored
-- official answer as the best available historical evidence.
update public.daily_answers
set first_student_answer = coalesce(first_student_answer, student_answer),
    first_correct = coalesce(first_correct, correct)
where first_student_answer is null or first_correct is null;

alter table public.daily_answers
    drop constraint if exists first_correctness_is_consistent;
alter table public.daily_answers
    add constraint first_correctness_is_consistent check (
        (first_student_answer is null and first_correct is null)
        or
        (first_student_answer is not null and first_correct is not null
         and first_correct = (first_student_answer = correct_answer))
    );

alter table public.daily_attempts
    add column if not exists learning_evidence_applied_at timestamptz;

-- Completed attempts from before this patch already went through the legacy evidence
-- path. Mark them as applied so the repair path only targets new completions.
update public.daily_attempts
set learning_evidence_applied_at = completed_at
where completed_at is not null and learning_evidence_applied_at is null;

alter table public.daily_attempts
    drop constraint if exists learning_evidence_requires_completion;
alter table public.daily_attempts
    add constraint learning_evidence_requires_completion check (
        learning_evidence_applied_at is null or completed_at is not null
    );
