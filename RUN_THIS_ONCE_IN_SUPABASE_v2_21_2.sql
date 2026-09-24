-- Teal's Daily Fact Challenge v2.21.2 — temporary question images
-- Run once in the SAME Supabase project used by Daily Fact Challenge.

create table if not exists public.question_images (
  image_id uuid primary key default gen_random_uuid(),
  storage_path text not null unique,
  question_date date not null,
  expires_on date not null,
  created_at timestamptz not null default now()
);

alter table public.question_images enable row level security;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'question-images',
  'question-images',
  false,
  2097152,
  array['image/png','image/jpeg','image/webp']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- No public Storage or table policies are created. The Streamlit server uses
-- the existing SUPABASE_SECRET_KEY and generates short-lived signed URLs.
