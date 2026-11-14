-- name: GetUser :one
select id, intensity, time_zone, planned_through_week, created_at, updated_at
from users
where id = $1 and deleted_at is null;

-- name: SetIntensity :one
update users set intensity = $2
where id = $1 and deleted_at is null
returning id, intensity, time_zone, planned_through_week, created_at, updated_at;

-- name: SetTimeZone :one
update users set time_zone = $2
where id = $1 and deleted_at is null
returning id, intensity, time_zone, planned_through_week, created_at, updated_at;

-- name: SetPlannedThroughWeek :one
update users set planned_through_week = $2
where id = $1 and deleted_at is null
returning id, intensity, time_zone, planned_through_week, created_at, updated_at;
