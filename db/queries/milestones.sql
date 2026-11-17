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
