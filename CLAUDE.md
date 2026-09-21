\# IRIS — Claude Code Instructions



\## Project



IRIS — Industrial Regulatory Intelligence System.



Core principle:



AI UNDERSTANDS.

RULES DECIDE.

GRAPHS ORGANISE.

ANALYTICS IDENTIFY.

HUMANS DECIDE.



IRIS is a regulatory intelligence and assurance layer that complements

existing systems such as MAITRI / NSWS.



It is NOT intended to replace statutory government portals.



\## Architecture



Current stack includes:

\- React / TypeScript frontend

\- FastAPI / Python backend

\- Supabase / PostgreSQL

\- deterministic regulatory Rule Engine

\- NetworkX dependency analysis

\- Ollama + local Qwen

\- Tesseract image OCR

\- JWT / Supabase Auth



Always inspect the repository before assuming exact paths or interfaces.



\## Core Safety Boundary



AI may:

\- extract candidate information

\- retrieve relevant regulatory evidence

\- explain deterministic results

\- assist candidate rule extraction



AI MUST NOT:

\- determine legal/regulatory applicability

\- activate regulatory rules

\- approve/reject applications

\- override deterministic Rule Engine results

\- silently persist extracted values as verified facts

\- invent regulatory requirements or dependencies



\## Existing Working Systems



The repository already contains substantial tested functionality.



Preserve working implementations.



Do not rebuild a subsystem merely because another design looks cleaner.



Treat these as frozen unless a genuine integration bug requires otherwise:

\- deterministic Rule Engine core

\- regulatory dataset

\- NetworkX core

\- AI module core

\- existing applied Supabase migrations



If a requested feature appears to require changing a frozen core, STOP that

feature and report the blocker.



\## Engineering Policy



Prefer:



ADAPTER > CORE MODIFICATION

SERVICE > DUPLICATED LOGIC

MINIMAL CHANGE > REFACTOR

EXISTING INTERFACE > REDESIGN

DETERMINISTIC CODE > NEW LLM CALL

NEW FORWARD MIGRATION > EDITING OLD MIGRATION



Do not perform unrelated cleanup.



Do not upgrade dependencies unless required.



Do not introduce:

\- microservices

\- Kubernetes

\- Kafka

\- Redis

\- Celery

\- dedicated graph database

\- dedicated vector database

\- mandatory cloud LLM

\- custom LLM training



unless explicitly requested in a future task.



\## Regulatory Data



Never invent:

\- legal requirements

\- statutory thresholds

\- regulatory dependencies

\- statutory SLA durations

\- renewal periods

\- scheme eligibility criteria

\- grievance escalation rules

\- legal citations



Clearly distinguish:

\- verified regulatory information

\- curated prototype regulatory information

\- synthetic/demo operational data

\- architectural assumptions



Do not activate DRAFT/unverified rules merely to make the demo look better.



\## Rule Engine



Regulatory applicability must remain deterministic.



Invariant:



Same Project Facts

\+ Same Rule Version

\+ Same Evaluator/Grammar Version

= Same Regulatory Result



Historical evaluations must remain reproducible.



Do not introduce LLM calls into applicability evaluation.



\## NetworkX



NetworkX organises dependencies.



Absence of a dependency edge does NOT automatically imply legal parallelism.



Only explicit verified metadata may support parallel-workflow claims.



Do not fabricate dependencies or durations.



\## Documents / OCR



Current intended boundary:



Image

→ Tesseract OCR

→ editable text

→ local AI candidate extraction

→ confidence/evidence

→ deterministic comparison where applicable

→ human confirmation

→ Project Facts



OCR/AI output is not automatically authoritative.



Do not claim PDF OCR unless actually implemented.



\## Local AI



Prefer existing Ollama/Qwen integration.



Do not require a larger model.



Do not train/fine-tune a model.



Small local AI is intentionally used for:

\- extraction

\- retrieval

\- explanation



Deterministic systems handle regulatory decisions.



\## Authentication / Security



Preserve existing authentication, RBAC and ownership checks.



Never expose:

\- Supabase service-role keys

\- API keys

\- JWT secrets

\- passwords

\- .env contents



Government-only functionality must remain protected server-side.



Do not weaken security to simplify the demo.



\## Database



Inspect the existing schema before adding tables.



Reuse existing entities where possible.



Never edit already-applied migrations.



If schema changes are genuinely required, create a minimal new forward migration.



\## Frontend



Preserve the existing visual identity.



Reuse:

\- existing components

\- API client

\- query patterns

\- project context

\- route structure

\- typography/colors

\- status components



Do not redesign the entire frontend.



For presentation polish:

\- reduce excessive cards/pills/gradients

\- improve hierarchy and spacing

\- remove fake/decorative metrics

\- use consistent loading/error/empty states

\- keep data more prominent than decoration



Do not introduce a new UI/component framework.



\## Testing



Never:

\- delete tests

\- weaken assertions

\- skip failing tests merely to obtain green output

\- modify expected results just to match broken code



After each feature:

1\. run targeted tests

2\. fix integration failures

3\. then run broader regression tests



Before completion, run everything the environment permits:

\- Rule Engine baseline

\- NetworkX tests

\- AI non-live tests

\- Ask IRIS tests

\- OCR tests

\- integration tests

\- complete backend tests

\- frontend TypeScript check

\- frontend production build



Report exact results.



\## Git



Do NOT automatically:

\- commit

\- merge

\- push

\- rebase

\- reset

\- restore

\- switch branches

\- clean the repository



Leave implementation changes uncommitted for human review unless explicitly

instructed otherwise.



Before editing, inspect:

\- current branch

\- git status

\- existing changes



Do not overwrite pre-existing user changes.



\## Working Style / Token Efficiency



Be concise.



Do not narrate routine:

\- file reads

\- searches

\- successful commands



Search before reading whole files.



Read only relevant files/ranges where practical.



Do not repeatedly reread unchanged files.



Do not print full files unless necessary.



Do not dump successful test output; report command + counts.



Do not restate these instructions.



Spend reasoning/context on:

\- architecture boundaries

\- integration decisions

\- failures

\- security

\- data correctness



not routine operations.



\## Failure Policy



Prefer:



STOP + REPORT



over:



MODIFY STABLE CORE UNTIL IT WORKS



If blocked, report:

1\. exact blocker

2\. affected interface/file

3\. why an adapter/service cannot solve it

4\. smallest possible change required



Do not make destructive architectural changes without explicit approval.

