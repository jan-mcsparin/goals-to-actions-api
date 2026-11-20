-- A day's answer, given or changed. The same answer again changes nothing.
-- name: AnswerQuitDay :exec
insert into quit_days (id, user_id, goal_id, day, held)
values ($1, $2, $3, $4, $5)
on conflict (goal_id, day) where deleted_at is null
do update set held = excluded.held where quit_days.held is distinct from excluded.held;

-- Back to unknown.
-- name: ClearQuitDay :exec
update quit_days set deleted_at = now()
where goal_id = $1 and user_id = $2 and day = $3 and deleted_at is null;

-- The answers of some goals from one day to another, oldest first.
-- name: ListQuitDays :many
select goal_id, day, held from quit_days
where user_id = sqlc.arg(user_id) and goal_id = any(sqlc.arg(goal_ids)::uuid[])
  and day between sqlc.arg(from_day)::date and sqlc.arg(through_day)::date
  and deleted_at is null
order by goal_id, day;

-- name: DeleteGoalQuitDays :exec
update quit_days set deleted_at = now()
where goal_id = $1 and user_id = $2 and deleted_at is null;
