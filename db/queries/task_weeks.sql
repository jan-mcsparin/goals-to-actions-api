-- name: ListTaskWeeks :many
select * from task_weeks
where task_id = $1 and user_id = $2 and deleted_at is null
order by week;

-- name: AddTaskWeek :exec
insert into task_weeks (id, user_id, task_id, week, planned_day, placed_by_hand, outcome)
values ($1, $2, $3, $4, $5, $6, $7);
