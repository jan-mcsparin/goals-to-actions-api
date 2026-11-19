-- migrate:up

-- Something you do: added by hand, or made from a weekly target or a recurring item. One row
-- for its whole life; each week it's in play is a row in task_weeks (ADR-006).
create table tasks (
  id uuid primary key,
  user_id uuid not null references users (id),
  title text not null constraint tasks_title_not_blank check (btrim(title) <> ''),
  -- Decides what happens when the task isn't finished by the end of its week.
  origin text not null check (origin in ('by_hand', 'weekly_target', 'recurring_item')),
  goal_id uuid,
  -- The foreign key is added by recurring_items. Deleting an item empties this on its done
  -- tasks, which keep their origin.
  recurring_item_id uuid,
  state text not null default 'open' check (state in ('open', 'done', 'dropped', 'lapsed')),
  -- A real constraint, unlike the planned day.
  due_date date,
  time_kind text check (time_kind in ('by', 'at')),
  time_of_day time,
  -- Miles, minutes: counts towards an amount target, in the target's unit.
  value_logged numeric check (value_logged >= 0),
  -- The moment the phone recorded the check-off, and the day it counts for as the phone saw it.
  completed_at timestamptz,
  completed_on date,
  -- Generated tasks only: the week or period the task is for, and which of its tasks it is.
  period_start date,
  number integer check (number >= 1),
  -- When "Still matter?" was last answered Keep or Reschedule.
  still_matters_answered_on date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint tasks_goal_same_owner foreign key (goal_id, user_id)
    references goals (id, user_id),
  constraint tasks_goal_or_item check (goal_id is null or recurring_item_id is null),
  constraint tasks_weekly_target_has_goal check (origin <> 'weekly_target' or goal_id is not null),
  constraint tasks_item_means_its_origin check (
    recurring_item_id is null or origin = 'recurring_item'
  ),
  constraint tasks_generated_has_period check (
    (origin = 'by_hand') = (period_start is null) and (period_start is null) = (number is null)
  ),
  constraint tasks_time_kind_and_time check ((time_kind is null) = (time_of_day is null)),
  constraint tasks_done_has_completion check (
    (state = 'done') = (completed_on is not null)
    and (completed_on is null) = (completed_at is null)
    and (value_logged is null or state = 'done')
  ),
  -- Deleted rows count too, so a deleted session is never made again.
  constraint tasks_goal_period_number unique (goal_id, period_start, number),
  constraint tasks_item_period_number unique (recurring_item_id, period_start, number),
  -- So a task_weeks row can name its task together with its owner.
  constraint tasks_id_owner unique (id, user_id)
);

create trigger tasks_set_updated_at before update on tasks
  for each row execute function set_updated_at();

create trigger tasks_audit after insert or update or delete on tasks
  for each row execute function audit();

-- migrate:down

drop table tasks;
