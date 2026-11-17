-- name: GetGoal :one
select * from goals
where id = $1 and user_id = $2 and deleted_at is null;

-- Under active aspirations by priority, then under retired ones, newest retirement first,
-- then goals with no aspiration; within each, oldest first.
-- name: ListGoals :many
select goals.* from goals
left join aspirations on aspirations.id = goals.aspiration_id
where goals.user_id = $1 and goals.deleted_at is null
order by goals.aspiration_id is null, aspirations.position nulls last,
  aspirations.retired_on desc, goals.aspiration_id, goals.created_at, goals.id;

-- Returns nothing when the id is taken.
-- name: CreateGoal :one
insert into goals (
  id, user_id, aspiration_id, type, label, measurable_line, baseline, start_date, deadline
) values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
on conflict (id) do nothing
returning *;

-- name: UpdateGoal :one
update goals
set label = $3, measurable_line = $4, baseline = $5, aspiration_id = $6, deadline = $7
where id = $1 and user_id = $2 and deleted_at is null
returning *;

-- name: SetGoalStatus :one
update goals set status = $3, ended_on = $4
where id = $1 and user_id = $2 and deleted_at is null
returning *;
