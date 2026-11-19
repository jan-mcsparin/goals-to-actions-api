-- name: ListTaskWeeks :many
select * from task_weeks
where task_id = $1 and user_id = $2 and deleted_at is null
order by week;
