-- A day's urge, rated or changed. The same level again changes nothing.
-- name: RateUrge :exec
insert into urge_ratings (id, user_id, goal_id, rated_on, level)
values ($1, $2, $3, $4, $5)
on conflict (goal_id, rated_on) where deleted_at is null
do update set level = excluded.level where urge_ratings.level is distinct from excluded.level;

-- name: ClearUrgeRating :exec
update urge_ratings set deleted_at = now()
where goal_id = $1 and user_id = $2 and rated_on = $3 and deleted_at is null;

-- The urge ratings of some goals from one day to another, oldest first.
-- name: ListUrgeRatings :many
select goal_id, rated_on, level from urge_ratings
where user_id = sqlc.arg(user_id) and goal_id = any(sqlc.arg(goal_ids)::uuid[])
  and rated_on between sqlc.arg(from_day)::date and sqlc.arg(through_day)::date
  and deleted_at is null
order by goal_id, rated_on;

-- name: DeleteGoalUrgeRatings :exec
update urge_ratings set deleted_at = now()
where goal_id = $1 and user_id = $2 and deleted_at is null;
