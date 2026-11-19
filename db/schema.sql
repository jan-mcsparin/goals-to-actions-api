--
-- PostgreSQL database dump
--

\restrict dbmate

-- Dumped from database version 18.7 (Debian 18.7-1.pgdg13+2)
-- Dumped by pg_dump version 18.7 (Debian 18.7-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: audit(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.audit() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
declare
  old_row jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
  new_row jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
begin
  insert into audit_log (table_name, row_id, operation, old_row, new_row, user_id, action)
  values (
    tg_table_name,
    (coalesce(new_row, old_row) ->> 'id')::uuid,
    lower(tg_op),
    old_row,
    new_row,
    nullif(current_setting('app.user_id', true), '')::uuid,
    nullif(current_setting('app.action', true), '')
  );
  return null;
end;
$$;


--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
  new.updated_at := statement_timestamp();
  return new;
end;
$$;


--
-- Name: task_rows_agree(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.task_rows_agree() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
declare
  checked_task uuid;
  task_state text;
  last_outcome text;
begin
  if tg_table_name = 'tasks' then
    checked_task := new.id;
  elsif tg_op = 'DELETE' then
    checked_task := old.task_id;
  else
    checked_task := new.task_id;
  end if;

  select state into task_state from tasks where id = checked_task and deleted_at is null;
  if not found then
    return null;
  end if;

  if task_state <> 'open' and exists (
    select from task_weeks
    where task_id = checked_task and outcome is null and deleted_at is null
  ) then
    raise exception 'A % task can''t have a row in play.', task_state
      using errcode = 'check_violation', constraint = 'task_rows_agree';
  end if;

  if task_state = 'done' then
    select outcome into last_outcome from task_weeks
    where task_id = checked_task and deleted_at is null
    order by week desc limit 1;
    if last_outcome is distinct from 'done' then
      raise exception 'A done task''s last row is done.'
        using errcode = 'check_violation', constraint = 'task_rows_agree';
    end if;
  end if;

  return null;
end;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: aspirations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.aspirations (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    name text NOT NULL,
    why text,
    status text DEFAULT 'active'::text NOT NULL,
    "position" integer,
    retired_on date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT aspirations_name_not_blank CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT aspirations_status_agrees CHECK ((((status = 'active'::text) AND ("position" IS NOT NULL) AND ("position" >= 1) AND (retired_on IS NULL)) OR ((status = 'retired'::text) AND ("position" IS NULL) AND (retired_on IS NOT NULL))))
);


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    id bigint NOT NULL,
    table_name text NOT NULL,
    row_id uuid NOT NULL,
    operation text NOT NULL,
    old_row jsonb,
    new_row jsonb,
    user_id uuid,
    action text,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_log_operation_check CHECK ((operation = ANY (ARRAY['insert'::text, 'update'::text, 'delete'::text])))
);


--
-- Name: audit_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.audit_log ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: check_ins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.check_ins (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    goal_id uuid NOT NULL,
    milestone_id uuid,
    outcome text NOT NULL,
    result text,
    checked_in_on date NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT check_ins_outcome_check CHECK ((outcome = ANY (ARRAY['hit'::text, 'not_yet'::text])))
);


--
-- Name: goals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.goals (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    aspiration_id uuid,
    type text NOT NULL,
    label text NOT NULL,
    measurable_line text NOT NULL,
    baseline text,
    status text DEFAULT 'active'::text NOT NULL,
    start_date date NOT NULL,
    deadline date,
    ended_on date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT goals_deadline_not_before_start CHECK ((deadline >= start_date)),
    CONSTRAINT goals_ended_on_agrees CHECK (((status = ANY (ARRAY['active'::text, 'paused'::text])) = (ended_on IS NULL))),
    CONSTRAINT goals_label_not_blank CHECK ((btrim(label) <> ''::text)),
    CONSTRAINT goals_measurable_line_not_blank CHECK ((btrim(measurable_line) <> ''::text)),
    CONSTRAINT goals_status_check CHECK ((status = ANY (ARRAY['active'::text, 'paused'::text, 'reached'::text, 'ended'::text]))),
    CONSTRAINT goals_type_check CHECK ((type = ANY (ARRAY['building'::text, 'quitting'::text, 'one_off'::text])))
);


--
-- Name: milestones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.milestones (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    goal_id uuid NOT NULL,
    goal_type text NOT NULL,
    "position" integer NOT NULL,
    measurable_line text NOT NULL,
    target_date date,
    status text DEFAULT 'upcoming'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT milestones_goal_type_check CHECK ((goal_type = ANY (ARRAY['building'::text, 'quitting'::text]))),
    CONSTRAINT milestones_measurable_line_not_blank CHECK ((btrim(measurable_line) <> ''::text)),
    CONSTRAINT milestones_position_check CHECK (("position" >= 1)),
    CONSTRAINT milestones_status_check CHECK ((status = ANY (ARRAY['upcoming'::text, 'hit'::text, 'not_yet'::text])))
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version character varying NOT NULL
);


--
-- Name: task_weeks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_weeks (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    task_id uuid NOT NULL,
    week date NOT NULL,
    planned_day date,
    placed_by_hand boolean DEFAULT false NOT NULL,
    outcome text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT task_weeks_day_in_week CHECK (((planned_day >= week) AND (planned_day <= (week + 6)))),
    CONSTRAINT task_weeks_outcome_check CHECK ((outcome = ANY (ARRAY['done'::text, 'rolled_over'::text, 'lapsed'::text, 'dropped'::text, 'set_aside'::text]))),
    CONSTRAINT task_weeks_placed_on_a_day CHECK (((NOT placed_by_hand) OR (planned_day IS NOT NULL))),
    CONSTRAINT task_weeks_week_is_monday CHECK ((EXTRACT(isodow FROM week) = (1)::numeric))
);


--
-- Name: tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tasks (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    title text NOT NULL,
    origin text NOT NULL,
    goal_id uuid,
    recurring_item_id uuid,
    state text DEFAULT 'open'::text NOT NULL,
    due_date date,
    time_kind text,
    time_of_day time without time zone,
    value_logged numeric,
    completed_at timestamp with time zone,
    completed_on date,
    period_start date,
    number integer,
    still_matters_answered_on date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT tasks_done_has_completion CHECK ((((state = 'done'::text) = (completed_on IS NOT NULL)) AND ((completed_on IS NULL) = (completed_at IS NULL)) AND ((value_logged IS NULL) OR (state = 'done'::text)))),
    CONSTRAINT tasks_generated_has_period CHECK ((((origin = 'by_hand'::text) = (period_start IS NULL)) AND ((period_start IS NULL) = (number IS NULL)))),
    CONSTRAINT tasks_goal_or_item CHECK (((goal_id IS NULL) OR (recurring_item_id IS NULL))),
    CONSTRAINT tasks_item_means_its_origin CHECK (((recurring_item_id IS NULL) OR (origin = 'recurring_item'::text))),
    CONSTRAINT tasks_number_check CHECK ((number >= 1)),
    CONSTRAINT tasks_origin_check CHECK ((origin = ANY (ARRAY['by_hand'::text, 'weekly_target'::text, 'recurring_item'::text]))),
    CONSTRAINT tasks_state_check CHECK ((state = ANY (ARRAY['open'::text, 'done'::text, 'dropped'::text, 'lapsed'::text]))),
    CONSTRAINT tasks_time_kind_and_time CHECK (((time_kind IS NULL) = (time_of_day IS NULL))),
    CONSTRAINT tasks_time_kind_check CHECK ((time_kind = ANY (ARRAY['by'::text, 'at'::text]))),
    CONSTRAINT tasks_title_not_blank CHECK ((btrim(title) <> ''::text)),
    CONSTRAINT tasks_value_logged_check CHECK ((value_logged >= (0)::numeric)),
    CONSTRAINT tasks_weekly_target_has_goal CHECK (((origin <> 'weekly_target'::text) OR (goal_id IS NOT NULL)))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    intensity text DEFAULT 'normal'::text NOT NULL,
    time_zone text,
    planned_through_week date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT users_intensity_check CHECK ((intensity = ANY (ARRAY['going_hard'::text, 'normal'::text, 'easing_off'::text])))
);


--
-- Name: weekly_targets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.weekly_targets (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    goal_id uuid NOT NULL,
    goal_type text DEFAULT 'building'::text NOT NULL,
    kind text NOT NULL,
    sessions integer NOT NULL,
    amount numeric,
    unit text NOT NULL,
    effective_from date NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT weekly_targets_amount_agrees CHECK ((((kind = 'amount'::text) = (amount IS NOT NULL)) AND (amount > (0)::numeric))),
    CONSTRAINT weekly_targets_goal_type_check CHECK ((goal_type = 'building'::text)),
    CONSTRAINT weekly_targets_kind_check CHECK ((kind = ANY (ARRAY['count'::text, 'amount'::text]))),
    CONSTRAINT weekly_targets_sessions_check CHECK (((sessions >= 1) AND (sessions <= 14))),
    CONSTRAINT weekly_targets_unit_not_blank CHECK ((btrim(unit) <> ''::text)),
    CONSTRAINT weekly_targets_week_is_a_monday CHECK ((EXTRACT(isodow FROM effective_from) = (1)::numeric))
);


--
-- Name: aspirations aspirations_id_owner; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspirations
    ADD CONSTRAINT aspirations_id_owner UNIQUE (id, user_id);


--
-- Name: aspirations aspirations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspirations
    ADD CONSTRAINT aspirations_pkey PRIMARY KEY (id);


--
-- Name: aspirations aspirations_position_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspirations
    ADD CONSTRAINT aspirations_position_unique UNIQUE (user_id, "position") DEFERRABLE;


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: check_ins check_ins_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.check_ins
    ADD CONSTRAINT check_ins_pkey PRIMARY KEY (id);


--
-- Name: goals goals_id_owner; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goals
    ADD CONSTRAINT goals_id_owner UNIQUE (id, user_id);


--
-- Name: goals goals_id_owner_type; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goals
    ADD CONSTRAINT goals_id_owner_type UNIQUE (id, user_id, type);


--
-- Name: goals goals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goals
    ADD CONSTRAINT goals_pkey PRIMARY KEY (id);


--
-- Name: milestones milestones_id_goal; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.milestones
    ADD CONSTRAINT milestones_id_goal UNIQUE (id, goal_id);


--
-- Name: milestones milestones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.milestones
    ADD CONSTRAINT milestones_pkey PRIMARY KEY (id);


--
-- Name: milestones milestones_position_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.milestones
    ADD CONSTRAINT milestones_position_unique UNIQUE (goal_id, "position") DEFERRABLE;


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: task_weeks task_weeks_one_per_week; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_weeks
    ADD CONSTRAINT task_weeks_one_per_week UNIQUE (task_id, week);


--
-- Name: task_weeks task_weeks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_weeks
    ADD CONSTRAINT task_weeks_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_goal_period_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_goal_period_number UNIQUE (goal_id, period_start, number);


--
-- Name: tasks tasks_id_owner; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_id_owner UNIQUE (id, user_id);


--
-- Name: tasks tasks_item_period_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_item_period_number UNIQUE (recurring_item_id, period_start, number);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: weekly_targets weekly_targets_one_per_week; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weekly_targets
    ADD CONSTRAINT weekly_targets_one_per_week UNIQUE (goal_id, effective_from);


--
-- Name: weekly_targets weekly_targets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weekly_targets
    ADD CONSTRAINT weekly_targets_pkey PRIMARY KEY (id);


--
-- Name: task_weeks_one_in_play; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX task_weeks_one_in_play ON public.task_weeks USING btree (task_id) WHERE ((outcome IS NULL) AND (deleted_at IS NULL));


--
-- Name: aspirations aspirations_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER aspirations_audit AFTER INSERT OR DELETE OR UPDATE ON public.aspirations FOR EACH ROW EXECUTE FUNCTION public.audit();


--
-- Name: aspirations aspirations_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER aspirations_set_updated_at BEFORE UPDATE ON public.aspirations FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: check_ins check_ins_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER check_ins_audit AFTER INSERT OR DELETE OR UPDATE ON public.check_ins FOR EACH ROW EXECUTE FUNCTION public.audit();


--
-- Name: check_ins check_ins_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER check_ins_set_updated_at BEFORE UPDATE ON public.check_ins FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: goals goals_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER goals_audit AFTER INSERT OR DELETE OR UPDATE ON public.goals FOR EACH ROW EXECUTE FUNCTION public.audit();


--
-- Name: goals goals_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER goals_set_updated_at BEFORE UPDATE ON public.goals FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: milestones milestones_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER milestones_audit AFTER INSERT OR DELETE OR UPDATE ON public.milestones FOR EACH ROW EXECUTE FUNCTION public.audit();


--
-- Name: milestones milestones_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER milestones_set_updated_at BEFORE UPDATE ON public.milestones FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: task_weeks task_weeks_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER task_weeks_audit AFTER INSERT OR DELETE OR UPDATE ON public.task_weeks FOR EACH ROW EXECUTE FUNCTION public.audit();


--
-- Name: task_weeks task_weeks_rows_agree; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER task_weeks_rows_agree AFTER INSERT OR DELETE OR UPDATE ON public.task_weeks DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.task_rows_agree();


--
-- Name: task_weeks task_weeks_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER task_weeks_set_updated_at BEFORE UPDATE ON public.task_weeks FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: tasks tasks_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER tasks_audit AFTER INSERT OR DELETE OR UPDATE ON public.tasks FOR EACH ROW EXECUTE FUNCTION public.audit();


--
-- Name: tasks tasks_rows_agree; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER tasks_rows_agree AFTER INSERT OR UPDATE ON public.tasks DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.task_rows_agree();


--
-- Name: tasks tasks_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER tasks_set_updated_at BEFORE UPDATE ON public.tasks FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: users users_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER users_audit AFTER INSERT OR DELETE OR UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.audit();


--
-- Name: users users_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: weekly_targets weekly_targets_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER weekly_targets_audit AFTER INSERT OR DELETE OR UPDATE ON public.weekly_targets FOR EACH ROW EXECUTE FUNCTION public.audit();


--
-- Name: weekly_targets weekly_targets_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER weekly_targets_set_updated_at BEFORE UPDATE ON public.weekly_targets FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: aspirations aspirations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aspirations
    ADD CONSTRAINT aspirations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: check_ins check_ins_goal_same_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.check_ins
    ADD CONSTRAINT check_ins_goal_same_owner FOREIGN KEY (goal_id, user_id) REFERENCES public.goals(id, user_id);


--
-- Name: check_ins check_ins_milestone_of_goal; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.check_ins
    ADD CONSTRAINT check_ins_milestone_of_goal FOREIGN KEY (milestone_id, goal_id) REFERENCES public.milestones(id, goal_id);


--
-- Name: check_ins check_ins_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.check_ins
    ADD CONSTRAINT check_ins_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: goals goals_aspiration_same_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goals
    ADD CONSTRAINT goals_aspiration_same_owner FOREIGN KEY (aspiration_id, user_id) REFERENCES public.aspirations(id, user_id);


--
-- Name: goals goals_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.goals
    ADD CONSTRAINT goals_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: milestones milestones_goal_has_milestones_same_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.milestones
    ADD CONSTRAINT milestones_goal_has_milestones_same_owner FOREIGN KEY (goal_id, user_id, goal_type) REFERENCES public.goals(id, user_id, type);


--
-- Name: milestones milestones_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.milestones
    ADD CONSTRAINT milestones_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: task_weeks task_weeks_task_same_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_weeks
    ADD CONSTRAINT task_weeks_task_same_owner FOREIGN KEY (task_id, user_id) REFERENCES public.tasks(id, user_id);


--
-- Name: task_weeks task_weeks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_weeks
    ADD CONSTRAINT task_weeks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: tasks tasks_goal_same_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_goal_same_owner FOREIGN KEY (goal_id, user_id) REFERENCES public.goals(id, user_id);


--
-- Name: tasks tasks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: weekly_targets weekly_targets_building_goal_same_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weekly_targets
    ADD CONSTRAINT weekly_targets_building_goal_same_owner FOREIGN KEY (goal_id, user_id, goal_type) REFERENCES public.goals(id, user_id, type);


--
-- Name: weekly_targets weekly_targets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.weekly_targets
    ADD CONSTRAINT weekly_targets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict dbmate


--
-- Dbmate schema migrations
--

INSERT INTO public.schema_migrations (version) VALUES
    ('20261114022739'),
    ('20261114022856'),
    ('20261116195619'),
    ('20261116230000'),
    ('20261116230100'),
    ('20261117000000'),
    ('20261117000100'),
    ('20261118000000'),
    ('20261118000100');
