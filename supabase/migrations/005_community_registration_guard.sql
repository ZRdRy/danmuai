-- DanmuAI community: registration rate-limit audit log (Edge Function service_role only).
-- Scope: community-site + community-register-guard. Not used by desktop config.db or main.py.

create table public.community_registration_logs (
  id uuid primary key default gen_random_uuid(),
  username text not null,
  auth_user_id uuid references auth.users (id) on delete set null,
  ip_hash text,
  device_hash text,
  user_agent_hash text,
  created_at timestamptz not null default now()
);

create index community_registration_logs_created_at_idx
  on public.community_registration_logs (created_at desc);

create index community_registration_logs_ip_created_idx
  on public.community_registration_logs (ip_hash, created_at desc)
  where ip_hash is not null;

create index community_registration_logs_device_created_idx
  on public.community_registration_logs (device_hash, created_at desc)
  where device_hash is not null;

create index community_registration_logs_username_idx
  on public.community_registration_logs (username);

comment on table public.community_registration_logs is
  'Registration audit for community-register-guard; no client access.';

alter table public.community_registration_logs enable row level security;

-- No policies: anon/authenticated cannot read or write via PostgREST.
revoke all on table public.community_registration_logs from anon, authenticated;
revoke all on table public.community_registration_logs from public;
grant select, insert on table public.community_registration_logs to service_role;

grant execute on function public.community_normalize_username(text) to service_role;
