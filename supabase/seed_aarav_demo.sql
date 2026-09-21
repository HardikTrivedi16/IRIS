-- IRIS — demo data seed for the "Aarav Lifesciences — Selaqui Formulations
-- Plant" project (project id: aarav-lifesciences).
--
-- Run this in the Supabase SQL Editor AFTER migration 0006. It is idempotent
-- (safe to run again): every section clears this project's rows first, then
-- reinserts them. The SQL Editor runs as the database owner, so it can delete
-- from the append-only history tables (the backend's service_role cannot).
--
-- It populates BOTH portals for this one project:
--   * Industry portal  -> project_requirements, documents, activity_events
--   * Government portal -> advances the two MPCB applications through the
--                          workflow with a realistic, backdated history.

-- =====================================================================
-- PART A — Industry: regulatory requirements checklist (high readiness)
-- =====================================================================
delete from public.project_requirements where project_id = 'aarav-lifesciences';

insert into public.project_requirements
  (project_id, req_key, name, authority, stage, status, applicability,
   documents_total, documents_complete, depends_on, blocks, source, description, reason, timeline, sort_order)
values
  ('aarav-lifesciences','midc-site','SIIDCUL Site Allotment','SIIDCUL','Pre-establishment','ready','applicable',
   3,3,'[]'::jsonb,'["building-plan","mpcb-cte","fire-approval"]'::jsonb,'SIIDCUL',
   'Allotment of industrial land in Selaqui Industrial Area for the formulations plant.',null,'30-45 days',1),

  ('aarav-lifesciences','building-plan','Building Plan Approval','SIIDCUL','Pre-establishment','ready','applicable',
   5,5,'["midc-site"]'::jsonb,'["factory-plan","construction"]'::jsonb,'SIIDCUL',
   'Approval of building plans for industrial construction on the allotted plot.',null,'45-60 days',2),

  ('aarav-lifesciences','mpcb-cte','MPCB Consent to Establish','MPCB','Pre-establishment','ready','applicable',
   6,6,'["midc-site"]'::jsonb,'["construction","mpcb-cto"]'::jsonb,'MPCB',
   'Consent to Establish (Water Act) verified applicable by the Phase 9 engine from the project discharge profile.',null,'60-90 days',3),

  ('aarav-lifesciences','fire-approval','Fire Safety Approval','Fire Department','Pre-establishment','ready','applicable',
   2,2,'["midc-site"]'::jsonb,'["construction"]'::jsonb,'Fire Department',
   'Fire safety NOC for the manufacturing facility.',null,'30 days',4),

  ('aarav-lifesciences','factory-plan','DISH Factory Plan Approval','Directorate of Industrial Safety and Health','Pre-establishment','ready','applicable',
   6,6,'["building-plan"]'::jsonb,'["factory-licence","drug-licence"]'::jsonb,'Directorate of Industrial Safety and Health',
   'Factory plan approval for the formulations manufacturing facility.',null,'60 days',5),

  ('aarav-lifesciences','construction','Construction Phase','SIIDCUL','Construction','ready','applicable',
   4,4,'["building-plan","mpcb-cte","fire-approval"]'::jsonb,'["inspection"]'::jsonb,'SIIDCUL',
   'Construction of the facility after all pre-establishment approvals.',null,'6-12 months',6),

  ('aarav-lifesciences','inspection','Factory Inspection','Directorate of Industrial Safety and Health','Commissioning','ready','applicable',
   3,3,'["construction"]'::jsonb,'["factory-licence"]'::jsonb,'Directorate of Industrial Safety and Health',
   'Inspection of the completed facility by DISH.',null,'30 days',7),

  ('aarav-lifesciences','factory-licence','Factory Licence','Directorate of Industrial Safety and Health','Commissioning','ready','applicable',
   5,5,'["factory-plan","inspection"]'::jsonb,'["mpcb-cto","operation-ready"]'::jsonb,'Directorate of Industrial Safety and Health',
   'Factory Licence from DISH to operate the facility.',null,'45 days',8),

  ('aarav-lifesciences','drug-licence','Drug Manufacturing Licence','State Drugs Department','Pre-operation','attention','applicable',
   8,6,'["factory-plan"]'::jsonb,'["operation-ready"]'::jsonb,'State Drugs Department',
   'Manufacturing licence (Rule 69, Drugs and Cosmetics Rules) for pharmaceutical production.',
   '2 of 8 documents pending — competent-person affidavit under review.','90-120 days',9),

  ('aarav-lifesciences','mpcb-cto','MPCB Consent to Operate','MPCB','Operations','attention','applicable',
   7,5,'["factory-licence"]'::jsonb,'["operation-ready"]'::jsonb,'MPCB',
   'Consent to Operate (Air Act) required before commencing operations.',
   'Awaiting final stack-emission monitoring report.','60-90 days',10),

  ('aarav-lifesciences','env-clearance','Environmental Clearance','SEIAA','Pre-establishment','not-applicable','not-applicable',
   0,0,'[]'::jsonb,'[]'::jsonb,'SEIAA',
   'Environmental clearance is not applicable at the current formulations scale.',null,'N/A',11),

  ('aarav-lifesciences','operation-ready','Operation Ready','—','Operations','not-ready','applicable',
   0,0,'["factory-licence","drug-licence","mpcb-cto"]'::jsonb,'[]'::jsonb,'—',
   'Final milestone — commences once the Drug Licence and Consent to Operate clear.',null,'—',12);

-- =====================================================================
-- PART B — Industry: document register
-- =====================================================================
delete from public.documents where project_id = 'aarav-lifesciences';

insert into public.documents
  (project_id, name, status, linked_requirement_ids, issues, extracted_information, uploaded_at)
values
  ('aarav-lifesciences','SIIDCUL Allotment Letter.pdf','extracted','["midc-site"]'::jsonb,'[]'::jsonb,'[]'::jsonb, now() - interval '19 days'),
  ('aarav-lifesciences','Building Plan.pdf','extracted','["building-plan"]'::jsonb,'[]'::jsonb,'[]'::jsonb, now() - interval '17 days'),
  ('aarav-lifesciences','Factory Layout.pdf','extracted','["factory-plan"]'::jsonb,'[]'::jsonb,'[]'::jsonb, now() - interval '15 days'),
  ('aarav-lifesciences','Formulation Process Flow.pdf','extracted','["factory-plan"]'::jsonb,'[]'::jsonb,'[]'::jsonb, now() - interval '15 days'),
  ('aarav-lifesciences','MPCB CTE Certificate.pdf','extracted','["mpcb-cte"]'::jsonb,'[]'::jsonb,'[]'::jsonb, now() - interval '10 days'),
  ('aarav-lifesciences','Competent Person Affidavit.pdf','missing-info','["drug-licence"]'::jsonb,
    '["Missing required information: competent-person registration number for the Drug Licence"]'::jsonb,'[]'::jsonb, now() - interval '4 days'),
  ('aarav-lifesciences','Stack Emission Report.pdf','mismatch','["mpcb-cto"]'::jsonb,
    '["Reported stack-emission value differs from the project profile"]'::jsonb,
    '[{"label":"Particulate matter (mg/Nm3)","projectProfile":"90","uploadedDocument":"118"}]'::jsonb, now() - interval '3 days');

-- =====================================================================
-- PART C — Industry: recent activity (Overview page timeline)
-- =====================================================================
delete from public.activity_events where project_id = 'aarav-lifesciences';

insert into public.activity_events (project_id, actor, event_type, message, created_at)
values
  ('aarav-lifesciences','System','STAGE','MPCB Consent to Operate progressed — 5 of 7 documents verified, stack-emission report pending', now() - interval '2 days'),
  ('aarav-lifesciences','P. Nair','SUBMISSION','Drug Manufacturing Licence application submitted to State Drugs Department', now() - interval '4 days'),
  ('aarav-lifesciences','System','COMPLETE','MPCB Consent to Establish marked complete — 6 of 6 documents verified', now() - interval '10 days'),
  ('aarav-lifesciences','P. Nair','UPLOAD','Factory Layout.pdf and Process Flow.pdf verified against the DISH factory plan', now() - interval '15 days'),
  ('aarav-lifesciences','System','MILESTONE','SIIDCUL site allotment recorded — pre-establishment pathway unlocked', now() - interval '19 days');

-- =====================================================================
-- PART D — Government: advance the two MPCB applications
--   APP-AARAV-REQ-0001 (Water Act) -> APPROVED  (completed)
--   APP-AARAV-REQ-0002 (Air Act)   -> UNDER_REVIEW (in progress)
-- Both assigned to an MPCB officer, with a realistic backdated history.
-- =====================================================================
do $$
declare
  v_app1   uuid;
  v_app2   uuid;
  v_off_id uuid;
  v_off_nm text;
begin
  select id into v_app1 from public.applications where application_id = 'APP-AARAV-REQ-0001';
  select id into v_app2 from public.applications where application_id = 'APP-AARAV-REQ-0002';

  -- Pick an MPCB officer to assign (prefer a DEPARTMENT_OFFICER, else any active user).
  select id, name into v_off_id, v_off_nm
    from public.department_users
   where department_id = 'dept-mpcb' and is_active
   order by (role = 'DEPARTMENT_OFFICER') desc
   limit 1;

  if v_app1 is null or v_app2 is null then
    raise notice 'Aarav applications not found — run migration 0005 first. Skipping Part D.';
    return;
  end if;

  -- Clear prior demo history for these two apps (idempotent re-run).
  delete from public.application_stage_history where application_id in (v_app1, v_app2);
  delete from public.assignment_history        where application_id in (v_app1, v_app2);
  delete from public.operational_events        where application_id in (v_app1, v_app2);

  -- ---- APP 1: full journey to APPROVED --------------------------------
  update public.applications
     set current_stage = 'APPROVED',
         assigned_officer_id = v_off_id,
         created_at = now() - interval '18 days',
         completed_at = now() - interval '2 days',
         updated_at = now() - interval '2 days'
   where id = v_app1;

  insert into public.assignment_history (application_id, officer_id, officer_name, assigned_by, reason, created_at)
    values (v_app1, v_off_id, coalesce(v_off_nm,'MPCB Officer'), 'MPCB Duty Officer', 'Initial triage assignment', now() - interval '17 days');

  insert into public.application_stage_history (application_id, previous_stage, new_stage, actor, reason, created_at)
  values
    (v_app1,'SUBMITTED','UNDER_REVIEW','MPCB Duty Officer',null, now() - interval '16 days'),
    (v_app1,'UNDER_REVIEW','INSPECTION_SCHEDULED','MPCB Duty Officer',null, now() - interval '12 days'),
    (v_app1,'INSPECTION_SCHEDULED','INSPECTION_COMPLETED','MPCB Duty Officer',null, now() - interval '8 days'),
    (v_app1,'INSPECTION_COMPLETED','RECOMMENDED','MPCB Duty Officer',null, now() - interval '4 days'),
    (v_app1,'RECOMMENDED','APPROVED','MPCB Duty Officer',null, now() - interval '2 days');

  insert into public.operational_events (application_id, event_type, message, actor, created_at)
  values
    (v_app1,'OFFICER_ASSIGNED', 'Assigned to ' || coalesce(v_off_nm,'MPCB Officer'), 'MPCB Duty Officer', now() - interval '17 days'),
    (v_app1,'STAGE_TRANSITION','Consent to Establish (Water Act) granted','MPCB Duty Officer', now() - interval '2 days');

  -- ---- APP 2: in progress, currently UNDER_REVIEW ---------------------
  update public.applications
     set current_stage = 'UNDER_REVIEW',
         assigned_officer_id = v_off_id,
         created_at = now() - interval '10 days',
         completed_at = null,
         updated_at = now() - interval '3 days'
   where id = v_app2;

  insert into public.assignment_history (application_id, officer_id, officer_name, assigned_by, reason, created_at)
    values (v_app2, v_off_id, coalesce(v_off_nm,'MPCB Officer'), 'MPCB Duty Officer', 'Initial triage assignment', now() - interval '9 days');

  insert into public.application_stage_history (application_id, previous_stage, new_stage, actor, reason, created_at)
    values (v_app2,'SUBMITTED','UNDER_REVIEW','MPCB Duty Officer',null, now() - interval '7 days');

  insert into public.operational_events (application_id, event_type, message, actor, created_at)
    values (v_app2,'OFFICER_ASSIGNED', 'Assigned to ' || coalesce(v_off_nm,'MPCB Officer'), 'MPCB Duty Officer', now() - interval '9 days');

  raise notice 'Aarav government applications advanced (APP1 APPROVED, APP2 UNDER_REVIEW).';
end $$;
