-- name: ListMilestones :many
select * from milestones
where goal_id = $1 and user_id = $2 and deleted_at is null
order by position;

-- name: GetMilestone :one
select * from milestones
where id = $1 and user_id = $2 and deleted_at is null;

-- Goes last among the goal's milestones. Returns nothing when the id is taken.
-- name: AddMilestone :one
insert into milestones (id, user_id, goal_id, goal_type, position, measurable_line, target_date)
select sqlc.arg(id), sqlc.arg(user_id), sqlc.arg(goal_id), sqlc.arg(goal_type),
  coalesce(max(position), 0) + 1, sqlc.arg(measurable_line), sqlc.narg(target_date)
from milestones
where goal_id = sqlc.arg(goal_id) and deleted_at is null
on conflict (id) do nothing
returning *;

-- A "not yet" edited (moved or adjusted) is upcoming again; a hit one stays hit.
-- name: UpdateMilestone :one
update milestones
set measurable_line = $3, target_date = $4,
  status = case when status = 'not_yet' then 'upcoming' else status end
where id = $1 and user_id = $2 and deleted_at is null
returning *;

-- name: SetMilestoneDate :exec
update milestones set target_date = $3
where id = $1 and user_id = $2 and deleted_at is null;

-- Numbers the goal's milestones in the order of the ids given.
-- name: SetMilestonePositions :exec
update milestones
set position = new_order.position
from unnest(sqlc.arg(ids)::uuid[]) with ordinality as new_order (id, position)
where milestones.id = new_order.id
  and milestones.goal_id = sqlc.arg(goal_id)
  and milestones.user_id = sqlc.arg(user_id)
  and milestones.deleted_at is null
  and milestones.position <> new_order.position;

-- name: SetMilestoneStatus :exec
update milestones set status = $3
where id = $1 and user_id = $2 and deleted_at is null;

-- Each of the owner's goals with milestones: how many, and how many are hit. One read for the list.
-- name: CountMilestones :many
select goal_id, count(*)::int as milestones, (count(*) filter (where status = 'hit'))::int as hit
from milestones
where user_id = $1 and deleted_at is null
group by goal_id;

-- A milestone of the owner's that has been deleted: deleting it again changes nothing.
-- name: MilestoneDeleted :one
select * from milestones
where id = $1 and user_id = $2 and deleted_at is not null;

-- name: DeleteMilestone :exec
update milestones set deleted_at = now()
where id = $1 and user_id = $2 and deleted_at is null;

-- Moves up the goal's milestones below a position that has just been left.
-- name: CloseMilestoneGap :exec
update milestones set position = position - 1
where goal_id = $1 and user_id = $2 and deleted_at is null and position > $3;
