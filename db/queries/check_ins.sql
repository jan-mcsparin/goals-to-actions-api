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
