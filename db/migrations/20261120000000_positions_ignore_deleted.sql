-- migrate:up

-- A deleted aspiration or milestone gives up its position, so the rows after it can move up
-- and a new one can take the last place. Deferrable as before, so one statement can renumber.
alter table aspirations drop constraint aspirations_position_unique;
alter table aspirations add constraint aspirations_position_unique
  exclude using btree (user_id with =, position with =) where (deleted_at is null) deferrable;

alter table milestones drop constraint milestones_position_unique;
alter table milestones add constraint milestones_position_unique
  exclude using btree (goal_id with =, position with =) where (deleted_at is null) deferrable;

-- migrate:down

alter table milestones drop constraint milestones_position_unique;
alter table milestones add constraint milestones_position_unique
  unique (goal_id, position) deferrable;

alter table aspirations drop constraint aspirations_position_unique;
alter table aspirations add constraint aspirations_position_unique
  unique (user_id, position) deferrable;
