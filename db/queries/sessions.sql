-- name: StartSession :exec
insert into sessions (id, user_id, token_hash, last_used_at)
values ($1, $2, $3, $4);

-- The one read without an owner: the token is how the owner is found.
-- name: FindSession :one
select id, user_id, last_used_at
from sessions
where token_hash = $1 and deleted_at is null;

-- name: TouchSession :exec
update sessions set last_used_at = $3
where id = $1 and user_id = $2 and deleted_at is null;
