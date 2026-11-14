-- migrate:up

-- No user_id: the row is its own owner. Sign-in adds its fields when it's decided.
create table users (
  id uuid primary key,
  intensity text not null default 'normal'
    check (intensity in ('going_hard', 'normal', 'easing_off')),
  time_zone text,
  planned_through_week date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create trigger users_set_updated_at before update on users
  for each row execute function set_updated_at();

create trigger users_audit after insert or update or delete on users
  for each row execute function audit();

-- The one user until sign-in. The same id is FIXED_USER_ID in app/config.py.
insert into users (id) values ('00000000-0000-4000-8000-000000000001');

-- migrate:down

drop table users;
