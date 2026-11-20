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

-- The rows closing a week up to `$2` has to settle, oldest week first: rows still in play,
-- and set-aside rows that are their task's latest. Weeks closed already (`$3` and before)
-- are left alone.
-- name: ListRowsToClose :many
select task_weeks.*, tasks.origin, tasks.period_start,
  items.schedule_kind as item_kind, items.period as item_period
from task_weeks
join tasks on tasks.id = task_weeks.task_id and tasks.state = 'open' and tasks.deleted_at is null
left join recurring_items items on items.id = tasks.recurring_item_id
where task_weeks.user_id = sqlc.arg(user_id) and task_weeks.week <= sqlc.arg(through)::date and task_weeks.week > sqlc.arg(after)::date
  and task_weeks.deleted_at is null
  and (
    task_weeks.outcome is null
    or (task_weeks.outcome = 'set_aside' and not exists (
      select 1 from task_weeks later
      where later.task_id = task_weeks.task_id and later.week > task_weeks.week
        and later.deleted_at is null
    ))
  )
order by task_weeks.week, tasks.created_at, tasks.id;

-- Every session a goal made for a week, with its row in that week.
-- name: ListGoalSessionsInWeek :many
select tasks.id as task_id, tasks.number, tasks.state, task_weeks.planned_day, task_weeks.outcome
from tasks
join task_weeks on task_weeks.task_id = tasks.id and task_weeks.week = $3
  and task_weeks.deleted_at is null
where tasks.goal_id = $1 and tasks.user_id = $2 and tasks.origin = 'weekly_target'
  and tasks.period_start = $3 and tasks.deleted_at is null;
