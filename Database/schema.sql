create table if not exists public.account (
  gdkey text primary key,
  ywp_user_tables jsonb,
  last_lgn_time text,
  opening_tutorial_flag boolean,
  start_date text,
  character_id text unique,
  user_id text unique,
  udkey text
);

create table if not exists public.device (
  udkey text primary key,
  gdkeys text[] not null
);

create table if not exists public.mail (
  mail text primary key,
  "currentUdkey" text
);

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

-- The ownership check and the device save list read accounts by device.
create index if not exists account_udkey_idx on public.account (udkey);
-- The admin player list orders by last login.
create index if not exists account_last_lgn_time_idx
  on public.account (last_lgn_time desc nulls last);
create index if not exists admin_audit_created_at_idx
  on public.admin_audit (created_at desc);
