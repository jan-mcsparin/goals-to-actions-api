-- name: GetRecurringItem :one
select * from recurring_items
where id = $1 and user_id = $2 and deleted_at is null;

-- An item of the owner's that has been deleted: deleting it again changes nothing.
-- name: RecurringItemDeleted :one
select * from recurring_items
where id = $1 and user_id = $2 and deleted_at is not null;

-- name: DeleteRecurringItem :exec
update recurring_items set deleted_at = now()
where id = $1 and user_id = $2 and deleted_at is null;

-- On and off, oldest first. The front end groups them by aspiration.
-- name: ListRecurringItems :many
select * from recurring_items
where user_id = $1 and deleted_at is null
order by created_at, id;

-- Returns nothing when the id is taken.
-- name: CreateRecurringItem :one
insert into recurring_items (
  id, user_id, name, aspiration_id, from_goal_id, schedule_kind, weekday, day_of_month, times,
  period, starts_on
) values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
on conflict (id) do nothing
returning *;

-- name: UpdateRecurringItem :one
update recurring_items
set name = $3, aspiration_id = $4, schedule_kind = $5, weekday = $6, day_of_month = $7,
  times = $8, period = $9, starts_on = $10
where id = $1 and user_id = $2 and deleted_at is null
returning *;

-- Off and on. Coming on, it can also lose an aspiration that has been retired.
-- name: SetRecurringItemActive :one
update recurring_items set active = $3, aspiration_id = $4
where id = $1 and user_id = $2 and deleted_at is null
returning *;

-- Retiring an aspiration with its work paused. Returns the items it turned off.
-- name: TurnOffAspirationItems :many
update recurring_items set active = false
where aspiration_id = $1 and user_id = $2 and active and deleted_at is null
returning id;

-- Retiring an aspiration and keeping its work going: its items become maintenance.
-- name: ClearAspirationItems :exec
update recurring_items set aspiration_id = null
where aspiration_id = $1 and user_id = $2 and deleted_at is null;
