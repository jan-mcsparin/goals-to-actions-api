-- name: ListTaskWeeks :many
select * from task_weeks
where task_id = $1 and user_id = $2 and deleted_at is null
order by week;

-- name: AddTaskWeek :exec
insert into task_weeks (id, user_id, task_id, week, planned_day, placed_by_hand, outcome)
values ($1, $2, $3, $4, $5, $6, $7);

-- name: SetTaskWeek :exec
update task_weeks set planned_day = $3, placed_by_hand = $4, outcome = $5
where id = $1 and user_id = $2 and deleted_at is null;

-- Every row of a goal's open tasks, each with its task's origin, oldest week first.
-- name: ListGoalTaskWeeks :many
select task_weeks.*, tasks.origin from task_weeks
join tasks on tasks.id = task_weeks.task_id and tasks.state = 'open' and tasks.deleted_at is null
where tasks.goal_id = $1 and task_weeks.user_id = $2 and task_weeks.deleted_at is null
order by task_weeks.task_id, task_weeks.week;
