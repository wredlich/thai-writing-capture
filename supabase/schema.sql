-- Write Echo capture: paste into Supabase SQL Editor and Run. Safe to re-run.
create extension if not exists pgcrypto;

create table if not exists public.writers (
  id uuid primary key default gen_random_uuid(),
  nickname text not null,
  handedness text check (handedness in ('right','left','both')),
  age_range text,
  consented boolean not null default false,
  device jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.samples (
  id uuid primary key default gen_random_uuid(),
  writer_id uuid not null references public.writers(id) on delete cascade,
  prompt_id text not null,
  prompt_text text not null,
  style text not null check (style in ('everyday','fast')),
  strokes jsonb not null default '[]'::jsonb,
  canvas_w integer, canvas_h integer, dpr real,
  screen_w integer, screen_h integer,
  user_agent text,
  skipped boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists samples_writer_idx on public.samples(writer_id);

create table if not exists public.admins (email text primary key);

alter table public.writers enable row level security;
alter table public.samples enable row level security;
alter table public.admins  enable row level security;

-- Anonymous visitors: insert only (no select, update, delete).
drop policy if exists writers_anon_insert on public.writers;
create policy writers_anon_insert on public.writers
  for insert to anon, authenticated with check (consented = true);
drop policy if exists samples_anon_insert on public.samples;
create policy samples_anon_insert on public.samples
  for insert to anon, authenticated with check (true);

-- Admin export: signed-in users whose email is in admins can read.
drop policy if exists writers_admin_select on public.writers;
create policy writers_admin_select on public.writers
  for select to authenticated
  using (exists (select 1 from public.admins a where a.email = auth.jwt()->>'email'));
drop policy if exists samples_admin_select on public.samples;
create policy samples_admin_select on public.samples
  for select to authenticated
  using (exists (select 1 from public.admins a where a.email = auth.jwt()->>'email'));
drop policy if exists admins_self_select on public.admins;
create policy admins_self_select on public.admins
  for select to authenticated using (email = auth.jwt()->>'email');

-- Table privileges: anon may only insert.
revoke all on public.writers, public.samples, public.admins from anon;
grant insert on public.writers, public.samples to anon;
grant insert, select on public.writers, public.samples to authenticated;
grant select on public.admins to authenticated;

-- Admin: replace with Warren's email before running.
insert into public.admins(email) values ('REPLACE_WITH_YOUR_EMAIL') on conflict do nothing;
