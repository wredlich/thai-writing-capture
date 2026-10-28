-- Write Echo capture: paste into Supabase SQL Editor and Run. Safe to re-run.
-- An existing project should run supabase/migrations/20261028_invites.sql instead of pasting this again.
create extension if not exists pgcrypto;

create table if not exists public.writers (
  id uuid primary key default gen_random_uuid(),
  nickname text not null,
  handedness text check (handedness in ('right','left','both')),
  age_range text,
  consented boolean not null default false,
  device jsonb,
  invite_code text,
  created_at timestamptz not null default now()
);
alter table public.writers add column if not exists invite_code text;

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
  rep smallint,
  created_at timestamptz not null default now()
);
alter table public.samples add column if not exists rep smallint;
alter table public.samples drop constraint if exists samples_rep_check;
alter table public.samples add constraint samples_rep_check check (rep is null or rep between 1 and 3);
create index if not exists samples_writer_idx on public.samples(writer_id);

create table if not exists public.admins (email text primary key);

create table if not exists public.invites (
  code text primary key,
  label text,
  created_at timestamptz not null default now()
);

alter table public.writers enable row level security;
alter table public.samples enable row level security;
alter table public.admins  enable row level security;
alter table public.invites enable row level security;

-- True only when this invite code is in invites. Security definer so anon never reads that table.
create or replace function public.capture_invite_ok(p_code text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (select 1 from public.invites i where i.code = p_code);
$$;

-- The capture page calls this to see whether invite codes are turned on.
-- If the function is missing, the page keeps the previous signup behavior.
create or replace function public.capture_invites_enabled()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select true;
$$;

revoke all on function public.capture_invite_ok(text) from public;
revoke all on function public.capture_invites_enabled() from public;
grant execute on function public.capture_invite_ok(text) to anon, authenticated;
grant execute on function public.capture_invites_enabled() to anon, authenticated;

-- Anonymous visitors: insert only (no select, update, delete).
-- A writer insert is allowed only when consented and the invite code exists.
drop policy if exists writers_anon_insert on public.writers;
create policy writers_anon_insert on public.writers
  for insert to anon, authenticated
  with check (consented = true and public.capture_invite_ok(invite_code));

-- Samples already require the writer row through writer_id references writers(id).
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

-- No anon policy on invites. Admins can read and create codes.
drop policy if exists invites_admin_select on public.invites;
create policy invites_admin_select on public.invites
  for select to authenticated
  using (exists (select 1 from public.admins a where a.email = auth.jwt()->>'email'));
drop policy if exists invites_admin_insert on public.invites;
create policy invites_admin_insert on public.invites
  for insert to authenticated
  with check (exists (select 1 from public.admins a where a.email = auth.jwt()->>'email'));

-- Table privileges: anon may only insert writers and samples.
revoke all on public.writers, public.samples, public.admins, public.invites from anon;
revoke all on public.invites from authenticated;
grant insert on public.writers, public.samples to anon;
grant insert, select on public.writers, public.samples to authenticated;
grant select on public.admins to authenticated;
grant select, insert on public.invites to authenticated;

-- Admin: replace with Warren's email before running.
insert into public.admins(email) values ('REPLACE_WITH_YOUR_EMAIL') on conflict do nothing;
