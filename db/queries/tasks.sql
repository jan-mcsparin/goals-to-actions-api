-- name: GetTask :one
select * from tasks
where id = $1 and user_id = $2 and deleted_at is null;

-- Returns nothing when the id is taken.
-- name: AddTask :one
insert into tasks (id, user_id, title, origin, goal_id, due_date, time_kind, time_of_day)
values ($1, $2, $3, 'by_hand', $4, $5, $6, $7)
on conflict (id) do nothing
returning *;

-- A task as the screens show it: with its goal's label, how often it has carried over, and
-- its row in play, or its done row. A task that's waiting, or set aside, has no week.
-- name: GetTaskView :one
select tasks.*, shown.week, shown.planned_day, shown.placed_by_hand,
  goals.label as goal_label,
  items.schedule_kind as item_kind, items.period as item_period,
  (select count(*) from task_weeks rolled
    where rolled.task_id = tasks.id and rolled.outcome = 'rolled_over'
      and rolled.deleted_at is null
      and (tasks.still_matters_answered_on is null
        or rolled.week + 6 >= tasks.still_matters_answered_on))::integer as rolled_since_answer,
  (select count(*) from task_weeks carried
    where carried.task_id = tasks.id and carried.outcome = 'rolled_over'
      and carried.week < coalesce(shown.week, 'infinity'::date)
      and carried.deleted_at is null)::integer as carried_over
from tasks
left join task_weeks shown on shown.id = (
  select task_weeks.id from task_weeks
  where task_weeks.task_id = tasks.id and task_weeks.deleted_at is null
    and (task_weeks.outcome is null or task_weeks.outcome = 'done')
  order by task_weeks.week desc
  limit 1
)
left join goals on goals.id = tasks.goal_id and goals.deleted_at is null
left join recurring_items items on items.id = tasks.recurring_item_id
where tasks.id = $1 and tasks.user_id = $2 and tasks.deleted_at is null;

-- The week read: the week's rows in play or done, by day, then the bank; timed tasks first
-- within a day.
-- name: ListWeekTasks :many
select tasks.*, task_weeks.week, task_weeks.planned_day, task_weeks.placed_by_hand,
  goals.label as goal_label,
  items.schedule_kind as item_kind, items.period as item_period,
  (select count(*) from task_weeks rolled
    where rolled.task_id = tasks.id and rolled.outcome = 'rolled_over'
      and rolled.deleted_at is null
      and (tasks.still_matters_answered_on is null
        or rolled.week + 6 >= tasks.still_matters_answered_on))::integer as rolled_since_answer,
  (select count(*) from task_weeks carried
    where carried.task_id = tasks.id and carried.outcome = 'rolled_over'
      and carried.week < task_weeks.week and carried.deleted_at is null)::integer as carried_over
from task_weeks
join tasks on tasks.id = task_weeks.task_id and tasks.deleted_at is null
left join goals on goals.id = tasks.goal_id and goals.deleted_at is null
left join recurring_items items on items.id = tasks.recurring_item_id
where task_weeks.user_id = $1 and task_weeks.week = $2 and task_weeks.deleted_at is null
  and (task_weeks.outcome is null or task_weeks.outcome = 'done')
order by task_weeks.planned_day nulls last, tasks.time_of_day nulls last, tasks.created_at,
  tasks.id;

-- name: UpdateTask :one
update tasks set title = $3, due_date = $4, time_kind = $5, time_of_day = $6
where id = $1 and user_id = $2 and deleted_at is null
returning *;

-- name: SetTaskDone :exec
update tasks
set state = 'done', completed_at = $3, completed_on = $4, value_logged = $5
where id = $1 and user_id = $2 and deleted_at is null;

-- Open again: unchecked, or brought back. The completion and the value logged go with it.
-- name: SetTaskOpen :exec
update tasks
set state = 'open', completed_at = null, completed_on = null, value_logged = null
where id = $1 and user_id = $2 and deleted_at is null;

-- What each goal's tasks did in a week: a task counts for the week of the row it was done
-- in, not the day it was checked off.
-- name: WeekDone :many
select tasks.goal_id::uuid as goal_id, count(*)::integer as done,
  coalesce(sum(tasks.value_logged), 0)::numeric as logged
from task_weeks
join tasks on tasks.id = task_weeks.task_id and tasks.deleted_at is null
where task_weeks.user_id = $1 and task_weeks.week = $2 and task_weeks.outcome = 'done'
  and task_weeks.deleted_at is null and tasks.goal_id is not null
group by tasks.goal_id;

-- A one-off goal's steps: its tasks that weren't dropped.
-- name: CountSteps :many
select tasks.goal_id::uuid as goal_id, count(*)::integer as steps,
  (count(*) filter (where tasks.state = 'done'))::integer as done
from tasks
join goals on goals.id = tasks.goal_id and goals.type = 'one_off'
where tasks.user_id = $1 and tasks.state <> 'dropped' and tasks.deleted_at is null
group by tasks.goal_id;

-- A one-off goal's steps as its page lists them, in the order they were added.
-- name: ListSteps :many
select tasks.*, shown.week, shown.planned_day, shown.placed_by_hand,
  goals.label as goal_label,
  items.schedule_kind as item_kind, items.period as item_period,
  (select count(*) from task_weeks rolled
    where rolled.task_id = tasks.id and rolled.outcome = 'rolled_over'
      and rolled.deleted_at is null
      and (tasks.still_matters_answered_on is null
        or rolled.week + 6 >= tasks.still_matters_answered_on))::integer as rolled_since_answer,
  (select count(*) from task_weeks carried
    where carried.task_id = tasks.id and carried.outcome = 'rolled_over'
      and carried.week < coalesce(shown.week, 'infinity'::date)
      and carried.deleted_at is null)::integer as carried_over
from tasks
left join task_weeks shown on shown.id = (
  select task_weeks.id from task_weeks
  where task_weeks.task_id = tasks.id and task_weeks.deleted_at is null
    and (task_weeks.outcome is null or task_weeks.outcome = 'done')
  order by task_weeks.week desc
  limit 1
)
join goals on goals.id = tasks.goal_id
left join recurring_items items on items.id = tasks.recurring_item_id
where tasks.goal_id = $1 and tasks.user_id = $2 and tasks.state <> 'dropped'
  and tasks.deleted_at is null
order by tasks.created_at, tasks.id;

-- Dropped or lapsed: closed without being done.
-- name: SetTaskClosed :exec
update tasks set state = $3
where id = $1 and user_id = $2 and deleted_at is null;

-- name: GoalWeekDone :one
select count(*)::integer as done, coalesce(sum(tasks.value_logged), 0)::numeric as logged
from task_weeks
join tasks on tasks.id = task_weeks.task_id and tasks.deleted_at is null
where task_weeks.user_id = $1 and task_weeks.week = $2 and task_weeks.outcome = 'done'
  and task_weeks.deleted_at is null and tasks.goal_id = $3;

-- Open tasks added by hand with a due date and no row yet: they join a week's bank when
-- that week is opened.
-- name: ListUpcoming :many
select tasks.*, null::date as week, null::date as planned_day, false as placed_by_hand,
  goals.label as goal_label,
  null::text as item_kind, null::text as item_period, 0::integer as rolled_since_answer,
  0::integer as carried_over
from tasks
left join goals on goals.id = tasks.goal_id and goals.deleted_at is null
where tasks.user_id = $1 and tasks.origin = 'by_hand' and tasks.state = 'open'
  and tasks.due_date is not null and tasks.deleted_at is null
  and not exists (
    select 1 from task_weeks where task_weeks.task_id = tasks.id and task_weeks.deleted_at is null
  )
order by tasks.due_date, tasks.created_at, tasks.id;

-- "Still matter?" answered with keep or a day: the count of rollovers starts again.
-- name: SetStillMattersAnswered :exec
update tasks set still_matters_answered_on = $3
where id = $1 and user_id = $2 and deleted_at is null;
