-- name: GetTask :one
select * from tasks
where id = $1 and user_id = $2 and deleted_at is null;
