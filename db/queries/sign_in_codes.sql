-- name: MakeCode :exec
insert into sign_in_codes (id, user_id, code_hash, expires_at)
values ($1, $2, $3, $4);

-- No owner: the code is how the owner is found.
-- name: FindCode :one
select id, user_id
from sign_in_codes
where code_hash = $1 and deleted_at is null;

-- Spent in one statement, so two devices typing the same code can't both use it.
-- name: SpendCode :one
update sign_in_codes set used_at = $3
where id = $1 and user_id = $2 and used_at is null and expires_at > $3 and deleted_at is null
returning id, user_id;
