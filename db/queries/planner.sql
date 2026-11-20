-- The recurring tasks the planner is handed that are still in a week's bank, each with what
-- places it: its goal or item, its schedule, its start, and its aspiration if that's active.
-- Tasks added by hand never come back from here, so they are never placed; nor does a task
-- whose goal or item is gone.
-- name: ListPlacementContext :many
select tasks.id as task_id, tasks.goal_id, tasks.recurring_item_id, task_weeks.week,
  items.schedule_kind as item_kind, items.weekday, items.day_of_month,
  items.aspiration_id as item_aspiration_id,
  coalesce(goals.start_date, items.starts_on)::date as starts_on,
  coalesce(goals.created_at, items.created_at)::timestamptz as made_at,
  aspirations.position as aspiration_position
from tasks
join task_weeks on task_weeks.task_id = tasks.id and task_weeks.deleted_at is null
  and task_weeks.outcome is null and task_weeks.planned_day is null
  and not task_weeks.placed_by_hand
left join goals on goals.id = tasks.goal_id and goals.deleted_at is null
left join recurring_items items on items.id = tasks.recurring_item_id
  and items.deleted_at is null
left join aspirations on aspirations.id = coalesce(goals.aspiration_id, items.aspiration_id)
  and aspirations.status = 'active' and aspirations.deleted_at is null
where tasks.user_id = sqlc.arg(user_id) and tasks.id = any(sqlc.arg(task_ids)::uuid[])
  and tasks.origin in ('weekly_target', 'recurring_item') and tasks.deleted_at is null
  and (goals.id is not null or items.id is not null)
order by task_weeks.week, tasks.number, tasks.id;

-- A week's tasks that are open or done, and where each is: on a day, or in the bank. What
-- the planner counts as a day's load, and the full-day mark.
-- name: ListWeekPlaces :many
select task_weeks.task_id, tasks.goal_id, tasks.recurring_item_id, task_weeks.planned_day
from task_weeks
join tasks on tasks.id = task_weeks.task_id and tasks.deleted_at is null
where task_weeks.user_id = $1 and task_weeks.week = $2 and task_weeks.deleted_at is null
  and (task_weeks.outcome is null or task_weeks.outcome = 'done');

-- Puts a recurring task that's still in a week's bank on a day: the planner's write, and a
-- new fixed-day item's task due today. It changes nothing for a row placed by hand, one
-- already on a day or settled, or a day before `first_day`: after a week's first placement,
-- the planner passes tomorrow, so today and earlier days only change because of something
-- the person did.
-- name: PlaceGeneratedTask :execrows
update task_weeks set planned_day = sqlc.arg(day)::date
where task_id = sqlc.arg(task_id) and user_id = sqlc.arg(user_id)
  and week = sqlc.arg(week)::date and deleted_at is null
  and planned_day is null and not placed_by_hand and outcome is null
  and sqlc.arg(day)::date >= sqlc.arg(first_day)::date;
