-- migrate:up

-- So a row elsewhere can name a goal together with its owner.
alter table goals add constraint goals_id_owner unique (id, user_id);

-- One row each time the person checks in, so results have a history.
create table check_ins (
  id uuid primary key,
  user_id uuid not null references users (id),
  goal_id uuid not null,
  -- Empty when the check-in is for the goal's own line.
  milestone_id uuid,
  outcome text not null check (outcome in ('hit', 'not_yet')),
  result text,
  checked_in_on date not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint check_ins_goal_same_owner foreign key (goal_id, user_id)
    references goals (id, user_id),
  -- The milestone belongs to the same goal, and so to the same owner.
  constraint check_ins_milestone_of_goal foreign key (milestone_id, goal_id)
    references milestones (id, goal_id)
);

create trigger check_ins_set_updated_at before update on check_ins
  for each row execute function set_updated_at();

create trigger check_ins_audit after insert or update or delete on check_ins
  for each row execute function audit();

-- migrate:down

drop table check_ins;

alter table goals drop constraint goals_id_owner;
