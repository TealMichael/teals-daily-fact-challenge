-- Teal's Daily Fact Challenge v2.6
-- Run ONCE if your project is already on v2.5.x.
-- Adds an idempotency key so browser-local Fix/Focus sessions can save a
-- whole evidence batch safely without duplicate rows if a network retry occurs.

alter table public.practice_answers
    add column if not exists client_event_id text;

create unique index if not exists practice_client_event_id_unique
    on public.practice_answers(client_event_id);
