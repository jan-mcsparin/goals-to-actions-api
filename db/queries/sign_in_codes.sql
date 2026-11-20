-- name: MakeCode :exec
insert into sign_in_codes (id, user_id, code_hash, expires_at)
values ($1, $2, $3, $4);
