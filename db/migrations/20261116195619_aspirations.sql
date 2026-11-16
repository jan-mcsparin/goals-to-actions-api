-- migrate:up

create table aspirations (
  id uuid primary key,
  user_id uuid not null references users (id),
  name text not null constraint aspirations_name_not_blank check (btrim(name) <> ''),
  why text,
  status text not null default 'active',
  -- Priority among the owner's active aspirations: 1, 2, 3. The routes keep it free of gaps.
  position integer,
  retired_on date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  -- The two statuses, and what each one has.
  constraint aspirations_status_agrees check (
    (status = 'active' and position is not null and position >= 1 and retired_on is null)
    or (status = 'retired' and position is null and retired_on is not null)
  ),
  -- Deferrable so it's checked when a statement ends, not row by row: a reorder renumbers
  -- several rows in one update. It can't be a partial index that leaves out deleted rows
  -- (those can't be deferrable), so deleting an aspiration will empty its position.
  constraint aspirations_position_unique unique (user_id, position) deferrable initially immediate
);

create trigger aspirations_set_updated_at before update on aspirations
  for each row execute function set_updated_at();

create trigger aspirations_audit after insert or update or delete on aspirations
  for each row execute function audit();

-- migrate:down

drop table aspirations;
