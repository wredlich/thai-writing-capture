-- Invite codes for Write Echo.
-- Paste this whole file into the Supabase SQL editor and run it once.
-- Safe to run again. Until this has been run, the capture page keeps working without an invite.

alter table public.writers add column if not exists invite_code text;

alter table public.samples add column if not exists rep smallint;
alter table public.samples drop constraint if exists samples_rep_check;
alter table public.samples add constraint samples_rep_check check (rep is null or rep between 1 and 3);

create table if not exists public.invites (
  code text primary key,
  label text,
  created_at timestamptz not null default now()
);

alter table public.invites enable row level security;

-- Returns true when the code is in invites. Security definer so the anon role never reads that table.
create or replace function public.capture_invite_ok(p_code text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (select 1 from public.invites i where i.code = p_code);
$$;

-- The capture page calls this. A missing function means invite codes are not on yet.
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

-- Writer insert succeeds only when the person consented and the invite code exists.
drop policy if exists writers_anon_insert on public.writers;
create policy writers_anon_insert on public.writers
  for insert to anon, authenticated
  with check (consented = true and public.capture_invite_ok(invite_code));

-- Sample inserts already require the writer row: samples.writer_id references writers(id).

-- Anon has no select, insert, update, or delete on invites.
drop policy if exists invites_admin_select on public.invites;
create policy invites_admin_select on public.invites
  for select to authenticated
  using (exists (select 1 from public.admins a where a.email = auth.jwt()->>'email'));

drop policy if exists invites_admin_insert on public.invites;
create policy invites_admin_insert on public.invites
  for insert to authenticated
  with check (exists (select 1 from public.admins a where a.email = auth.jwt()->>'email'));

revoke all on public.invites from anon, authenticated;
grant select, insert on public.invites to authenticated;
