-- migrate:up

-- Expired challenges are cleared each time one is made: starting a sign-in needs no session,
-- so its rows can't be left to pile up.
create index sign_in_challenges_expires_at on sign_in_challenges (expires_at);

-- migrate:down

drop index sign_in_challenges_expires_at;
