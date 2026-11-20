-- migrate:up

-- A quitting goal's daily answer. No row means unknown, never a slip. The id is made by the
-- server: a day is named by its goal and date.
create table quit_days (
  id uuid primary key,
  user_id uuid not null references users (id),
  goal_id uuid not null,
  -- Always 'quitting': with the foreign key below, the database refuses an answer on any other
  -- type of goal, or on another owner's.
  goal_type text not null default 'quitting' check (goal_type = 'quitting'),
  day date not null,
  held boolean not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Set when the answer is cleared: the day is unknown again.
  deleted_at timestamptz,
  constraint quit_days_quitting_goal_same_owner foreign key (goal_id, user_id, goal_type)
    references goals (id, user_id, type)
);

-- One answer per goal per day. A cleared one doesn't count, so the day can be answered again.
create unique index quit_days_one_per_day on quit_days (goal_id, day) where deleted_at is null;

create trigger quit_days_set_updated_at before update on quit_days
  for each row execute function set_updated_at();

create trigger quit_days_audit after insert or update or delete on quit_days
  for each row execute function audit();

-- How strong the urge was on a day, now and then. Never asked for.
create table urge_ratings (
  id uuid primary key,
  user_id uuid not null references users (id),
  goal_id uuid not null,
  goal_type text not null default 'quitting' check (goal_type = 'quitting'),
  rated_on date not null,
  level text not null check (level in ('low', 'some', 'strong')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint urge_ratings_quitting_goal_same_owner foreign key (goal_id, user_id, goal_type)
    references goals (id, user_id, type)
);

create unique index urge_ratings_one_per_day on urge_ratings (goal_id, rated_on)
  where deleted_at is null;

create trigger urge_ratings_set_updated_at before update on urge_ratings
  for each row execute function set_updated_at();

create trigger urge_ratings_audit after insert or update or delete on urge_ratings
  for each row execute function audit();

-- migrate:down

drop table urge_ratings;

drop table quit_days;
