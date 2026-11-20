-- migrate:up

-- A one-time code (ADR-012): made by a command run inside AWS, typed into the app to add a
-- passkey. Only its SHA-256 is kept, in hex. Used once, gone in ten minutes. Audited: the log
-- records who was given a code and when; the hash of a spent ten-minute code is no use.
create table sign_in_codes (
  id uuid primary key,
  user_id uuid not null references users (id),
  code_hash text not null constraint sign_in_codes_code_hash_unique unique,
  expires_at timestamptz not null,
  used_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create trigger sign_in_codes_set_updated_at before update on sign_in_codes
  for each row execute function set_updated_at();

create trigger sign_in_codes_audit after insert or update or delete on sign_in_codes
  for each row execute function audit();

-- migrate:down

drop table sign_in_codes;
