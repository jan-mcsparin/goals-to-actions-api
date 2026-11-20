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

-- Numbers the owner's active aspirations in the order of the ids given.
-- name: SetAspirationPositions :exec
update aspirations
set position = new_order.position
from unnest(sqlc.arg(ids)::uuid[]) with ordinality as new_order (id, position)
where aspirations.id = new_order.id
  and aspirations.user_id = sqlc.arg(user_id)
  and aspirations.status = 'active'
  and aspirations.deleted_at is null
  and aspirations.position <> new_order.position;

-- name: UpdateAspiration :one
update aspirations set name = $3, why = $4
where id = $1 and user_id = $2 and deleted_at is null
returning *;

-- Changes nothing, and returns nothing, when it's already retired.
-- name: RetireAspiration :one
update aspirations set status = 'retired', position = null, retired_on = $3
where id = $1 and user_id = $2 and status = 'active' and deleted_at is null
returning *;

-- Moves up the owner's active aspirations below a position that has just been left.
-- name: CloseAspirationGap :exec
update aspirations set position = position - 1
where user_id = $1 and status = 'active' and deleted_at is null and position > $2;

-- Goes last among the owner's active aspirations. Changes nothing, and returns nothing,
-- when it's already active.
-- name: BringBackAspiration :one
update aspirations
set status = 'active',
  retired_on = null,
  position = (
    select coalesce(max(active.position), 0) + 1
    from aspirations active
    where active.user_id = $2 and active.status = 'active' and active.deleted_at is null
  )
where aspirations.id = $1
  and aspirations.user_id = $2
  and aspirations.status = 'retired'
  and aspirations.deleted_at is null
returning *;

-- An aspiration of the owner's that has been deleted: deleting it again changes nothing.
-- name: AspirationDeleted :one
select * from aspirations
where id = $1 and user_id = $2 and deleted_at is not null;

-- name: DeleteAspiration :exec
update aspirations set deleted_at = now()
where id = $1 and user_id = $2 and deleted_at is null;
