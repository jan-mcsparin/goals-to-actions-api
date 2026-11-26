-- name: GetTask :one
select * from tasks
where id = $1 and user_id = $2 and deleted_at is null;

-- A task of the owner's that has been deleted: deleting it again changes nothing.
-- name: TaskDeleted :one
select * from tasks
where id = $1 and user_id = $2 and deleted_at is not null;

-- Hidden everywhere. It stays in the database, so a deleted session isn't made again.
-- name: DeleteTask :exec
update tasks set deleted_at = now()
where id = $1 and user_id = $2 and deleted_at is null;

-- Returns nothing when the id is taken.
-- name: AddTask :one
insert into tasks (id, user_id, title, origin, goal_id, due_date, time_kind, time_of_day)
values ($1, $2, $3, 'by_hand', $4, $5, $6, $7)
on conflict (id) do nothing
returning *;

-- A task as the screens show it: with its goal's label, its aspiration (its goal's, or for a
-- recurring item's task with no goal, the item's), how often it has carried over, and
-- its row in play, or its done row. A task that's waiting, or set aside, has no week.
-- name: GetTaskView :one
select tasks.*, shown.week, shown.planned_day, shown.placed_by_hand,
  null::text as week_outcome,
  goals.label as goal_label,
  aspirations.id as aspiration_id, aspirations.name as aspiration_name,
  aspirations.position as aspiration_position,
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
left join aspirations on aspirations.id = coalesce(goals.aspiration_id, items.aspiration_id)
  and aspirations.deleted_at is null
where tasks.id = $1 and tasks.user_id = $2 and tasks.deleted_at is null;

-- The week read: the week's rows in play, done, rolled over or lapsed (spec `any-week`), by
-- day, then the bank; timed tasks first within a day.
-- name: ListWeekTasks :many
select tasks.*, task_weeks.week, task_weeks.planned_day, task_weeks.placed_by_hand,
  task_weeks.outcome as week_outcome,
  goals.label as goal_label,
  aspirations.id as aspiration_id, aspirations.name as aspiration_name,
  aspirations.position as aspiration_position,
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
left join aspirations on aspirations.id = coalesce(goals.aspiration_id, items.aspiration_id)
  and aspirations.deleted_at is null
where task_weeks.user_id = $1 and task_weeks.week = $2 and task_weeks.deleted_at is null
  and (task_weeks.outcome is null or task_weeks.outcome in ('done', 'rolled_over', 'lapsed'))
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
  null::text as week_outcome,
  goals.label as goal_label,
  aspirations.id as aspiration_id, aspirations.name as aspiration_name,
  aspirations.position as aspiration_position,
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
left join aspirations on aspirations.id = goals.aspiration_id
  and aspirations.deleted_at is null
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
  null::text as week_outcome,
  goals.label as goal_label,
  aspirations.id as aspiration_id, aspirations.name as aspiration_name,
  aspirations.position as aspiration_position,
  null::text as item_kind, null::text as item_period, 0::integer as rolled_since_answer,
  0::integer as carried_over
from tasks
left join goals on goals.id = tasks.goal_id and goals.deleted_at is null
left join aspirations on aspirations.id = goals.aspiration_id
  and aspirations.deleted_at is null
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

-- A deleted item's open tasks go with it.
-- name: DeleteItemOpenTasks :exec
update tasks set deleted_at = now()
where recurring_item_id = $1 and user_id = $2 and state = 'open' and deleted_at is null;

-- A deleted item's other tasks stay as history, with the origin `recurring_item` and no item.
-- name: UnlinkItemTasks :exec
update tasks set recurring_item_id = null
where recurring_item_id = $1 and user_id = $2 and deleted_at is null;

-- A deleted goal's tasks go with it, whatever their state.
-- name: DeleteGoalTasks :exec
update tasks set deleted_at = now()
where goal_id = $1 and user_id = $2 and deleted_at is null;

-- An edited item's open tasks take its new name; done, dropped and lapsed ones keep theirs.
-- name: RenameItemOpenTasks :exec
update tasks set title = $3
where recurring_item_id = $1 and user_id = $2 and state = 'open' and deleted_at is null;

-- Every key an item's tasks hold, deleted ones too: keys are never used twice.
-- name: ListItemSlots :many
select period_start, number from tasks
where recurring_item_id = $1 and user_id = $2;

-- A generated task counted as another period's or number (an edited item's schedule).
-- name: SetTaskSlot :exec
update tasks set period_start = $3, number = $4
where id = $1 and user_id = $2;

-- The owner's earliest row, whatever its outcome: its week is how far back Week can go.
-- name: FirstRow :one
select * from task_weeks
where user_id = $1 and deleted_at is null
order by week
limit 1;
