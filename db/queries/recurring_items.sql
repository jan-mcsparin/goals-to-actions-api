-- name: GetRecurringItem :one
select * from recurring_items
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
