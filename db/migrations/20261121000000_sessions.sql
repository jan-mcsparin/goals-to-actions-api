-- migrate:up

-- A signed-in device (ADR-012). The cookie holds a random token; this row holds only its
-- SHA-256, in hex. Ending a session sets deleted_at. No audit trigger: the log shouldn't
-- collect token hashes, or a row each day a session is used.
create table sessions (
  id uuid primary key,
  user_id uuid not null references users (id),
  token_hash text not null constraint sessions_token_hash_unique unique,
  -- Written at most once a day; the session lasts 90 days from it.
  last_used_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create trigger sessions_set_updated_at before update on sessions
  for each row execute function set_updated_at();

-- migrate:down

drop table sessions;
