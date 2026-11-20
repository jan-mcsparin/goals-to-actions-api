-- A credential already kept is left as it is.
-- name: AddPasskey :exec
insert into passkeys (id, user_id, credential_id, public_key, sign_count)
values ($1, $2, $3, $4, $5)
on conflict (credential_id) do nothing;

-- No owner: the passkey is how the owner is found.
-- name: FindPasskey :one
select id, user_id, public_key, sign_count
from passkeys
where credential_id = $1 and deleted_at is null;

-- name: SetSignCount :exec
update passkeys set sign_count = $3
where id = $1 and user_id = $2 and deleted_at is null;
