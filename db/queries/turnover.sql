-- Every generated task's place, deleted ones too, so a deleted session isn't made again.
-- name: ListGeneratedSlots :many
select goal_id, recurring_item_id, period_start, number from tasks
where user_id = $1 and period_start >= $2;

-- A task a goal or item makes for a period. A second writer's identical task is ignored.
-- name: AddGeneratedTask :one
insert into tasks (id, user_id, title, origin, goal_id, recurring_item_id, period_start, number)
values ($1, $2, $3, $4, $5, $6, $7, $8)
on conflict do nothing
returning *;

-- Open tasks added by hand that are due by the end of the week and have no row yet:
-- not under a goal that isn't active.
-- name: ListDueTasksWithoutRows :many
select tasks.id from tasks
left join goals on goals.id = tasks.goal_id and goals.deleted_at is null
where tasks.user_id = $1 and tasks.origin = 'by_hand' and tasks.state = 'open'
  and tasks.due_date is not null and tasks.due_date <= $2 and tasks.deleted_at is null
  and (tasks.goal_id is null or goals.status = 'active')
  and not exists (
    select 1 from task_weeks where task_weeks.task_id = tasks.id and task_weeks.deleted_at is null
  )
order by tasks.due_date, tasks.created_at, tasks.id;
