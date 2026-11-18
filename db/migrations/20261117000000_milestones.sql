-- migrate:up

-- Benchmarks on building and quitting goals. The goal itself is the final milestone and
-- isn't stored as one.
create table milestones (
  id uuid primary key,
  user_id uuid not null references users (id),
  goal_id uuid not null,
  -- With the foreign key below, the database refuses a milestone on a one-off goal, or on
  -- another owner's goal.
  goal_type text not null check (goal_type in ('building', 'quitting')),
  -- The order they're checked in: 1, 2, 3 within the goal. Dates are optional, so order
  -- can't come from them.
  position integer not null check (position >= 1),
  measurable_line text not null
    constraint milestones_measurable_line_not_blank check (btrim(measurable_line) <> ''),
  -- Between the goal's start and its deadline, which the routes keep: it spans two tables.
  target_date date,
  -- Stored, not read off the latest check-in: keep, move and adjust put a "not yet" back
  -- to upcoming without a new check-in.
  status text not null default 'upcoming' check (status in ('upcoming', 'hit', 'not_yet')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint milestones_goal_has_milestones_same_owner foreign key (goal_id, user_id, goal_type)
    references goals (id, user_id, type),
  -- Checked when each statement ends, so a reorder can renumber in one statement.
  constraint milestones_position_unique unique (goal_id, position)
    deferrable initially immediate,
  -- So a check-in can name a milestone together with its goal.
  constraint milestones_id_goal unique (id, goal_id)
);

create trigger milestones_set_updated_at before update on milestones
  for each row execute function set_updated_at();

create trigger milestones_audit after insert or update or delete on milestones
  for each row execute function audit();

-- migrate:down

drop table milestones;
