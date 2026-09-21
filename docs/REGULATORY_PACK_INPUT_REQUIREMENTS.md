# Regulatory Pack — Input Requirements (engineering contract)

**Audience:** the teammate verifying regulatory content from official sources.
**Status:** engineering interface specification. This document contains **no
regulatory research and no legal content**. It describes only the file shapes,
field names, ID formats and validation rules the *existing* IRIS code already
enforces, so that verified content can be loaded without any code change.

Derived by reading the current repository:

| What | Where |
|---|---|
| Loader (which directories/ID keys are read) | `backend/iris_engine/loader.py` |
| Condition evaluator (supported predicates/operators) | `backend/iris_engine/conditions.py` |
| Rule Version evaluation + lifecycle gate | `backend/iris_engine/rules.py` |
| Classification sub-groups | `backend/iris_engine/classification.py` |
| Dependencies | `backend/iris_engine/dependencies.py` |
| Provenance chain | `backend/iris_engine/provenance.py` |
| Programmatic validation | `backend/iris_engine/validate.py` |
| Live dataset | `backend/regulatory-data/` |

> **Nothing in `backend/regulatory-data/` was modified in this pass.** The four
> existing Requirements and six Rule Versions are untouched and remain DRAFT.

---

## 0. Current state (as shipped)

| Record type | Count | Directory |
|---|---|---|
| Conditions | 14 | `regulatory-data/conditions/` |
| Rules | 6 | `regulatory-data/rules/` |
| Rule Versions | 6 (**all DRAFT**) | `regulatory-data/rule-versions/` |
| Requirements | 4 | `regulatory-data/requirements/` |
| Verified dependency edges | **0** | `regulatory-data/index/dependencies_index.yaml` |

Because zero Rule Versions are `ACTIVE`, every PRODUCTION evaluation returns
`BLOCKED_DRAFT_NOT_PRODUCTION`. **That is correct fail-closed behaviour, not a
bug.** It is the single thing your verified pack changes.

---

## 1. Directory + file layout

One YAML document per file. The loader keys each record by the first `*_id`
field it finds, in this order: `condition_id`, `rule_version_id`, `rule_id`,
`requirement_id`, `dependency_id`.

```
regulatory-data/
├── conditions/     COND-####.yaml
├── rules/          RULE-####.yaml
├── rule-versions/  RULE-####-V#.yaml
├── requirements/   REQ-####.yaml
├── registers/      rule_conflict_register.yaml, rule_review_register.yaml,
│                   dependency_conflict_register.yaml, dependency_review_register.yaml
└── index/          conditions_index.yaml, rules_index.yaml,
                    requirements_index.yaml, dependencies_index.yaml
```

**ID formats** must stay `COND-####`, `RULE-####`, `RULE-####-V#`, `REQ-####`,
`DEP-####`. IDs are globally unique per record type; duplicates are a hard
validation failure.

---

## 2. Condition (`conditions/COND-####.yaml`)

A Condition is the only place a threshold or comparison value may live.

```yaml
condition_id: COND-0015              # required, unique
predicate_type: THRESHOLD_COMPARISON # required, see table below
target_variable_key: project.<fact>  # required for leaves; null for COMPOSITE
operator: ">="                       # required
comparison_value: 25000              # required for leaves; null for COMPOSITE
unit: "KLD"                          # required when the value has a unit, else null
child_condition_ids: []              # COMPOSITE only; must resolve to real COND-####
unresolved_behavior: UNKNOWN         # see §2.3
evidence_ids: [EVID-...]
grounding_regulatory_fact_ids: [RF-...]
description: >
  Verbatim or near-verbatim restatement of the evidenced statutory trigger.
normalization_notes: >
  Why target_variable_key means exactly what the source says.
```

### 2.1 Supported predicates and operators

Enforced by `conditions.py`. **Anything outside this table fails safe to
UNKNOWN — it does not raise, so an unsupported operator silently disables the
rule. Do not invent new ones without an engineering change.**

| `predicate_type` | Allowed `operator` | Operand type required |
|---|---|---|
| `BOOLEAN_EQUALS` | `==` | boolean |
| `SET_MEMBERSHIP` | `==`, `NOT_IN` | string (`NOT_IN` needs a list `comparison_value`) |
| `THRESHOLD_COMPARISON` | `>`, `>=`, `<=` | number (int/float; **bool is rejected**) |
| `COMPOSITE` | `AND`, `OR` | n/a — uses `child_condition_ids` |

> There is **no `<` operator** and no `IN`. Express a lower bound with `>=`
> and an upper bound with `<=`, as the existing dairy-capacity band does.

### 2.2 Units

`unit` is **documentation, not conversion**. The engine does **no** unit
conversion: it compares the raw numeric fact to the raw `comparison_value`. If
your source states a threshold in KLD and the project fact is captured in
m³/day, that mismatch will produce a wrong answer silently. Either:

* state the threshold in the same unit the Project Fact is captured in, **or**
* raise it with engineering so a conversion step is added explicitly.

### 2.3 `unresolved_behavior`

Must be `UNKNOWN`. Missing data must never collapse to FALSE — that is the
engine's core safety property ("missing data ≠ not applicable"). Composite
nodes use three-valued Kleene logic (`T∨U=T`, `F∨U=U`, `U∨U=U`).

---

## 3. Rule (`rules/RULE-####.yaml`)

```yaml
rule_id: RULE-0007          # required, unique
code: SHORT_STABLE_CODE
requirement_id: REQ-0005    # must resolve to a real Requirement
title: "..."
output_type: APPLICABILITY
rule_type: APPLICABILITY_RULE
description: >
  What statutory question this rule answers.
current_active_rule_version_id: null   # set only when a version is promoted
```

---

## 4. Rule Version (`rule-versions/RULE-####-V#.yaml`) — the lifecycle gate

```yaml
rule_version_id: RULE-0007-V1     # required, unique
rule_id: RULE-0007                # must resolve
version_number: 1

condition_expression_root_id: COND-0015   # must resolve to a real Condition

output_mapping:                   # required — the engine reads ONLY this
  TRUE: APPLICABLE
  FALSE: NOT_APPLICABLE
  UNKNOWN: REQUIRES_INFORMATION

true_outcome:    "APPLICABLE — <verbatim outcome text>"
false_outcome:   "NOT_APPLICABLE — <verbatim outcome text>"
unknown_outcome: "REQUIRES_INFORMATION — <verbatim outcome text>"

required_project_facts:           # drives the fact-capture UI and change impact
  - project.<fact_key>

regulatory_fact_ids: [RF-...]
evidence_ids:        [EVID-...]
source_ids:          [SRC-...]
authority_id:        AUTH-...
instrument_id:       INST-...

jurisdiction: INDIA
lifecycle_stage: PRE_ESTABLISHMENT

effective_start_date: null        # ISO date once in force
effective_end_date:   null

status: DRAFT                     # DRAFT | ACTIVE | SUPERSEDED | RETIRED
confidence: VERIFIED

supersedes_rule_version_id: null
prerequisite_requirement_ids: []
exception_ids: []
priority: 1

provenance: { ... }               # mirror of the id fields above
validation_notes: >
  What this version does and does NOT assert.
```

### 4.1 `output_mapping` is authoritative

The engine never guesses what TRUE means. Whatever this map says is the
outcome. All three keys (`TRUE`, `FALSE`, `UNKNOWN`) must be present.

### 4.2 `required_project_facts` — read this

This list is what the UI asks the user for and what Change Impact lets them
vary. It is consumed at runtime by `backend/app/fact_registry.py`, which is
**derived, never hardcoded**. Every fact key you list here:

* must be targeted by some Condition in the tree (otherwise its value type
  cannot be inferred and it is reported as `unknown`/not typed),
* must use the `project.` prefix,
* becomes a form field automatically — no frontend change needed.

### 4.3 Promotion to ACTIVE — the only way to unblock PRODUCTION

`status: ACTIVE` is what moves a requirement off
`BLOCKED_DRAFT_NOT_PRODUCTION`. Per the dataset's own convention, a version
must not be promoted without a human verification (`VER`) record.

**Please supply, per promoted Rule Version:**

| Field | Why |
|---|---|
| `status: ACTIVE` | the gate itself |
| `effective_start_date` | ISO `YYYY-MM-DD`, from the instrument |
| verifier identity + date | the `VER` record |
| exact instrument, section/clause | provenance |
| confirmation that `output_mapping` matches the source | correctness |

**Do not promote a version whose Conditions have not been verified.** A single
ACTIVE version with a wrong threshold is worse than the current honest block.

---

## 5. Requirement (`requirements/REQ-####.yaml`)

```yaml
requirement_id: REQ-0005
code: STABLE_CODE
title: "..."
catalog_status: PROVISIONAL_BRIDGING | VERIFIED
authority_id: AUTH-...        # the PRACTICAL issuing/enforcing body
category: CORE_APPROVAL
lifecycle_stage_ids: [PRE_ESTABLISHMENT]
default_applicability: REQUIRES_REVIEW
evaluated_by_rule_id: RULE-0007      # must resolve
classification_rule_ids: []          # optional sub-tier rules, must resolve
document_ids: []
dependencies_as_target: []
dependencies_as_source: []
grounding_regulatory_fact_ids: [RF-...]
evidence_ids: [EVID-...]
requirement_notes: >
  Scope and limits of this Requirement identity.
```

> Note the existing convention: `Requirement.authority_id` is the **practical
> regulator** (e.g. `AUTH-MPCB`), while `RuleVersion.authority_id` is the
> **instrument's issuing authority** (e.g. `AUTH-MoEFCC`). Keep both.
>
> `classification_rule_ids` is explicitly flagged in `REQ-0004` as *not* an
> adopted Phase 2 schema field. If you need tiering, flag it — don't assume.

---

## 6. Dependencies — currently zero, and that is load-bearing

`dependencies_index.yaml` has **no** executed edges; five candidates sit
unexecuted in `registers/dependency_review_register.yaml`. The UI therefore
shows an honest "no verified dependencies" state and makes **no** claim about
sequencing, parallelism or critical path.

To supply a verified edge:

```yaml
dependencies:
  - dependency_id: DEP-0001
    from_requirement_id: REQ-0001   # must resolve
    to_requirement_id:   REQ-0002   # must resolve
    dependency_type: PREREQUISITE
    verification_status: VERIFIED
    evidence_ids: [EVID-...]
    source_ids:   [SRC-...]
    note: >
      The statutory basis for this ordering.
```

**Required for every edge:** the legal basis that B cannot lawfully be granted
or applied for before A. *"In practice people file A first"* is **not** a
dependency — that is operational sequencing and must not be encoded here.

**Absence of an edge does not mean the two approvals are legally parallel.**
Any parallel-workflow claim needs its own explicit verified metadata.

---

## 7. Provenance — what is currently unresolvable

`provenance.py` preserves `regulatory_fact_ids`, `evidence_ids`, `source_ids`,
`authority_id`, `instrument_id` as **IDs only**. The upstream `facts/`,
`evidence/`, `sources/`, `authorities/`, `instruments/` record directories are
**not in this repository**, so every Decision currently carries an
`unresolved_note` and the UI shows **SOURCE DETAILS UNRESOLVED** rather than
inventing a readable citation from an ID.

To make citations resolvable, supply records with at least:

| Record | Minimum fields |
|---|---|
| `SRC-####` | title, publisher/authority, official URL, publication date, retrieved date |
| `EVID-####` | `source_id`, exact quoted text, section/clause, page number |
| `RF-####` | `evidence_id`, normalized statement, `authority_id`, `instrument_id` |
| `AUTH-####` | name, level (CENTRAL/STATE_REGULATOR/...), jurisdiction |
| `INST-####` | short title, full citation, year, in-force status |

Until these exist, **do not** write a human-readable citation into a
`description` or `*_outcome` field to make the UI look better — that
manufactures a citation the system cannot verify.

---

## 8. Project Fact keys

* Prefix `project.` and use `snake_case`.
* Name the **question the statute asks**, not the operational attribute.
  The live counter-example: `characteristics.airEmissions` ("this plant emits
  to air") is **not** the same question as
  `project.plant_located_in_air_pollution_control_area` ("this plant sits in a
  formally declared control area"). That mapping was removed in this pass
  precisely because it manufactured a jurisdictional fact from an operational
  one.
* Value types are inferred from the predicate: boolean / number / string.
* `null`, absent, or the string `"UNKNOWN"` all mean *missing* → UNKNOWN.

Current keys (all of them):

| Key | Type | Unit | Used by |
|---|---|---|---|
| `project.likely_to_discharge_sewage_or_trade_effluent` | boolean | — | REQ-0001 |
| `project.plant_located_in_air_pollution_control_area` | boolean | — | REQ-0002 |
| `project.drug_schedule_classification` | string | — | REQ-0003 |
| `project.industry` | string | — | REQ-0004 |
| `project.dairy_liquid_milk_capacity` | number | L/day | REQ-0004 |
| `project.dairy_milk_solids_capacity` | number | MT/annum | REQ-0004 |

Live machine-readable version: `GET /api/v1/facts/registry`.

---

## 9. Validation — run this before handing the pack over

`backend/iris_engine/validate.py` checks, against the actual files:

1. every `*.yaml` parses,
2. no duplicate IDs per record type,
3. `child_condition_ids` / `condition_expression_root_id` resolve,
4. `rule_id` on each Rule Version resolves,
5. `evaluated_by_rule_id` / `classification_rule_ids` resolve,
6. `rules.requirement_id` resolves,
7. conflict-register `involved_*` resolve,
8. dependency edges resolve to real `REQ-####`,
9. `status` ∈ {DRAFT, ACTIVE, SUPERSEDED, RETIRED},
10. index `counts` match on-disk counts — **update the index files**.

```bash
cd backend
.venv/Scripts/python -c "from iris_engine import RegulatoryDataset; from iris_engine.validate import validate_dataset; ds=RegulatoryDataset.load('regulatory-data'); r=validate_dataset('regulatory-data', ds); print('PASSED' if r.passed else 'FAILED'); [print(x) for x in r.yaml_parse_errors + r.duplicate_ids + r.broken_references + r.status_violations + r.index_count_mismatches]"
```

Then run the frozen engine baseline, which must still pass:

```bash
cd backend && .venv/Scripts/python -m pytest tests_engine_baseline/ -q
```

### Dataset integrity hashing

`dataset_integrity.hash_tree` hashes `regulatory-data/`. Any content change
changes the hash — that is intended and makes a pack a versioned, auditable
act. Record the new hash when you deliver.

---

## 10. Checklist

- [ ] Conditions use only supported `predicate_type`/`operator` pairs
- [ ] Every threshold is in the same unit as its Project Fact
- [ ] `unresolved_behavior: UNKNOWN` everywhere
- [ ] Every Rule Version has all three `output_mapping` keys
- [ ] `required_project_facts` lists every fact the tree reads
- [ ] Every ACTIVE promotion has a `VER` record + `effective_start_date`
- [ ] Every dependency edge has a stated statutory basis
- [ ] Index `counts` updated
- [ ] `validate_dataset` reports PASSED
- [ ] `tests_engine_baseline/` still passes
- [ ] New dataset hash recorded
