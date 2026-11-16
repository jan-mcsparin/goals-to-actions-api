-- Active by priority, then retired with the newest first.
-- name: ListAspirations :many
select * from aspirations
where user_id = $1 and deleted_at is null
order by position nulls last, retired_on desc, name;

-- name: GetAspiration :one
select * from aspirations
where id = $1 and user_id = $2 and deleted_at is null;

-- Goes last among the owner's active aspirations. Returns nothing when the id is taken.
-- name: CreateAspiration :one
insert into aspirations (id, user_id, name, why, position)
select $1, $2, $3, $4, coalesce(max(position), 0) + 1
from aspirations
where user_id = $2 and status = 'active' and deleted_at is null
on conflict (id) do nothing
returning *;
