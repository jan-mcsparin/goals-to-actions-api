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
-- Name: aspirations aspirations_audit; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER aspirations_audit AFTER INSERT OR DELETE OR UPDATE ON public.aspirations FOR EACH ROW EXECUTE FUNCTION public.audit();


--
-- Name: aspirations aspirations_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER aspirations_set_updated_at BEFORE UPDATE ON public.aspirations FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


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
    ('20261117000000');
