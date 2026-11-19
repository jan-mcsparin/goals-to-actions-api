-- migrate:up

create table recurring_items (
  id uuid primary key,
  user_id uuid not null references users (id),
  name text not null constraint recurring_items_name_not_blank check (btrim(name) <> ''),
  -- With none, the item is maintenance and belongs to Keep life running.
  aspiration_id uuid,
  -- The goal whose practice this continues, when a reached goal is kept going.
  from_goal_id uuid,
  schedule_kind text not null check (schedule_kind in ('weekly', 'monthly', 'flexible')),
  -- ISO: Monday is 1.
  weekday smallint check (weekday between 1 and 7),
  -- Up to the 28th, so every month has the day.
  day_of_month smallint check (day_of_month between 1 and 28),
  times smallint check (times between 1 and 6),
  period text check (period in ('week', 'two_weeks', 'month')),
  -- The first day the item can be due; it also anchors a two-week period.
  starts_on date not null,
  -- Turned off by hand and paused by retiring its aspiration are one state.
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint recurring_items_aspiration_same_owner foreign key (aspiration_id, user_id)
    references aspirations (id, user_id),
  constraint recurring_items_from_goal_same_owner foreign key (from_goal_id, user_id)
    references goals (id, user_id),
  -- Each kind fills its own schedule columns and leaves the rest empty.
  constraint recurring_items_schedule_fits_kind check (
    case schedule_kind
      when 'weekly' then weekday is not null and day_of_month is null
        and times is null and period is null
      when 'monthly' then day_of_month is not null and weekday is null
        and times is null and period is null
      when 'flexible' then times is not null and period is not null
        and weekday is null and day_of_month is null
    end
  ),
  -- Several times only in a week: every two weeks and every month are once.
  constraint recurring_items_once_in_a_longer_period check (period = 'week' or times = 1),
  -- So a task can name its item together with its owner.
  constraint recurring_items_id_owner unique (id, user_id)
);

create trigger recurring_items_set_updated_at before update on recurring_items
  for each row execute function set_updated_at();

create trigger recurring_items_audit after insert or update or delete on recurring_items
  for each row execute function audit();

alter table tasks add constraint tasks_item_same_owner foreign key (recurring_item_id, user_id)
  references recurring_items (id, user_id);

-- migrate:down

alter table tasks drop constraint tasks_item_same_owner;

drop table recurring_items;
