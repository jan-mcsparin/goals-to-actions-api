-- migrate:up

-- One row for each week a task is in play. This is the plan: there is no separate plan table.
create table task_weeks (
  id uuid primary key,
  user_id uuid not null references users (id),
  task_id uuid not null,
  -- Named by its Monday.
  week date not null constraint task_weeks_week_is_monday check (extract(isodow from week) = 1),
  -- Empty means the task is in that week's bank.
  planned_day date,
  -- The person put it on its day. The planner never moves it.
  placed_by_hand boolean not null default false,
  -- Empty while the week is in play for the task.
  outcome text check (outcome in ('done', 'rolled_over', 'lapsed', 'dropped', 'set_aside')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint task_weeks_task_same_owner foreign key (task_id, user_id)
    references tasks (id, user_id),
  constraint task_weeks_day_in_week check (planned_day between week and week + 6),
  constraint task_weeks_placed_on_a_day check (not placed_by_hand or planned_day is not null),
  constraint task_weeks_one_per_week unique (task_id, week)
);

create unique index task_weeks_one_in_play on task_weeks (task_id)
  where outcome is null and deleted_at is null;

create trigger task_weeks_set_updated_at before update on task_weeks
  for each row execute function set_updated_at();

create trigger task_weeks_audit after insert or update or delete on task_weeks
  for each row execute function audit();

-- A task's state and its rows agree: a task that is done, dropped or lapsed has no row in
-- play, and a done task's last row is done. Checked at commit, since a write changes the task
-- and its row one after the other.
create function task_rows_agree() returns trigger
language plpgsql as $$
declare
  checked_task uuid;
  task_state text;
  last_outcome text;
begin
  if tg_table_name = 'tasks' then
    checked_task := new.id;
  elsif tg_op = 'DELETE' then
    checked_task := old.task_id;
  else
    checked_task := new.task_id;
  end if;

  select state into task_state from tasks where id = checked_task and deleted_at is null;
  if not found then
    return null;
  end if;

  if task_state <> 'open' and exists (
    select from task_weeks
    where task_id = checked_task and outcome is null and deleted_at is null
  ) then
    raise exception 'A % task can''t have a row in play.', task_state
      using errcode = 'check_violation', constraint = 'task_rows_agree';
  end if;

  if task_state = 'done' then
    select outcome into last_outcome from task_weeks
    where task_id = checked_task and deleted_at is null
    order by week desc limit 1;
    if last_outcome is distinct from 'done' then
      raise exception 'A done task''s last row is done.'
        using errcode = 'check_violation', constraint = 'task_rows_agree';
    end if;
  end if;

  return null;
end;
$$;

create constraint trigger tasks_rows_agree after insert or update on tasks
  deferrable initially deferred
  for each row execute function task_rows_agree();

create constraint trigger task_weeks_rows_agree after insert or update or delete on task_weeks
  deferrable initially deferred
  for each row execute function task_rows_agree();

-- migrate:down

drop trigger tasks_rows_agree on tasks;

drop table task_weeks;

drop function task_rows_agree;
