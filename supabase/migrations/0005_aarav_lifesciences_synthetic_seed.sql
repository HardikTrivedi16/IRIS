-- IRIS — Supabase migration 0005: Aarav Lifesciences synthetic pharma dataset
--
-- SOURCE
-- ======
-- aarav_lifesciences_IRIS_pharma_synthetic_data.zip — a synthetic pharma dataset
-- (Aarav Lifesciences Private Limited, Selaqui, Dehradun, Uttarakhand) generated
-- specifically against this repo's real backend contracts (ProjectIn, ProjectFactsIn,
-- DocumentIn, CreateApplicationIn — see the ZIP's own mappings/iris_v7_document_data_mapping.json
-- and validation/dataset_validation_report.json, both re-checked field-by-field before
-- writing this migration).
--
-- WHAT THIS MIGRATION DOES
-- =========================
-- 1. Upserts real rows into the EXISTING engine-facing tables from migration 0001/0002
--    (public.projects, public.project_facts, public.documents, public.applications) —
--    it does NOT create new tables for these, because equivalent tables already exist
--    and are what the FastAPI backend / Phase 9 engine actually reads.
-- 2. Adds NEW tables for entities the current IRIS backend has NO model for at all
--    (companies, company_directors, products, compliance_scenarios, document_metadata,
--    product_documents) — confirmed via the ZIP's own mapping file, category "E — not
--    required by current IRIS implementation". These are descriptive/reference data,
--    clearly separated from engine-authoritative data.
-- 3. Does NOT touch backend/regulatory-data/*.yaml, does NOT invent a Condition/Rule/
--    Decision, does NOT create a pharma-specific department, does NOT convert the 8
--    compliance scenarios into fabricated engine Decisions. See "Important limitations"
--    in the accompanying chat response for the full list.
--
-- IDEMPOTENCY
-- ===========
-- Every CREATE TABLE / INDEX uses IF NOT EXISTS. Every INSERT uses ON CONFLICT ... DO
-- UPDATE (or DO NOTHING for append-only-style reference rows). Every CREATE POLICY is
-- preceded by DROP POLICY IF EXISTS. Safe to paste and re-run this whole script as many
-- times as you like — it will never duplicate rows or destroy data.
--
-- NAMING — NO COLLISIONS WITH EXISTING SCHEMA
-- =============================================
-- public.projects, public.project_facts, public.documents, public.applications,
-- public.departments, public.sla_policies already exist (migrations 0001/0002/0003/0004)
-- and are reused as-is. New table names (companies, company_directors, products,
-- compliance_scenarios, document_metadata, product_documents) do not exist anywhere in
-- 0001-0004.

create extension if not exists "pgcrypto"; -- gen_random_uuid() — already enabled by 0001, defensive re-declare only

-- =====================================================================================
-- 1. PROJECT — upsert into the EXISTING public.projects (migration 0001)
-- =====================================================================================
-- owner_id is intentionally left NULL: this is unclaimed demo data, same as the
-- pre-existing "mahapharm"/"freshbite" demo projects. Under migration 0004's strict RLS,
-- an authenticated Industry user other than the eventual owner will not see this project
-- via direct Supabase reads until someone runs:
--   update public.projects set owner_id = '<your-auth-uid>' where id = 'aarav-lifesciences';
-- Government users in dept-mpcb CAN already see it via 0004's government-application-join
-- policy once the application rows below exist. The backend's normal demo-mode path
-- (service_role, bypasses RLS) is unaffected either way.
insert into public.projects (id, name, industry, activity, location, stage, scale, workers, characteristics)
values (
  'aarav-lifesciences',
  'Aarav Lifesciences — Selaqui Formulations Plant',
  'PHARMACEUTICAL',
  'Manufacture of pharmaceutical formulations (tablets, oral powders)',
  'Selaqui Industrial Area, Dehradun, Uttarakhand',
  'OPERATION',
  'MEDIUM',
  85,
  '{"hazardousChemicals": false, "hazardousWaste": false, "wastewater": true, "airEmissions": true, "waterUse": true, "chemicalStorage": true}'::jsonb
)
on conflict (id) do update set
  name            = excluded.name,
  industry        = excluded.industry,
  activity        = excluded.activity,
  location        = excluded.location,
  stage           = excluded.stage,
  scale           = excluded.scale,
  workers         = excluded.workers,
  characteristics = excluded.characteristics,
  updated_at      = now();

-- =====================================================================================
-- 2. PROJECT FACTS — upsert into the EXISTING public.project_facts (migration 0001)
-- =====================================================================================
-- Fact keys are copied VERBATIM from data/project_facts.json — these are exactly the
-- keys the frozen iris_engine's 4 rule versions declare they need (see HANDOFF.md /
-- README.md in the ZIP). source='user' for the 4 project.* facts (project-level
-- characteristics a human declares); source='document' for the 11 document.* facts
-- (confirmed-extraction facts, matching HANDOFF.md rule #5's document.* namespace).
insert into public.project_facts (project_id, fact_key, fact_value, source)
values
  ('aarav-lifesciences', 'project.industry',                                          to_jsonb('PHARMACEUTICAL'::text), 'user'),
  ('aarav-lifesciences', 'project.drug_schedule_classification',                       to_jsonb('SCHEDULE_H'::text),      'user'),
  ('aarav-lifesciences', 'project.likely_to_discharge_sewage_or_trade_effluent',       to_jsonb(true),                    'user'),
  ('aarav-lifesciences', 'project.plant_located_in_air_pollution_control_area',        to_jsonb(true),                    'user'),
  ('aarav-lifesciences', 'document.drug_manufacturing_licence_number',                 to_jsonb('UK/DL/2019/00417'::text),   'document'),
  ('aarav-lifesciences', 'document.drug_manufacturing_licence_valid_upto',             to_jsonb('2029-06-30'::text),         'document'),
  ('aarav-lifesciences', 'document.gmp_certificate_number',                            to_jsonb('GMP/UK/2024/2211'::text),   'document'),
  ('aarav-lifesciences', 'document.gmp_certificate_valid_upto',                        to_jsonb('2027-02-09'::text),         'document'),
  ('aarav-lifesciences', 'document.who_gmp_certificate_number',                        to_jsonb('WHOGMP/UK/2023/0871'::text),'document'),
  ('aarav-lifesciences', 'document.fire_noc_number',                                   to_jsonb('FIRE/UK/2025/1187'::text),  'document'),
  ('aarav-lifesciences', 'document.pollution_consent_number',                          to_jsonb('UEPPCB/CTO/2025/774'::text),'document'),
  ('aarav-lifesciences', 'document.pollution_consent_category',                        to_jsonb('Orange'::text),             'document'),
  ('aarav-lifesciences', 'document.gstin',                                             to_jsonb('05AAACA1234C1Z5'::text),    'document'),
  ('aarav-lifesciences', 'document.cin',                                               to_jsonb('U24232UK2019PTC012345'::text),'document'),
  ('aarav-lifesciences', 'document.pan',                                               to_jsonb('AAACA1234C'::text),         'document')
on conflict (project_id, fact_key) do update set
  fact_value = excluded.fact_value,
  source     = excluded.source,
  updated_at = now();

-- =====================================================================================
-- 3. DOCUMENT REGISTER — upsert into the EXISTING public.documents (migration 0001)
-- =====================================================================================
-- public.documents already has exactly the DocumentIn shape (name, storage_path, status
-- in {uploaded, extracted, missing-info, mismatch}, linked_requirement_ids). We add one
-- new nullable column, external_document_id, so the 22 human-readable ids from the ZIP
-- (DOC-ENT-001 etc.) survive as the natural key for ON CONFLICT upserts and as the join
-- target for document_metadata below — this is additive/non-destructive to any existing
-- rows from other projects (their external_document_id stays NULL).
alter table public.documents add column if not exists external_document_id text;

comment on column public.documents.external_document_id is
  'Optional natural document id from an external synthetic dataset (e.g. "DOC-ENT-001"). NULL for documents created through the normal upload flow.';

create unique index if not exists ux_documents_project_external_id
  on public.documents (project_id, external_document_id)
  where external_document_id is not null;

insert into public.documents (project_id, name, storage_path, status, linked_requirement_ids, external_document_id)
values
  ('aarav-lifesciences', 'DOC-ENT-001 — Pan Card',                          'documents/DOC-ENT-001.pdf', 'extracted',    '[]'::jsonb,                        'DOC-ENT-001'),
  ('aarav-lifesciences', 'DOC-ENT-002 — Cert Of Incorporation',             'documents/DOC-ENT-002.pdf', 'extracted',    '[]'::jsonb,                        'DOC-ENT-002'),
  ('aarav-lifesciences', 'DOC-ENT-003 — Gst Registration Certificate',      'documents/DOC-ENT-003.pdf', 'extracted',    '[]'::jsonb,                        'DOC-ENT-003'),
  ('aarav-lifesciences', 'DOC-ENT-004 — Tan Record',                        'documents/DOC-ENT-004.pdf', 'extracted',    '[]'::jsonb,                        'DOC-ENT-004'),
  ('aarav-lifesciences', 'DOC-ENT-005 — Authorized Signatory Pan',          'documents/DOC-ENT-005.pdf', 'extracted',    '[]'::jsonb,                        'DOC-ENT-005'),
  ('aarav-lifesciences', 'DOC-ENT-006 — Address Proof',                     'documents/DOC-ENT-006.pdf', 'mismatch',     '[]'::jsonb,                        'DOC-ENT-006'),
  ('aarav-lifesciences', 'DOC-ENT-007 — Cancelled Cheque',                  'documents/DOC-ENT-007.pdf', 'extracted',    '[]'::jsonb,                        'DOC-ENT-007'),
  ('aarav-lifesciences', 'DOC-REG-001 — Drug Manufacturing Licence',        'documents/DOC-REG-001.pdf', 'extracted',    '["REQ-0003"]'::jsonb,              'DOC-REG-001'),
  ('aarav-lifesciences', 'DOC-REG-002 — Drug Licence Renewal',              'documents/DOC-REG-002.pdf', 'extracted',    '["REQ-0003"]'::jsonb,              'DOC-REG-002'),
  ('aarav-lifesciences', 'DOC-REG-003 — Gmp Certificate',                   'documents/DOC-REG-003.pdf', 'extracted',    '["REQ-0003"]'::jsonb,              'DOC-REG-003'),
  ('aarav-lifesciences', 'DOC-REG-004 — Who Gmp Certificate',               'documents/DOC-REG-004.pdf', 'extracted',    '["REQ-0003"]'::jsonb,              'DOC-REG-004'),
  ('aarav-lifesciences', 'DOC-REG-005 — Product Approval',                  'documents/DOC-REG-005.pdf', 'missing-info', '[]'::jsonb,                        'DOC-REG-005'),
  ('aarav-lifesciences', 'DOC-REG-006 — State Drug Authority Registration', 'documents/DOC-REG-006.pdf', 'mismatch',     '["REQ-0003"]'::jsonb,              'DOC-REG-006'),
  ('aarav-lifesciences', 'DOC-REG-007 — Certificate Of Analysis',           'documents/DOC-REG-007.pdf', 'extracted',    '[]'::jsonb,                        'DOC-REG-007'),
  ('aarav-lifesciences', 'DOC-REG-008 — Batch Manufacturing Record',        'documents/DOC-REG-008.pdf', 'extracted',    '[]'::jsonb,                        'DOC-REG-008'),
  ('aarav-lifesciences', 'DOC-REG-009 — Stability Report',                  'documents/DOC-REG-009.pdf', 'extracted',    '[]'::jsonb,                        'DOC-REG-009'),
  ('aarav-lifesciences', 'DOC-REG-010 — Product Label',                     'documents/DOC-REG-010.pdf', 'extracted',    '[]'::jsonb,                        'DOC-REG-010'),
  ('aarav-lifesciences', 'DOC-REG-011 — Package Insert',                    'documents/DOC-REG-011.pdf', 'extracted',    '[]'::jsonb,                        'DOC-REG-011'),
  ('aarav-lifesciences', 'DOC-FAC-001 — Factory Licence',                   'documents/DOC-FAC-001.pdf', 'mismatch',     '[]'::jsonb,                        'DOC-FAC-001'),
  ('aarav-lifesciences', 'DOC-FAC-002 — Fire Safety Noc',                   'documents/DOC-FAC-002.pdf', 'extracted',    '[]'::jsonb,                        'DOC-FAC-002'),
  ('aarav-lifesciences', 'DOC-FAC-003 — Pollution Consent',                 'documents/DOC-FAC-003.pdf', 'extracted',    '["REQ-0001","REQ-0002"]'::jsonb,   'DOC-FAC-003'),
  ('aarav-lifesciences', 'DOC-FAC-004 — Facility Inspection Report',        'documents/DOC-FAC-004.pdf', 'extracted',    '[]'::jsonb,                        'DOC-FAC-004')
on conflict (project_id, external_document_id) where external_document_id is not null do update set
  name                   = excluded.name,
  storage_path           = excluded.storage_path,
  status                 = excluded.status,
  linked_requirement_ids = excluded.linked_requirement_ids;

-- =====================================================================================
-- 4. COMPANIES — new table (no Company model exists anywhere in the current backend)
-- =====================================================================================
-- Text primary key (COMP-0001) preserved unchanged, matching every other IRIS id scheme
-- (projects.id, REQ-####, DOC-####). project_id links company -> project (1:1 in this
-- dataset; nullable because a company entity could in principle exist before a project
-- record does).
create table if not exists public.companies (
  company_id                      text primary key,
  legal_name                      text not null,
  trade_name                      text,
  cin                             text,
  pan                             text,
  gstin                           text,
  tan                             text,
  incorporation_date              date,
  constitution                    text,
  industry                        text,
  registered_address              jsonb not null default '{}'::jsonb,
  principal_place_of_business     jsonb not null default '{}'::jsonb,
  manufacturing_facility          jsonb not null default '{}'::jsonb,
  authorized_signatory            jsonb not null default '{}'::jsonb,  -- {name, designation} — not sensitive
  contact                         jsonb not null default '{}'::jsonb,  -- {email, phone} — RESTRICTED, see grants below
  bank                            jsonb not null default '{}'::jsonb,  -- {bank_name, account_no, ifsc} — RESTRICTED, see grants below
  business_activities             text[] not null default '{}',
  manufacturer_distributor_role   text,
  project_id                      text references public.projects(id) on delete set null,
  created_at                      timestamptz not null default now(),
  updated_at                      timestamptz not null default now()
);

comment on table public.companies is
  'Company/entity master data (CIN/PAN/GSTIN/TAN/directors/bank). No Company model exists '
  'anywhere in the current IRIS backend (confirmed against app/schemas.py) — this is '
  'descriptive/reference data for the frontend only, not consumed by any engine or API '
  'contract. contact and bank columns are deliberately excluded from the authenticated '
  'grant below (see RLS section) — do not widen that grant to include them.';

create index if not exists idx_companies_project on public.companies(project_id);

alter table public.companies enable row level security;

insert into public.companies (
  company_id, legal_name, trade_name, cin, pan, gstin, tan, incorporation_date, constitution, industry,
  registered_address, principal_place_of_business, manufacturing_facility, authorized_signatory, contact, bank,
  business_activities, manufacturer_distributor_role, project_id
) values (
  'COMP-0001',
  'Aarav Lifesciences Private Limited',
  'Aarav Lifesciences',
  'U24232UK2019PTC012345',
  'AAACA1234C',
  '05AAACA1234C1Z5',
  'DEHA12345F',
  date '2019-03-14',
  'Private Limited Company (Companies Act, 2013)',
  'Pharmaceutical - Formulations Manufacturing',
  '{"line1":"Plot No. 42, Sector 5","area":"Selaqui Industrial Area","city":"Dehradun","state":"Uttarakhand","pincode":"248011"}'::jsonb,
  '{"line1":"Plot No. 42, Sector 5","area":"Selaqui Industrial Area","city":"Dehradun","state":"Uttarakhand","pincode":"248011"}'::jsonb,
  '{"line1":"Plot No. 42, Sector 5","area":"Selaqui Industrial Area","city":"Dehradun","state":"Uttarakhand","pincode":"248011"}'::jsonb,
  '{"name":"Rohan Vikram Sharma","designation":"Managing Director"}'::jsonb,
  '{"email":"compliance@aaravlifesciences.example","phone":"+91-135-2XXXXXX"}'::jsonb,
  '{"bank_name":"Synthetic National Bank","account_no":"XXXXXXXX7890","ifsc":"SYNB0001234"}'::jsonb,
  array['Manufacture of pharmaceutical formulations','Sale/distribution of formulations'],
  'Manufacturer',
  'aarav-lifesciences'
)
on conflict (company_id) do update set
  legal_name = excluded.legal_name, trade_name = excluded.trade_name, cin = excluded.cin, pan = excluded.pan,
  gstin = excluded.gstin, tan = excluded.tan, incorporation_date = excluded.incorporation_date,
  constitution = excluded.constitution, industry = excluded.industry,
  registered_address = excluded.registered_address, principal_place_of_business = excluded.principal_place_of_business,
  manufacturing_facility = excluded.manufacturing_facility, authorized_signatory = excluded.authorized_signatory,
  contact = excluded.contact, bank = excluded.bank, business_activities = excluded.business_activities,
  manufacturer_distributor_role = excluded.manufacturer_distributor_role, project_id = excluded.project_id,
  updated_at = now();

-- =====================================================================================
-- 5. COMPANY DIRECTORS — new table, 1:many with companies
-- =====================================================================================
create table if not exists public.company_directors (
  id            uuid primary key default gen_random_uuid(),
  company_id    text not null references public.companies(company_id) on delete cascade,
  name          text not null,
  designation   text,
  din           text,   -- Director Identification Number (India) — synthetic here
  created_at    timestamptz not null default now(),
  unique (company_id, din)
);

comment on table public.company_directors is
  'One row per director of a company. Synthetic DINs in this dataset.';

create index if not exists idx_company_directors_company on public.company_directors(company_id);

alter table public.company_directors enable row level security;

insert into public.company_directors (company_id, name, designation, din)
values
  ('COMP-0001', 'Rohan Vikram Sharma', 'Managing Director',     '08123456'),
  ('COMP-0001', 'Ananya Kapoor',       'Whole-time Director',   '08123457')
on conflict (company_id, din) do update set
  name = excluded.name, designation = excluded.designation;

-- =====================================================================================
-- 6. PRODUCTS — new table (no Product model exists anywhere in the current backend)
-- =====================================================================================
create table if not exists public.products (
  product_id                text primary key,
  company_id                text not null references public.companies(company_id) on delete cascade,
  product_name               text not null,
  generic_name               text,
  brand_name                 text,
  dosage_form                text,
  strength                   text,
  composition                text,
  pack_size                  text,
  manufacturer               text,
  marketer                   text,
  product_category           text,
  regulatory_classification  text,
  hsn                        text,
  batch_number               text,
  manufacturing_date         date,
  expiry_date                date,
  storage_conditions         text,
  intended_use               text,
  product_status             text not null default 'Active',
  applicable_regulations     text[] not null default '{}',  -- simple homogeneous list of Act/Rules names — array is the right fit, not jsonb
  notes                      text,
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now()
);

comment on table public.products is
  'Product master data. No Product model exists anywhere in the current IRIS backend '
  '(confirmed against app/schemas.py) — descriptive/reference data for the frontend only. '
  'Product <-> licence/document relationships live in product_documents, not as an array '
  'column here, because that relationship carries its own attribute (relationship_type).';

create index if not exists idx_products_company on public.products(company_id);

alter table public.products enable row level security;

insert into public.products (
  product_id, company_id, product_name, generic_name, brand_name, dosage_form, strength, composition, pack_size,
  manufacturer, marketer, product_category, regulatory_classification, hsn, batch_number,
  manufacturing_date, expiry_date, storage_conditions, intended_use, product_status, applicable_regulations, notes
) values
  ('PRD-0001', 'COMP-0001', 'Paracetamol Tablets IP 500 mg', 'Paracetamol', 'Aaravcet-500', 'Tablet', '500 mg',
   'Each uncoated tablet contains Paracetamol IP 500 mg', '10x10 tablets (Blister)',
   'Aarav Lifesciences Private Limited', 'Aarav Lifesciences Private Limited', 'Analgesic / Antipyretic', 'Schedule H',
   '30049099', 'ACT-24-1187', date '2025-11-01', date '2027-10-31',
   'Store below 30°C, protect from light and moisture', 'Fever and mild-to-moderate pain relief', 'Active',
   array['Drugs and Cosmetics Act, 1940','Drugs and Cosmetics Rules, 1945'], null),
  ('PRD-0002', 'COMP-0001', 'Azithromycin Tablets 500 mg', 'Azithromycin', 'Aaravzith-500', 'Tablet', '500 mg',
   'Each film-coated tablet contains Azithromycin (as dihydrate) equivalent to Azithromycin 500 mg', '1x3 tablets (Alu-Alu)',
   'Aarav Lifesciences Private Limited', 'Aarav Lifesciences Private Limited', 'Antibiotic (Macrolide)', 'Schedule H',
   '30042099', 'ACT-24-2043', date '2025-08-15', date '2027-07-31',
   'Store below 25°C, protect from light and moisture', 'Bacterial infections susceptible to azithromycin', 'Active',
   array['Drugs and Cosmetics Act, 1940','Drugs and Cosmetics Rules, 1945'],
   'Stability report intentionally omitted — see scenario SCN-0005 (missing evidence).'),
  ('PRD-0003', 'COMP-0001', 'ORS Powder', 'Oral Rehydration Salts', 'Aaravlyte', 'Powder for oral solution', '21.8 g/sachet',
   'Sodium chloride, potassium chloride, sodium citrate, dextrose anhydrous (WHO formula)', '1 sachet (reconstitute in 1 L water)',
   'Aarav Lifesciences Private Limited', 'Aarav Lifesciences Private Limited', 'Fluid & Electrolyte Replenisher', 'Non-Schedule (OTC)',
   '30049011', 'ACT-25-0512', date '2025-12-01', date '2027-11-30',
   'Store in a cool, dry place below 30°C', 'Prevention/treatment of dehydration', 'Active',
   array['Drugs and Cosmetics Act, 1940','Drugs and Cosmetics Rules, 1945'], null)
on conflict (product_id) do update set
  company_id = excluded.company_id, product_name = excluded.product_name, generic_name = excluded.generic_name,
  brand_name = excluded.brand_name, dosage_form = excluded.dosage_form, strength = excluded.strength,
  composition = excluded.composition, pack_size = excluded.pack_size, manufacturer = excluded.manufacturer,
  marketer = excluded.marketer, product_category = excluded.product_category,
  regulatory_classification = excluded.regulatory_classification, hsn = excluded.hsn, batch_number = excluded.batch_number,
  manufacturing_date = excluded.manufacturing_date, expiry_date = excluded.expiry_date,
  storage_conditions = excluded.storage_conditions, intended_use = excluded.intended_use,
  product_status = excluded.product_status, applicable_regulations = excluded.applicable_regulations,
  notes = excluded.notes, updated_at = now();

-- =====================================================================================
-- 7. COMPLIANCE SCENARIOS — new table, narrative/demo data ONLY
-- =====================================================================================
-- CRITICAL: these are NOT engine Decisions. The frozen iris_engine has exactly 14
-- Conditions today, none of which check document dates or cross-document name/address
-- equality (confirmed in the ZIP's own mapping file). expected_result is authored demo
-- narrative, not a computed value — do not wire a frontend "Compliance" badge to this
-- table and imply the Phase 9 engine produced it. Engine Decisions live in
-- public.decisions (migration 0001) and are keyed by requirement_id, not scenario_id;
-- there is no relationship between the two beyond both concerning the same project.
create table if not exists public.compliance_scenarios (
  scenario_id       text primary key,
  company_id        text references public.companies(company_id) on delete set null,
  title             text not null,
  input_document_ids text[] not null default '{}',
  expected_result   text not null,
  reason            text,
  created_at        timestamptz not null default now()
);

comment on table public.compliance_scenarios is
  'Narrative/demo compliance scenarios (expired licence, name mismatch, address mismatch, '
  'missing evidence, review-required, etc). NOT engine-evaluated Decisions — the frozen '
  'iris_engine has no Condition type capable of evaluating dates or cross-document '
  'identity matching (14 conditions total, none of this kind). Do not present these as '
  'engine-verified in the UI; label them as demo/reference scenarios.';

create index if not exists idx_compliance_scenarios_company on public.compliance_scenarios(company_id);

alter table public.compliance_scenarios enable row level security;

insert into public.compliance_scenarios (scenario_id, company_id, title, input_document_ids, expected_result, reason)
values
  ('SCN-0001', 'COMP-0001', 'Fully compliant — clean baseline',
   array['DOC-ENT-001','DOC-ENT-002','DOC-ENT-003','DOC-ENT-004','DOC-ENT-005','DOC-ENT-007',
         'DOC-REG-001','DOC-REG-004','DOC-REG-007','DOC-REG-008','DOC-REG-009','DOC-REG-010','DOC-REG-011',
         'DOC-FAC-002','DOC-FAC-003','DOC-FAC-004'],
   'GREEN / COMPLIANT',
   'All identifiers, names, addresses and dates agree across entity, product and facility documents.'),
  ('SCN-0002', 'COMP-0001', 'Expired licence',
   array['DOC-REG-006'],
   'RED / NON-COMPLIANT',
   'State Drug Authority Registration expiry_date (2021-04-30) is before the demo evaluation date (2026-09-06).'),
  ('SCN-0003', 'COMP-0001', 'Entity name mismatch',
   array['DOC-ENT-003','DOC-ENT-006'],
   'AMBER / POTENTIAL MISMATCH',
   'GST certificate (DOC-ENT-003) shows "Aarav Lifesciences Private Limited"; address proof (DOC-ENT-006) shows "Aarav Life Sciences Pvt Ltd" — same entity, subtle wording difference for entity-resolution to catch.'),
  ('SCN-0004', 'COMP-0001', 'Address mismatch',
   array['DOC-ENT-003','DOC-FAC-001'],
   'AMBER / INCONSISTENCY',
   'GST/registered address (DOC-ENT-003) is Plot No. 42, Sector 5; factory licence (DOC-FAC-001) lists Plot No. 44, Sector 5, same locality.'),
  ('SCN-0005', 'COMP-0001', 'Missing evidence',
   array['DOC-REG-011'],
   'AMBER / EVIDENCE MISSING',
   'Azithromycin Tablets 500 mg (PRD-0002) has no stability report on file — DOC-REG-009 (stability report) exists only for PRD-0001, intentionally not generated for PRD-0002.'),
  ('SCN-0006', 'COMP-0001', 'Product/regulatory mismatch — review required',
   array['DOC-REG-005'],
   'AMBER / REVIEW REQUIRED',
   'PRD-0002 is classified Schedule H (antibiotic); its product manufacturing permission (DOC-REG-005) does not carry an antimicrobial-stewardship endorsement field, so a classification rule keyed on product_category=Antibiotic would route this to human review rather than auto-approve.'),
  ('SCN-0007', 'COMP-0001', 'Invoice/product inconsistency',
   array[]::text[],
   'NOT GENERATED IN THIS DELIVERY',
   'This scenario needs GST sales-invoice records (a later phase of the original brief), which were out of scope for this documents-only delivery — recorded here so it is not silently dropped if the fuller dataset is requested later.'),
  ('SCN-0008', 'COMP-0001', 'Valid/compliant renewal',
   array['DOC-REG-002','DOC-REG-003'],
   'GREEN',
   'Drug licence renewal (DOC-REG-002) and GMP certificate (DOC-REG-003) are both correctly renewed and currently valid as of the demo evaluation date.')
on conflict (scenario_id) do update set
  company_id = excluded.company_id, title = excluded.title, input_document_ids = excluded.input_document_ids,
  expected_result = excluded.expected_result, reason = excluded.reason;

-- =====================================================================================
-- 8. DOCUMENT METADATA — new table, rich descriptive fields NOT present in public.documents
-- =====================================================================================
-- public.documents (section 3 above) already owns: name, storage_path, status (the
-- extraction-pipeline status: uploaded/extracted/missing-info/mismatch), and
-- linked_requirement_ids. This table adds everything the source manifest carries that
-- public.documents has no column for, and links back to the corresponding
-- public.documents row via iris_document_id — no duplicated/conflicting "status" column
-- (manifest_status below is a DIFFERENT concept: document master-data lifecycle state,
-- not extraction-pipeline state; do not conflate the two).
create table if not exists public.document_metadata (
  document_id           text primary key,                       -- e.g. 'DOC-ENT-001', matches the source manifest's document_id
  company_id            text not null references public.companies(company_id) on delete cascade,
  iris_document_id      uuid references public.documents(id) on delete set null,   -- link to the engine-facing register row
  document_type         text not null
                          check (document_type in (
                            'REGISTRATION_CERTIFICATE','ENVIRONMENTAL_CONSENT','FIRE_CERTIFICATE','SITE_PLAN',
                            'PROJECT_REPORT','INVESTMENT_DECLARATION','PROOF_OF_PREMISES','OTHER','UNKNOWN'
                          )),                                    -- exact frozen enum: backend/app/modules/ai/schemas.py::DocumentType
  pharma_subtype        text,                                    -- descriptive sub-classification; not an IRIS-owned enum
  document_number       text,
  issue_date            date,
  effective_date        date,
  expiry_date           date,
  issuing_authority     text,
  related_product_id    text references public.products(product_id) on delete set null,
  scenario_id           text references public.compliance_scenarios(scenario_id) on delete set null,
  manifest_source       text,                                    -- e.g. 'synthetic_generation' — provenance of the record, not the file
  manifest_version      integer not null default 1,
  manifest_status       text not null default 'ACTIVE',          -- document MASTER-DATA lifecycle status — see comment above, distinct from public.documents.status
  extracted_text        text,                                    -- full extracted text (documents_text/*.txt) — every file here is <1KB, inlining is appropriate; large scans should go through the real OCR pipeline instead
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

comment on table public.document_metadata is
  'Rich descriptive metadata per document (type, number, authority, dates, related '
  'product, scenario, extracted text). Complements public.documents (which owns the '
  'extraction-pipeline status and linked_requirement_ids) via iris_document_id — '
  'deliberately not duplicating those columns here to avoid two sources of truth.';

create index if not exists idx_document_metadata_company    on public.document_metadata(company_id);
create index if not exists idx_document_metadata_product    on public.document_metadata(related_product_id);
create index if not exists idx_document_metadata_scenario   on public.document_metadata(scenario_id);
create index if not exists idx_document_metadata_iris_doc   on public.document_metadata(iris_document_id);
create index if not exists idx_document_metadata_expiry     on public.document_metadata(expiry_date) where expiry_date is not null;

alter table public.document_metadata enable row level security;

insert into public.document_metadata (
  document_id, company_id, iris_document_id, document_type, pharma_subtype, document_number,
  issue_date, effective_date, expiry_date, issuing_authority, related_product_id, scenario_id,
  manifest_source, manifest_version, manifest_status, extracted_text
) values
('DOC-ENT-001', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-ENT-001'),
 'OTHER', 'PAN_CARD', 'AAACA1234C', date '2019-03-20', date '2019-03-20', null,
 'Income Tax Department (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Permanent Account Number (PAN)
Issuing Authority: Income Tax Department (synthetic)
Document No.: AAACA1234C | Document ID: DOC-ENT-001
Issue Date: 2019-03-20 | Effective: 2019-03-20 | Expiry: N/A




Particulars
 Legal Name:                                 Aarav Lifesciences Private Limited
 PAN:                                        AAACA1234C
 Date of Incorporation:                      2019-03-14




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-ENT-002', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-ENT-002'),
 'REGISTRATION_CERTIFICATE', 'CERT_OF_INCORPORATION', 'U24232UK2019PTC012345', date '2019-03-14', date '2019-03-14', null,
 'Registrar of Companies, Uttarakhand (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Certificate of Incorporation
Issuing Authority: Registrar of Companies, Uttarakhand (synthetic)
Document No.: U24232UK2019PTC012345 | Document ID: DOC-ENT-002
Issue Date: 2019-03-14 | Effective: 2019-03-14 | Expiry: N/A




Particulars
 Company Name:                               Aarav Lifesciences Private Limited
 CIN:                                        U24232UK2019PTC012345
 Date of Incorporation:                      2019-03-14
 Registered Office:                          Plot No. 42, Sector 5, Selaqui Industrial Area, Dehradun, Uttarakhand - 248011




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-ENT-003', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-ENT-003'),
 'REGISTRATION_CERTIFICATE', 'GST_REGISTRATION_CERTIFICATE', '05AAACA1234C1Z5', date '2019-04-05', date '2019-04-05', null,
 'Goods and Services Tax Network (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



GST Registration Certificate (Form GST REG-06)
Issuing Authority: Goods and Services Tax Network (synthetic)
Document No.: 05AAACA1234C1Z5 | Document ID: DOC-ENT-003
Issue Date: 2019-04-05 | Effective: 2019-04-05 | Expiry: N/A




Particulars
 Legal Name:                                 Aarav Lifesciences Private Limited
 Trade Name:                                 Aarav Lifesciences
 GSTIN:                                      05AAACA1234C1Z5
 Constitution:                               Private Limited Company (Companies Act, 2013)
 Principal Place of Business:                Plot No. 42, Sector 5, Selaqui Industrial Area, Dehradun, Uttarakhand - 248011
 Taxpayer Type:                              Regular




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-ENT-004', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-ENT-004'),
 'OTHER', 'TAN_RECORD', 'DEHA12345F', date '2019-04-10', date '2019-04-10', null,
 'Income Tax Department (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Tax Deduction and Collection Account Number (TAN)
Issuing Authority: Income Tax Department (synthetic)
Document No.: DEHA12345F | Document ID: DOC-ENT-004
Issue Date: 2019-04-10 | Effective: 2019-04-10 | Expiry: N/A




Particulars
 Deductor Name:                              Aarav Lifesciences Private Limited
 TAN:                                        DEHA12345F




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-ENT-005', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-ENT-005'),
 'OTHER', 'AUTHORIZED_SIGNATORY_PAN', 'AXXPS9821K', date '2010-06-11', date '2010-06-11', null,
 'Income Tax Department (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Authorized Signatory PAN
Issuing Authority: Income Tax Department (synthetic)
Document No.: AXXPS9821K | Document ID: DOC-ENT-005
Issue Date: 2010-06-11 | Effective: 2010-06-11 | Expiry: N/A




Particulars
 Name:                                       Rohan Vikram Sharma
 Designation:                                Managing Director
 PAN:                                        AXXPS9821K




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-ENT-006', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-ENT-006'),
 'PROOF_OF_PREMISES', 'ADDRESS_PROOF', 'UPCL/DDN/889231', date '2026-08-01', date '2026-08-01', null,
 'Uttarakhand Power Corporation Ltd (synthetic)', null, 'SCN-0003', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Address Proof — Electricity Bill
Issuing Authority: Uttarakhand Power Corporation Ltd (synthetic)
Document No.: UPCL/DDN/889231 | Document ID: DOC-ENT-006
Issue Date: 2026-08-01 | Effective: 2026-08-01 | Expiry: N/A




Particulars
 Consumer Name:                              Aarav Life Sciences Pvt Ltd
 Service Address:                            Plot No. 42, Sector 5, Selaqui Industrial Area, Dehradun, Uttarakhand - 248011
 Consumer Number:                            889231


Demo note: Entity name mismatch vs GST certificate ("Aarav Life Sciences Pvt Ltd" here vs "Aarav Lifesciences Private Limited" on DOC-ENT-003).




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-ENT-007', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-ENT-007'),
 'OTHER', 'CANCELLED_CHEQUE', 'XXXXXXXX7890', date '2019-04-15', date '2019-04-15', null,
 'Synthetic National Bank (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Bank Account Record — Cancelled Cheque
Issuing Authority: Synthetic National Bank (synthetic)
Document No.: XXXXXXXX7890 | Document ID: DOC-ENT-007
Issue Date: 2019-04-15 | Effective: 2019-04-15 | Expiry: N/A




Particulars
 Account Holder:                             Aarav Lifesciences Private Limited
 Account No.:                                XXXXXXXX7890
 IFSC:                                       SYNB0001234




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-001', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-001'),
 'REGISTRATION_CERTIFICATE', 'DRUG_MANUFACTURING_LICENCE', 'UK/DL/2019/00417', date '2019-07-01', date '2019-07-01', date '2029-06-30',
 'Uttarakhand State Drug Controller (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Drug Manufacturing Licence (Form 25)
Issuing Authority: Uttarakhand State Drug Controller (synthetic)
Document No.: UK/DL/2019/00417 | Document ID: DOC-REG-001
Issue Date: 2019-07-01 | Effective: 2019-07-01 | Expiry: 2029-06-30




Particulars
 Licensee:                                   Aarav Lifesciences Private Limited
 Licence No.:                                UK/DL/2019/00417
 Valid Upto:                                 2029-06-30
 Category:                                   Formulations - Tablets/Powders




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-002', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-002'),
 'REGISTRATION_CERTIFICATE', 'DRUG_LICENCE_RENEWAL', 'UK/DL/2019/00417-R1', date '2024-06-15', date '2024-07-01', date '2029-06-30',
 'Uttarakhand State Drug Controller (synthetic)', null, 'SCN-0008', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Drug Manufacturing Licence — Renewal Record
Issuing Authority: Uttarakhand State Drug Controller (synthetic)
Document No.: UK/DL/2019/00417-R1 | Document ID: DOC-REG-002
Issue Date: 2024-06-15 | Effective: 2024-07-01 | Expiry: 2029-06-30




Particulars
 Original Licence No.:                       UK/DL/2019/00417
 Renewal Order No.:                          UK/DL/2019/00417-R1
 Renewed Valid Upto:                         2029-06-30




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-003', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-003'),
 'OTHER', 'GMP_CERTIFICATE', 'GMP/UK/2024/2211', date '2024-02-10', date '2024-02-10', date '2027-02-09',
 'Uttarakhand State Drug Controller (synthetic)', null, 'SCN-0008', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Good Manufacturing Practice (GMP) Certificate — Schedule M
Issuing Authority: Uttarakhand State Drug Controller (synthetic)
Document No.: GMP/UK/2024/2211 | Document ID: DOC-REG-003
Issue Date: 2024-02-10 | Effective: 2024-02-10 | Expiry: 2027-02-09




Particulars
 Certificate No.:                            GMP/UK/2024/2211
 Standard:                                   Schedule M, Drugs & Cosmetics Rules 1945
 Valid Upto:                                 2027-02-09




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-004', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-004'),
 'OTHER', 'WHO_GMP_CERTIFICATE', 'WHOGMP/UK/2023/0871', date '2023-09-05', date '2023-09-05', date '2026-09-04',
 'Uttarakhand State Drug Controller (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



WHO-GMP Certificate
Issuing Authority: Uttarakhand State Drug Controller (synthetic)
Document No.: WHOGMP/UK/2023/0871 | Document ID: DOC-REG-004
Issue Date: 2023-09-05 | Effective: 2023-09-05 | Expiry: 2026-09-04




Particulars
 Certificate No.:                            WHOGMP/UK/2023/0871
 Standard:                                   WHO Technical Report Series 961, Annex 3
 Valid Upto:                                 2026-09-04




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-005', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-005'),
 'OTHER', 'PRODUCT_APPROVAL', 'UK/PA/2023/3390', date '2023-01-20', date '2023-01-20', null,
 'Uttarakhand State Drug Controller (synthetic)', 'PRD-0002', 'SCN-0006', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Product Manufacturing Permission
Issuing Authority: Uttarakhand State Drug Controller (synthetic)
Document No.: UK/PA/2023/3390 | Document ID: DOC-REG-005
Issue Date: 2023-01-20 | Effective: 2023-01-20 | Expiry: N/A




Particulars
 Product:                                    Azithromycin Tablets 500 mg
 Approval No.:                               UK/PA/2023/3390


Demo note: Product classified Schedule H antibiotic; permission on file does not carry an antimicrobial-stewardship endorsement — flagged for review under RULE checks that key on product_category=Antibiotic.




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-006', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-006'),
 'REGISTRATION_CERTIFICATE', 'STATE_DRUG_AUTHORITY_REGISTRATION', 'UK/SDA/REG/2016/0098', date '2016-05-01', date '2016-05-01', date '2021-04-30',
 'Uttarakhand State Drug Controller (synthetic)', null, 'SCN-0002', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



State Drug Authority Registration
Issuing Authority: Uttarakhand State Drug Controller (synthetic)
Document No.: UK/SDA/REG/2016/0098 | Document ID: DOC-REG-006
Issue Date: 2016-05-01 | Effective: 2016-05-01 | Expiry: 2021-04-30




Particulars
    Registration No.:                        UK/SDA/REG/2016/0098
    Valid Upto:                              2021-04-30 (EXPIRED)


Demo note: expiry_date (2021-04-30) is before the demo evaluation date (2026-09-06) — expected result RED / NON-COMPLIANT.




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-007', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-007'),
 'OTHER', 'CERTIFICATE_OF_ANALYSIS', 'COA-ACT-24-1187', date '2025-11-02', date '2025-11-02', null,
 'Aarav Lifesciences QC Laboratory', 'PRD-0001', 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Certificate of Analysis
Issuing Authority: Aarav Lifesciences QC Laboratory
Document No.: COA-ACT-24-1187 | Document ID: DOC-REG-007
Issue Date: 2025-11-02 | Effective: 2025-11-02 | Expiry: N/A




Particulars
 Product:                                    Paracetamol Tablets IP 500 mg
 Batch No.:                                  ACT-24-1187
 Assay:                                      99.2% w/w
 Result:                                     Complies




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-008', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-008'),
 'OTHER', 'BATCH_MANUFACTURING_RECORD', 'BMR-ACT-24-1187', date '2025-11-01', date '2025-11-01', null,
 'Aarav Lifesciences Production Department', 'PRD-0001', 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Batch Manufacturing Record (Summary)
Issuing Authority: Aarav Lifesciences Production Department
Document No.: BMR-ACT-24-1187 | Document ID: DOC-REG-008
Issue Date: 2025-11-01 | Effective: 2025-11-01 | Expiry: N/A




Particulars
 Product:                                    Paracetamol Tablets IP 500 mg
 Batch No.:                                  ACT-24-1187
 Batch Size:                                 5,00,000 tablets
 Reviewed By:                                QA Officer




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-009', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-009'),
 'OTHER', 'STABILITY_REPORT', 'STB-ACT-24-1187', date '2025-10-20', date '2025-10-20', null,
 'Aarav Lifesciences QC Laboratory', 'PRD-0001', 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Stability Study Report
Issuing Authority: Aarav Lifesciences QC Laboratory
Document No.: STB-ACT-24-1187 | Document ID: DOC-REG-009
Issue Date: 2025-10-20 | Effective: 2025-10-20 | Expiry: N/A




Particulars
 Product:                                    Paracetamol Tablets IP 500 mg
 Study Type:                                 Accelerated + Long-term
 Conclusion:                                 Stable for proposed 24-month shelf life




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-010', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-010'),
 'OTHER', 'PRODUCT_LABEL', 'LBL-PRD-0003', date '2025-11-15', date '2025-11-15', null,
 'Aarav Lifesciences Regulatory Affairs', 'PRD-0003', 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Product Label
Issuing Authority: Aarav Lifesciences Regulatory Affairs
Document No.: LBL-PRD-0003 | Document ID: DOC-REG-010
Issue Date: 2025-11-15 | Effective: 2025-11-15 | Expiry: N/A




Particulars
 Product:                                    ORS Powder
 Batch No.:                                  ACT-25-0512




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-REG-011', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-REG-011'),
 'OTHER', 'PACKAGE_INSERT', 'PI-PRD-0002', date '2025-08-01', date '2025-08-01', null,
 'Aarav Lifesciences Regulatory Affairs', 'PRD-0002', 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Package Insert
Issuing Authority: Aarav Lifesciences Regulatory Affairs
Document No.: PI-PRD-0002 | Document ID: DOC-REG-011
Issue Date: 2025-08-01 | Effective: 2025-08-01 | Expiry: N/A




Particulars
 Product:                                    Azithromycin Tablets 500 mg
 Batch No.:                                  ACT-24-2043




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-FAC-001', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-FAC-001'),
 'PROOF_OF_PREMISES', 'FACTORY_LICENCE', 'UK/FAC/2019/5521', date '2019-08-01', date '2019-08-01', date '2027-12-31',
 'Chief Inspector of Factories, Uttarakhand (synthetic)', null, 'SCN-0004', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Factory Licence (Factories Act, 1948)
Issuing Authority: Chief Inspector of Factories, Uttarakhand (synthetic)
Document No.: UK/FAC/2019/5521 | Document ID: DOC-FAC-001
Issue Date: 2019-08-01 | Effective: 2019-08-01 | Expiry: 2027-12-31




Particulars
 Occupier:                                   Aarav Lifesciences Private Limited
 Licence No.:                                UK/FAC/2019/5521
 Premises:                                   Plot No. 44, Sector 5, Selaqui Industrial Area, Dehradun, Uttarakhand - 248011


Demo note: Premises address (Plot No. 44) differs from the GST/registered address (Plot No. 42) on DOC-ENT-003 — expected result AMBER / INCONSISTENCY.




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-FAC-002', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-FAC-002'),
 'FIRE_CERTIFICATE', 'FIRE_SAFETY_NOC', 'FIRE/UK/2025/1187', date '2025-01-10', date '2025-01-10', date '2028-01-09',
 'Uttarakhand Fire Services (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Fire Safety No-Objection Certificate
Issuing Authority: Uttarakhand Fire Services (synthetic)
Document No.: FIRE/UK/2025/1187 | Document ID: DOC-FAC-002
Issue Date: 2025-01-10 | Effective: 2025-01-10 | Expiry: 2028-01-09




Particulars
 Premises:                                   Plot No. 42, Sector 5, Selaqui Industrial Area, Dehradun, Uttarakhand - 248011
 Certificate No.:                            FIRE/UK/2025/1187




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-FAC-003', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-FAC-003'),
 'ENVIRONMENTAL_CONSENT', 'POLLUTION_CONSENT', 'UEPPCB/CTO/2025/774', date '2025-03-01', date '2025-03-01', date '2028-02-29',
 'Uttarakhand Environment Protection & Pollution Control Board (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Consent to Operate — Pollution Control Board
Issuing Authority: Uttarakhand Environment Protection & Pollution Control Board (synthetic)
Document No.: UEPPCB/CTO/2025/774 | Document ID: DOC-FAC-003
Issue Date: 2025-03-01 | Effective: 2025-03-01 | Expiry: 2028-02-29




Particulars
 Unit:                                       Aarav Lifesciences Private Limited
 Consent No.:                                UEPPCB/CTO/2025/774
 Category:                                   Orange




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.'),

('DOC-FAC-004', 'COMP-0001',
 (select id from public.documents where project_id='aarav-lifesciences' and external_document_id='DOC-FAC-004'),
 'OTHER', 'FACILITY_INSPECTION_REPORT', 'INSP-UK-2025-0342', date '2025-06-18', date '2025-06-18', null,
 'Uttarakhand State Drug Controller (synthetic)', null, 'SCN-0001', 'synthetic_generation', 1, 'ACTIVE',
'                       SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT



Facility Inspection Report
Issuing Authority: Uttarakhand State Drug Controller (synthetic)
Document No.: INSP-UK-2025-0342 | Document ID: DOC-FAC-004
Issue Date: 2025-06-18 | Effective: 2025-06-18 | Expiry: N/A




Particulars
 Premises:                                   Plot No. 42, Sector 5, Selaqui Industrial Area, Dehradun, Uttarakhand - 248011
 Outcome:                                    Satisfactory, no critical observations




SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT
This is a fictional document generated for the IRIS SIH-2026 prototype demo only.')
on conflict (document_id) do update set
  company_id = excluded.company_id, iris_document_id = excluded.iris_document_id,
  document_type = excluded.document_type, pharma_subtype = excluded.pharma_subtype,
  document_number = excluded.document_number, issue_date = excluded.issue_date,
  effective_date = excluded.effective_date, expiry_date = excluded.expiry_date,
  issuing_authority = excluded.issuing_authority, related_product_id = excluded.related_product_id,
  scenario_id = excluded.scenario_id, manifest_source = excluded.manifest_source,
  manifest_version = excluded.manifest_version, manifest_status = excluded.manifest_status,
  extracted_text = excluded.extracted_text, updated_at = now();

-- =====================================================================================
-- 9. PRODUCT <-> DOCUMENT JUNCTION — new table, many-to-many
-- =====================================================================================
-- Two distinct source fields produce product<->document pairs: products.json's
-- applicable_licences (licence-type documents a product is covered by) and
-- documents_manifest.json's related_product_id (documents authored specifically about
-- one product — COA, BMR, stability report, label, package insert, product approval).
-- One pair, (PRD-0002, DOC-REG-005), is asserted by BOTH sources — preserved as two rows
-- (one per relationship_type) rather than collapsed, so neither source's claim is lost.
create table if not exists public.product_documents (
  product_id        text not null references public.products(product_id) on delete cascade,
  document_id       text not null references public.document_metadata(document_id) on delete cascade,
  relationship_type text not null check (relationship_type in ('applicable_licence', 'product_specific_document')),
  created_at        timestamptz not null default now(),
  primary key (product_id, document_id, relationship_type)
);

comment on table public.product_documents is
  'Many-to-many product <-> document links. relationship_type distinguishes '
  '"applicable_licence" (from products.json applicable_licences) from '
  '"product_specific_document" (from documents_manifest.json related_product_id) — '
  'a given pair can legitimately appear under both if both sources assert it.';

create index if not exists idx_product_documents_document on public.product_documents(document_id);

alter table public.product_documents enable row level security;

insert into public.product_documents (product_id, document_id, relationship_type) values
  ('PRD-0001', 'DOC-REG-001', 'applicable_licence'),
  ('PRD-0001', 'DOC-REG-002', 'applicable_licence'),
  ('PRD-0002', 'DOC-REG-001', 'applicable_licence'),
  ('PRD-0002', 'DOC-REG-005', 'applicable_licence'),
  ('PRD-0003', 'DOC-REG-001', 'applicable_licence'),
  ('PRD-0002', 'DOC-REG-005', 'product_specific_document'),
  ('PRD-0001', 'DOC-REG-007', 'product_specific_document'),
  ('PRD-0001', 'DOC-REG-008', 'product_specific_document'),
  ('PRD-0001', 'DOC-REG-009', 'product_specific_document'),
  ('PRD-0003', 'DOC-REG-010', 'product_specific_document'),
  ('PRD-0002', 'DOC-REG-011', 'product_specific_document')
on conflict (product_id, document_id, relationship_type) do nothing;

-- =====================================================================================
-- 10. APPLICATIONS — upsert into the EXISTING public.applications (migration 0002)
-- =====================================================================================
-- Only REQ-0001 and REQ-0002 get application rows, against dept-mpcb — exactly what the
-- source dataset provides. REQ-0003 (drug manufacturing licence) intentionally has NO
-- application: no CDSCO/FDA-equivalent department is seeded in department_store.py, and
-- adding one is a source-code change, not a data change (see "Important limitations").
-- sla_policy_id: applications.json uses the human slug "sla-standard-30d"; mapped here to
-- the actual seeded policy row (name = 'Standard Review (30 days)', migration 0002) —
-- a schema-design mapping decision, not sourced data.
insert into public.applications (application_id, project_id, department_id, requirement_id, title, applicant_name, sla_policy_id)
values
  ('APP-AARAV-REQ-0001', 'aarav-lifesciences', 'dept-mpcb', 'REQ-0001',
   'Consent to Establish — Water Act (Selaqui plant)', 'Rohan Vikram Sharma',
   (select id from public.sla_policies where name = 'Standard Review (30 days)')),
  ('APP-AARAV-REQ-0002', 'aarav-lifesciences', 'dept-mpcb', 'REQ-0002',
   'Consent to Establish/Operate — Air Act (Selaqui plant)', 'Rohan Vikram Sharma',
   (select id from public.sla_policies where name = 'Standard Review (30 days)'))
on conflict (application_id) do update set
  project_id = excluded.project_id, department_id = excluded.department_id,
  requirement_id = excluded.requirement_id, title = excluded.title,
  applicant_name = excluded.applicant_name, sla_policy_id = excluded.sla_policy_id,
  updated_at = now();

-- =====================================================================================
-- 11. CONVENIENCE VIEW — documents joined with their rich metadata
-- =====================================================================================
-- security_invoker = true is REQUIRED here: without it, a view created by a role with
-- BYPASSRLS (the default table-owner role in the Supabase SQL editor) would silently
-- bypass RLS on public.documents/public.document_metadata for every caller — a well-known
-- Supabase footgun. With security_invoker, the view enforces RLS as the querying role.
create or replace view public.v_project_document_details
with (security_invoker = true) as
select
  d.project_id,
  dm.document_id,
  d.name,
  d.storage_path,
  d.status,
  d.linked_requirement_ids,
  dm.document_type,
  dm.pharma_subtype,
  dm.document_number,
  dm.issue_date,
  dm.effective_date,
  dm.expiry_date,
  (dm.expiry_date is not null and dm.expiry_date < current_date) as is_expired,
  dm.issuing_authority,
  dm.related_product_id,
  dm.scenario_id,
  dm.company_id,
  dm.extracted_text
from public.document_metadata dm
join public.documents d on d.id = dm.iris_document_id;

comment on view public.v_project_document_details is
  'Convenience join of the engine-facing documents register with descriptive metadata. '
  'is_expired is computed live from CURRENT_DATE, not a stored/cached value.';

-- =====================================================================================
-- 12. ROW LEVEL SECURITY — new tables
-- =====================================================================================
-- Pattern: SELECT-only for `authenticated`, scoped to projects the user can already see
-- under migration 0004's rules (owner_id = auth.uid(), or a government user whose
-- department has an application against the project). No anon access anywhere. No
-- INSERT/UPDATE/DELETE policies for authenticated on any of these — this is
-- reference/master data maintained by SQL script or backend service-role, not something
-- the frontend should mutate directly. service_role keeps full CRUD, as with every other
-- table in this schema.

create or replace function public.project_visible_to_current_user(p_project_id text)
returns boolean
language sql
stable
security definer
as $$
  select exists (
    select 1 from public.projects
    where id = p_project_id and owner_id = auth.uid()
  ) or exists (
    select 1 from public.applications
    where project_id = p_project_id
      and department_id = public.current_user_department_id()
  );
$$;

comment on function public.project_visible_to_current_user is
  'True if the current authenticated user owns the project OR is a government officer '
  'whose department has an application filed against it. Mirrors the visibility rules '
  'already established by migration 0004 for public.projects; reused here for the new '
  'companies/products/documents tables instead of re-deriving separate logic.';

-- companies: authenticated gets a column-restricted grant (see GRANT below) — contact
-- and bank are excluded from that grant, so even a visible row never leaks banking info.
drop policy if exists companies_select_visible on public.companies;
create policy companies_select_visible on public.companies
  for select to authenticated
  using (project_visible_to_current_user(project_id));

drop policy if exists company_directors_select_visible on public.company_directors;
create policy company_directors_select_visible on public.company_directors
  for select to authenticated
  using (
    exists (
      select 1 from public.companies c
      where c.company_id = company_directors.company_id
        and project_visible_to_current_user(c.project_id)
    )
  );

drop policy if exists products_select_visible on public.products;
create policy products_select_visible on public.products
  for select to authenticated
  using (
    exists (
      select 1 from public.companies c
      where c.company_id = products.company_id
        and project_visible_to_current_user(c.project_id)
    )
  );

drop policy if exists document_metadata_select_visible on public.document_metadata;
create policy document_metadata_select_visible on public.document_metadata
  for select to authenticated
  using (
    exists (
      select 1 from public.companies c
      where c.company_id = document_metadata.company_id
        and project_visible_to_current_user(c.project_id)
    )
  );

drop policy if exists product_documents_select_visible on public.product_documents;
create policy product_documents_select_visible on public.product_documents
  for select to authenticated
  using (
    exists (
      select 1 from public.document_metadata dm
      join public.companies c on c.company_id = dm.company_id
      where dm.document_id = product_documents.document_id
        and project_visible_to_current_user(c.project_id)
    )
  );

drop policy if exists compliance_scenarios_select_visible on public.compliance_scenarios;
create policy compliance_scenarios_select_visible on public.compliance_scenarios
  for select to authenticated
  using (
    company_id is null or exists (
      select 1 from public.companies c
      where c.company_id = compliance_scenarios.company_id
        and project_visible_to_current_user(c.project_id)
    )
  );

-- =====================================================================================
-- 13. GRANTS
-- =====================================================================================
-- service_role: full CRUD on every new table (same pattern as 0001/0002).
grant select, insert, update, delete on
  public.companies, public.company_directors, public.products,
  public.compliance_scenarios, public.document_metadata, public.product_documents
  to service_role;

-- authenticated: column-restricted on companies (NO contact, NO bank), full-row on the
-- rest (they carry no sensitive fields). RLS policies above still gate which ROWS are
-- visible; this grant only controls which COLUMNS.
grant select (
  company_id, legal_name, trade_name, cin, pan, gstin, tan, incorporation_date, constitution,
  industry, registered_address, principal_place_of_business, manufacturing_facility,
  authorized_signatory, business_activities, manufacturer_distributor_role, project_id,
  created_at, updated_at
) on public.companies to authenticated;

grant select on
  public.company_directors, public.products, public.compliance_scenarios,
  public.document_metadata, public.product_documents
  to authenticated;

grant select on public.v_project_document_details to authenticated, service_role;
