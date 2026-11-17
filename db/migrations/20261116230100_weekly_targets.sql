-- migrate:up

-- Building goals only. A change adds a row, so earlier weeks keep the target they had.
create table weekly_targets (
  id uuid primary key,
  user_id uuid not null references users (id),
  goal_id uuid not null,
  -- Always 'building': with the foreign key below, the database refuses a target on any other
  -- type of goal, or on another owner's.
  goal_type text not null default 'building' check (goal_type = 'building'),
  kind text not null check (kind in ('count', 'amount')),
  -- How many tasks the week gets.
  sessions integer not null check (sessions between 1 and 14),
  -- Amount targets only: the total to reach, in the unit.
  amount numeric,
  unit text not null constraint weekly_targets_unit_not_blank check (btrim(unit) <> ''),
  -- A week, named by its Monday.
  effective_from date not null
    constraint weekly_targets_week_is_a_monday check (extract(isodow from effective_from) = 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint weekly_targets_building_goal_same_owner foreign key (goal_id, user_id, goal_type)
    references goals (id, user_id, type),
  constraint weekly_targets_amount_agrees check (
    (kind = 'amount') = (amount is not null) and amount > 0
  ),
  -- A second change in the same week replaces the first.
  constraint weekly_targets_one_per_week unique (goal_id, effective_from)
);

create trigger weekly_targets_set_updated_at before update on weekly_targets
  for each row execute function set_updated_at();

create trigger weekly_targets_audit after insert or update or delete on weekly_targets
  for each row execute function audit();

-- migrate:down

drop table weekly_targets;
