-- "Latest" on a goal's page: its most recent check-in with a result.
-- name: LatestResult :one
select * from check_ins
where goal_id = $1 and user_id = $2 and result is not null and deleted_at is null
order by checked_in_on desc, created_at desc
limit 1;
