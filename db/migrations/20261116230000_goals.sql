-- migrate:up

-- So a row elsewhere can name an aspiration together with its owner, and never point at
-- another owner's aspiration.
alter table aspirations add constraint aspirations_id_owner unique (id, user_id);

create table goals (
  id uuid primary key,
  user_id uuid not null references users (id),
  aspiration_id uuid,
  -- Picked by the person, never inferred, and never changed: weekly targets copy it.
  type text not null check (type in ('building', 'quitting', 'one_off')),
  label text not null constraint goals_label_not_blank check (btrim(label) <> ''),
  measurable_line text not null
    constraint goals_measurable_line_not_blank check (btrim(measurable_line) <> ''),
  baseline text,
  status text not null default 'active'
    check (status in ('active', 'paused', 'reached', 'ended')),
  start_date date not null,
  deadline date,
  ended_on date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint goals_aspiration_same_owner foreign key (aspiration_id, user_id)
    references aspirations (id, user_id),
  constraint goals_deadline_not_before_start check (deadline >= start_date),
  -- Set when the goal is reached or ended, cleared by Reopen and Go again.
  constraint goals_ended_on_agrees check (
    (status in ('active', 'paused')) = (ended_on is null)
  ),
  -- What weekly targets point at, so only a building goal of the same owner can have one.
  constraint goals_id_owner_type unique (id, user_id, type)
);

create trigger goals_set_updated_at before update on goals
  for each row execute function set_updated_at();

create trigger goals_audit after insert or update or delete on goals
  for each row execute function audit();

-- migrate:down

drop table goals;

alter table aspirations drop constraint aspirations_id_owner;
