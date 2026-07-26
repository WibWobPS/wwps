-- Upgrade for servers created before the admin audit log and the lookup
-- indexes existed. Safe to run repeatedly.

create table if not exists public.ban (
  gdkey text primary key,
  reason text,
  banned_at timestamptz default now()
);

create table if not exists public.admin_audit (
  id bigserial primary key,
  action text not null,
  gdkey text,
  detail text,
  actor text,
  created_at timestamptz not null default now()
);

create index if not exists account_udkey_idx on public.account (udkey);
create index if not exists account_last_lgn_time_idx
  on public.account (last_lgn_time desc nulls last);
create index if not exists admin_audit_created_at_idx
  on public.admin_audit (created_at desc);
