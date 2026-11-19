-- name: GetRecurringItem :one
select * from recurring_items
where id = $1 and user_id = $2 and deleted_at is null;

-- On and off, oldest first. The front end groups them by aspiration.
-- name: ListRecurringItems :many
select * from recurring_items
where user_id = $1 and deleted_at is null
order by created_at, id;
