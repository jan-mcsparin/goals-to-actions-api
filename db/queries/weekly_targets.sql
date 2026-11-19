-- The goal's target from the latest week it was set for.
-- name: LatestWeeklyTarget :one
select * from weekly_targets
where goal_id = $1 and user_id = $2 and deleted_at is null
order by effective_from desc
limit 1;

-- Each of the owner's goals' latest target.
-- name: LatestWeeklyTargets :many
select distinct on (goal_id) * from weekly_targets
where user_id = $1 and deleted_at is null
order by goal_id, effective_from desc;

-- A second change in the same week replaces the first. The same target again changes
-- nothing, and returns nothing.
-- name: SetWeeklyTarget :one
insert into weekly_targets (id, user_id, goal_id, kind, sessions, amount, unit, effective_from)
values ($1, $2, $3, $4, $5, $6, $7, $8)
on conflict (goal_id, effective_from) do update
set kind = excluded.kind, sessions = excluded.sessions, amount = excluded.amount,
  unit = excluded.unit
where (weekly_targets.kind, weekly_targets.sessions, weekly_targets.amount, weekly_targets.unit)
  is distinct from (excluded.kind, excluded.sessions, excluded.amount, excluded.unit)
returning *;

-- Each of the owner's goals' target for a week: the one set latest on or before it.
-- name: WeeklyTargetsFor :many
select distinct on (goal_id) * from weekly_targets
where user_id = $1 and effective_from <= $2 and deleted_at is null
order by goal_id, effective_from desc;

-- One goal's target for a week: the one set latest on or before it.
-- name: GoalWeeklyTargetFor :one
select * from weekly_targets
where goal_id = $1 and user_id = $2 and effective_from <= $3 and deleted_at is null
order by effective_from desc
limit 1;
