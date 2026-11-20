-- migrate:up

-- A sign-in under way (ADR-012): the challenge the browser must sign, kept between the two
-- steps since the API holds nothing between requests. Deleted when used, gone in five minutes.
-- Only the columns it needs: it exists before anyone is known, so a sign-in's has no owner,
-- and it is never changed or audited.
create table sign_in_challenges (
  id uuid primary key,
  user_id uuid references users (id),
  kind text not null,
  -- base64url, as the browser sends it back.
  challenge text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  -- Adding a passkey is for the code's user; a sign-in finds its user from the passkey.
  constraint sign_in_challenges_kind_agrees check (
    (kind = 'add_passkey' and user_id is not null) or (kind = 'sign_in' and user_id is null)
  )
);

-- A passkey: its credential id and public key, base64url, as the WebAuthn library gives them.
-- Nothing secret. A person can have several.
create table passkeys (
  id uuid primary key,
  user_id uuid not null references users (id),
  credential_id text not null constraint passkeys_credential_id_unique unique,
  public_key text not null,
  sign_count bigint not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create trigger passkeys_set_updated_at before update on passkeys
  for each row execute function set_updated_at();

create trigger passkeys_audit after insert or update or delete on passkeys
  for each row execute function audit();

-- migrate:down

drop table passkeys;
drop table sign_in_challenges;
