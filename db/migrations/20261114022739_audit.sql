-- migrate:up

-- One row per insert, update or delete on every table (ADR-005). No screen reads it.
-- The device never writes here and nothing updates it, so it has its own key and none
-- of the shared columns.
create table audit_log (
  id bigint generated always as identity primary key,
  table_name text not null,
  row_id uuid not null,
  operation text not null check (operation in ('insert', 'update', 'delete')),
  old_row jsonb,
  new_row jsonb,
  user_id uuid,
  action text,
  changed_at timestamptz not null default now()
);

-- The trigger every table gets: `after insert or update or delete ... for each row`.
-- The user and action come from app.transaction(), which sets them for one transaction.
-- Outside it they are empty.
create function audit() returns trigger
language plpgsql as $$
declare
  old_row jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
  new_row jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
begin
  insert into audit_log (table_name, row_id, operation, old_row, new_row, user_id, action)
  values (
    tg_table_name,
    (coalesce(new_row, old_row) ->> 'id')::uuid,
    lower(tg_op),
    old_row,
    new_row,
    nullif(current_setting('app.user_id', true), '')::uuid,
    nullif(current_setting('app.action', true), '')
  );
  return null;
end;
$$;

-- The trigger every table gets: `before update ... for each row`. Queries never set
-- updated_at themselves. statement_timestamp(), not now(), so two writes in one
-- transaction get different times.
create function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := statement_timestamp();
  return new;
end;
$$;

-- migrate:down

drop function set_updated_at();
drop function audit();
drop table audit_log;
