-- "Latest" on a goal's page: its most recent check-in with a result.
-- name: LatestResult :one
select * from check_ins
where goal_id = $1 and user_id = $2 and result is not null and deleted_at is null
order by checked_in_on desc, created_at desc
limit 1;

-- name: GetCheckIn :one
select * from check_ins
where id = $1 and user_id = $2 and deleted_at is null;

-- Returns nothing when the id is taken.
-- name: AddCheckIn :one
insert into check_ins (id, user_id, goal_id, milestone_id, outcome, result, checked_in_on)
values ($1, $2, $3, $4, $5, $6, $7)
on conflict (id) do nothing
returning *;

-- The result of each of a goal's checked-in milestones: its latest check-in's, hit or not yet.
-- A hit is always a milestone's last check-in, so it comes first.
-- name: MilestoneResults :many
select distinct on (milestone_id) milestone_id, result from check_ins
where goal_id = $1 and user_id = $2 and milestone_id is not null and deleted_at is null
order by milestone_id, outcome = 'hit' desc, checked_in_on desc, created_at desc;

-- A deleted milestone's check-ins go with it.
-- name: DeleteMilestoneCheckIns :exec
update check_ins set deleted_at = now()
where milestone_id = $1 and user_id = $2 and deleted_at is null;

-- name: DeleteGoalCheckIns :exec
update check_ins set deleted_at = now()
where goal_id = $1 and user_id = $2 and deleted_at is null;
