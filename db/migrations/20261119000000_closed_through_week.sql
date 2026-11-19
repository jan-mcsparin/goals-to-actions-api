-- migrate:up

-- The Monday of the latest week that has been closed (ADR-009). Null until the first close.
alter table users add column closed_through_week date;

-- migrate:down

alter table users drop column closed_through_week;
