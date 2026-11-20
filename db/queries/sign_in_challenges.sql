-- name: AddChallenge :exec
insert into sign_in_challenges (id, user_id, kind, challenge, expires_at)
values ($1, $2, $3, $4, $5);

-- Used once, even when what's signed with it is refused. No owner: it's how the owner is found.
-- name: TakeChallenge :one
delete from sign_in_challenges
where id = $1 and kind = $2
returning user_id, challenge, expires_at;
