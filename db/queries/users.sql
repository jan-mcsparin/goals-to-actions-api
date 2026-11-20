-- name: GetUser :one
select id, intensity, time_zone, planned_through_week, closed_through_week, created_at, updated_at
from users
where id = $1 and deleted_at is null;

-- name: SetIntensity :one
update users set intensity = $2
where id = $1 and deleted_at is null
returning id, intensity, time_zone, planned_through_week, closed_through_week, created_at, updated_at;

-- name: SetTimeZone :one
update users set time_zone = $2
where id = $1 and deleted_at is null
returning id, intensity, time_zone, planned_through_week, closed_through_week, created_at, updated_at;

-- name: SetPlannedThroughWeek :one
update users set planned_through_week = $2
where id = $1 and deleted_at is null
returning id, intensity, time_zone, planned_through_week, closed_through_week, created_at, updated_at;

-- Taken before any write that renumbers the user's rows, so two such writes arriving
-- together run one after the other.
-- name: LockUser :exec
select id from users
where id = $1 and deleted_at is null
for update;

-- name: SetClosedThroughWeek :one
update users set closed_through_week = $2
where id = $1 and deleted_at is null
returning id, intensity, time_zone, planned_through_week, closed_through_week, created_at, updated_at;

-- An invited tester, added by the command (ADR-012). Every other field starts at its default.
-- name: AddUser :exec
insert into users (id) values ($1);
