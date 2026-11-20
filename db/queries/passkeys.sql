-- A credential already kept is left as it is.
-- name: AddPasskey :exec
insert into passkeys (id, user_id, credential_id, public_key, sign_count)
values ($1, $2, $3, $4, $5)
on conflict (credential_id) do nothing;
