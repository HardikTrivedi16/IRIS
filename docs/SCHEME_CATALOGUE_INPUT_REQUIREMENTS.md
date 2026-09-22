# Scheme Catalogue — Input Requirements (engineering contract)

**Audience:** the teammate researching official incentive/subsidy scheme data.
**Status:** engineering interface specification. **No scheme content, no
eligibility criteria and no benefit figures appear in this document** — every
example below is explicitly marked synthetic.

---

## 0. Current state — read this first

**The scheme *framework* exists; the scheme *content* does not.**

Already implemented (software only):

| Piece | Where |
|---|---|
| Catalogue loader, structural validator, deterministic matcher | `backend/app/schemes.py` |
| API | `GET /api/v1/schemes/catalogue`, `GET /api/v1/projects/{id}/schemes?mode=PRODUCTION\|NON_PRODUCTION` (`backend/app/routers/schemes.py`) |
| UI | `/schemes` (`frontend/src/routes/schemes.tsx`) |
| Catalogue location | `backend/scheme-data/` — overridable with the `SCHEME_DATA_ROOT` environment variable (relative paths resolve against `backend/`) |
| Tests | `backend/tests/test_schemes.py`, using only the synthetic `SCH-9###` fixtures in `backend/tests/fixtures/scheme-data/` |

There is deliberately **no scheme database table**: the catalogue is
version-controlled YAML, like `regulatory-data/`, and is read-only at runtime.

**The production catalogue (`backend/scheme-data/`) ships intentionally EMPTY**
(only a README and `.gitkeep` files; a test asserts this). No real scheme, and
no unverified scheme of any kind, is shipped. Until ACTIVE + VERIFIED records
are delivered in the format below, the API reports `AWAITING_VERIFIED_DATA`
with no results and the UI shows:

> **SCHEME CATALOGUE AWAITING VERIFIED DATA**

Other behaviour to know before you deliver data:

* Only `status: ACTIVE` **and** `confidence: VERIFIED` records produce a normal
  result. DRAFT / UNVERIFIED records appear only in the labelled diagnostic
  mode (`mode=NON_PRODUCTION`).
* A catalogue that fails validation (`INVALID`) produces **no** eligibility
  results at all; the validation errors are reported instead.
* Conditions are evaluated with the Rule Engine's own generic condition
  evaluator (called read-only), so the same three-valued semantics apply:
  a missing fact is `NEEDS_INFORMATION`, never `NOT_ELIGIBLE`.
* A scheme record may also carry `application_status`/`application_window`
  (§3.2) — a claim about whether applications are currently open, entirely
  independent of the eligibility result. No production scheme uses these
  fields yet; the framework supports them, no content asserts them.

This document specifies the **format to deliver content in**.

Do **not** populate placeholder or plausible-looking schemes to fill the empty
screen. A fabricated eligibility result is materially worse than an empty one:
a user could rely on it for a funding decision.

---

## 1. Architecture this must fit

```
Project Facts
      ↓
Structured Scheme Rules   ← what you supply
      ↓
Deterministic Matcher     ← engineering, mirrors iris_engine's predicate model
      ↓
POTENTIALLY_ELIGIBLE | NEEDS_INFORMATION | NOT_ELIGIBLE
      ↓
WHY (which conditions matched / which facts are missing)
      ↓
Official Source
```

Two non-negotiable properties, carried over from the Rule Engine:

1. **The LLM never determines eligibility.** Matching is deterministic. AI may
   only explain a result the matcher already produced.
2. **Missing data ≠ not eligible.** An unresolved condition yields
   `NEEDS_INFORMATION`, never `NOT_ELIGIBLE`. `NEEDS_INFORMATION` must name
   exactly which facts are missing.

The strongest outcome is deliberately `POTENTIALLY_ELIGIBLE`, never
"ELIGIBLE" — IRIS is an assurance layer; the administering authority decides.

3. **Eligibility and application status are two independent claims** (§3.2).
   The diagram above is the eligibility path only; `application_status`/
   `application_window` run alongside it, never through it — see §3.2.

---

## 2. File layout (as implemented)

Mirrors `regulatory-data/`, and is **separate from it** — schemes are
incentives, not statutory applicability, and must never be loaded by
`iris_engine`. The root directory is `backend/scheme-data/` by default, or the
path in the `SCHEME_DATA_ROOT` environment variable (a relative path resolves
against `backend/`).

```
backend/scheme-data/          (or $SCHEME_DATA_ROOT)
├── schemes/            SCH-####.yaml
└── scheme-conditions/  SCHC-####.yaml
```

The loader reads exactly these two directories, one YAML document per file,
keyed by `scheme_id` / `scheme_condition_id`. No index file is read or
required.

---

## 3. Scheme record (`schemes/SCH-####.yaml`)

```yaml
scheme_id: SCH-0001                  # required, unique, SCH-####
name: "<official scheme name>"       # exactly as published
administering_authority_id: AUTH-... # reuse an existing AUTH-#### where possible
administering_authority_name: "<as published>"

official_source:                     # REQUIRED — no scheme without one
  url: "https://<official government domain>"
  document_title: "<notification / GR / guideline title>"
  reference_number: "<GR/notification number, if any>"
  published_date: "YYYY-MM-DD"
  retrieved_date: "YYYY-MM-DD"
  retrieved_by: "<name>"

effective_start_date: "YYYY-MM-DD"
effective_end_date: null             # null = open-ended AS PUBLISHED, not "assumed ongoing"

jurisdiction: "<STATE or INDIA>"
sector_scope: []                     # [] = not sector-restricted PER THE SOURCE

eligibility_condition_root_id: SCHC-0001   # must resolve

required_project_facts:
  - project.<fact_key>

benefits_summary: >
  Verbatim or close paraphrase of the published benefit. Do NOT compute,
  extrapolate or "typical case" a number.

required_documents: []               # only if the source lists them

status: DRAFT                        # DRAFT | ACTIVE | SUPERSEDED | RETIRED
confidence: UNVERIFIED               # UNVERIFIED | VERIFIED

last_verified:
  date: "YYYY-MM-DD"
  verified_by: "<name>"
  method: "<e.g. read GR PDF from the department portal>"

notes: >
  Scope limits, ambiguities, anything you had to interpret.
```

### 3.1 Lifecycle

Same fail-closed gate as Rule Versions: **only `status: ACTIVE` +
`confidence: VERIFIED` may produce a user-facing eligibility result.** DRAFT
schemes are visible only in a clearly labelled non-production/diagnostic view.

### 3.2 Application status — a SEPARATE claim from eligibility

**Eligibility and application availability are two independent claims and
must never be collapsed into one.** `outcome` (`POTENTIALLY_ELIGIBLE` /
`NEEDS_INFORMATION` / `NOT_ELIGIBLE` / `CANNOT_EVALUATE`) answers "does this
project's Project Facts satisfy the published eligibility conditions?".
`application_status` answers a completely different question: "is this
scheme currently accepting applications at all?". A project can be
`POTENTIALLY_ELIGIBLE` for a scheme whose applications are
`VERIFIED_CLOSED`; a scheme can be `VERIFIED_OPEN` for a project that is
`NOT_ELIGIBLE`. Neither is inferred from the other, and neither is inferred
from wall-clock time.

```yaml
application_status: VERIFIED_OPEN    # optional — omit if genuinely unverified

application_window:                  # required whenever application_status is set
  mode: FIXED_WINDOW                 # see allowed values below
  opens: "2027-01-01"                # ISO date, or null if not applicable/unresolved
  closes: "2027-04-30"               # ISO date, or null if not applicable/unresolved
  as_of_date: "2026-09-21"           # REQUIRED whenever application_status is set —
                                      # the date this status was last verified true.
                                      # NOT a computed/derived date.
  source_reference:                  # same shape as a scheme condition's source_reference
    document_title: "..."
    clause: "..."
    page_number: 0
    quoted_text: "..."

supersedes: null                     # optional — a scheme_id this record supersedes
superseded_by: null                  # optional — a scheme_id that supersedes this record
```

**Allowed `application_status` values** (reuse this vocabulary — do not
invent a new one, and do not infer it from `status`/`confidence`, which
describe IRIS's own catalogue lifecycle, not the scheme's application
window):

| Value | Meaning |
|---|---|
| `VERIFIED_OPEN` | Verified currently accepting new applications |
| `VERIFIED_CLOSED` | Verified currently not accepting new applications |
| `VERIFIED_CONTINUING_BUT_NOT_OPEN_FOR_NEW_APPLICATIONS` | Existing beneficiaries continue; no new intake |
| `VERIFIED_PERIODIC_CALL_FOR_PROPOSALS` | Opens in periodic calls, not continuously |
| `SELECTION_COMPLETED` | A selection round has concluded |
| `NO_CURRENT_WINDOW` | No application window is currently open or announced |
| `UNRESOLVED_CURRENT_STATUS` | Researched but the current status could not be resolved |
| `DISCONTINUED` | The scheme itself has been discontinued |
| `SUPERSEDED` | Superseded by a newer scheme (see `superseded_by`) |

**Allowed `application_window.mode` values:** `CONTINUOUS`, `PERIODIC_EOI`,
`FIXED_WINDOW`, `PROPOSAL_BASED`, `SELECTION_COMPLETED`, `CLOSED`,
`UNKNOWN`.

**`as_of_date` is required whenever `application_status` is set.** Every
value in the table above is a verified position *as of a specific date*,
never a live/computed one — the catalogue records what was true when
verified, not an inference from today's date. There is deliberately **no
wall-clock check** anywhere in this framework (no `if today > closes then
CLOSED`) — `match_scheme`'s `as_of` parameter is used only for the existing
`effective_start_date`/`effective_end_date` in-force check (§3), never for
`application_status`.

`VERIFIED_OPEN` combined with `mode: FIXED_WINDOW` requires a `closes` date
— a fixed window is by definition a known window. If the source doesn't
state a closing date, the scheme genuinely isn't a fixed window yet; use
`mode: UNKNOWN` (or another mode that fits) instead of `FIXED_WINDOW`.
Conversely, when `application_status: VERIFIED_CLOSED` and the source does
state the closing date the window actually closed on, preserve it in
`closes` — do not blank it out.

### 3.3 Supersession pointers

`supersedes` / `superseded_by` are optional `scheme_id` references,
validated to resolve to a real record when present. This is **only a
pointer**, not historical-version machinery — no automatic status change, no
inherited fields, no chain-walking. If a scheme record itself needs
retiring, use `status: SUPERSEDED`/`RETIRED` as already supported (§3.1);
`supersedes`/`superseded_by` exist so the catalogue can additionally say
*which* record replaced *which*.

---

## 4. Scheme condition (`scheme-conditions/SCHC-####.yaml`)

Intentionally the **same predicate model** as `regulatory-data/conditions/`,
so the matcher can reuse the evaluator's semantics rather than inventing a
second condition language.

```yaml
scheme_condition_id: SCHC-0001
predicate_type: THRESHOLD_COMPARISON   # BOOLEAN_EQUALS | SET_MEMBERSHIP | THRESHOLD_COMPARISON | COMPOSITE
target_variable_key: project.<fact>    # null for COMPOSITE
operator: ">="                         # == | NOT_IN | > | >= | <= | AND | OR
comparison_value: 0                    # null for COMPOSITE
unit: "<unit as published>"            # null if unitless
child_scheme_condition_ids: []         # COMPOSITE only
unresolved_behavior: UNKNOWN           # must be UNKNOWN

source_reference:
  document_title: "<...>"
  clause: "<para/section number>"
  page_number: 0
  quoted_text: >
    The exact published sentence this condition encodes.

description: >
  Plain restatement of the eligibility test.
normalization_notes: >
  Why target_variable_key means exactly what the source says.
```

**Constraints (identical to the regulatory pack — see
`REGULATORY_PACK_INPUT_REQUIREMENTS.md` §2):**

| `predicate_type` | Allowed `operator` | Operand |
|---|---|---|
| `BOOLEAN_EQUALS` | `==` | boolean |
| `SET_MEMBERSHIP` | `==`, `NOT_IN` | string (`NOT_IN` needs a list) |
| `THRESHOLD_COMPARISON` | `>`, `>=`, `<=` | number |
| `COMPOSITE` | `AND`, `OR` | children |

There is **no `<`** and **no `IN`**. No unit conversion is performed — state
thresholds in the unit the Project Fact is captured in.

---

## 5. Project Facts schemes may test

**Project Fact Registry is shared infrastructure.** `GET
/api/v1/facts/registry` (`backend/app/fact_registry.py`) is the ONE
`project.*` vocabulary regulatory rules and scheme rules both consume —
there is no separate "scheme fact" registry, storage, or validation path.
A key a scheme references via `required_project_facts` or a Scheme
Condition's `target_variable_key` is merged into that same registry by
key: if a regulation already references it, the registry reports ONE entry
with `consumer_domains: ["REGULATORY", "SCHEME"]`, not two.

Prefer reusing existing keys (`GET /api/v1/facts/registry`). If a scheme needs
a fact IRIS does not capture — investment quantum, employment numbers,
enterprise classification, category of promoter — **list it and stop**; do not
repurpose a similarly-named existing fact. New keys must:

* use the `project.` prefix and `snake_case`,
* name the question the scheme asks,
* declare a value type and, for numbers, a unit,
* be listed in the scheme's `required_project_facts`.

A fact key must have **one meaning, one value type and one unit** across
every consumer, regulatory or scheme. If the same key is genuinely used
with an incompatible type or a different non-empty unit by a regulation
and a scheme, the registry reports `value_type: "mixed"` and/or
`units_conflict: true` for that key and refuses typed input rather than
guessing or silently converting — that is a sign the scheme needs its own,
differently-named fact, not a reason to force reuse.

Deliver new fact keys as a table:

| Proposed key | Type | Unit | Question as published | Source clause |
|---|---|---|---|---|

---

## 6. Worked example — **SYNTHETIC, NOT A REAL SCHEME**

> ⚠️ `SCH-9001` is a **fabricated illustration of the file format only**. It
> is not a real scheme, its values are meaningless, and it must never be
> loaded outside tests. Note `status: DRAFT`, `confidence: UNVERIFIED` and the
> `example.invalid` URL.

```yaml
# scheme-data/schemes/SCH-9001.yaml   — SYNTHETIC TEST FIXTURE
scheme_id: SCH-9001
name: "SYNTHETIC TEST SCHEME — NOT A REAL SCHEME"
administering_authority_name: "SYNTHETIC AUTHORITY"
official_source:
  url: "https://example.invalid/synthetic"
  document_title: "SYNTHETIC FIXTURE — NO REAL SOURCE"
  published_date: "2026-01-01"
  retrieved_date: "2026-01-01"
  retrieved_by: "engineering fixture"
effective_start_date: "2026-01-01"
effective_end_date: null
jurisdiction: "SYNTHETIC"
eligibility_condition_root_id: SCHC-9001
required_project_facts:
  - project.industry
benefits_summary: "SYNTHETIC — no real benefit is described here."
status: DRAFT
confidence: UNVERIFIED
notes: "Format demonstration and automated-test fixture only."
```

Tests must use `SCH-9###` fixtures exclusively, never a real scheme ID.

---

## 7. Data-classification labelling (required in the UI)

Every scheme row must carry one of:

| Label | Meaning |
|---|---|
| **Verified regulatory information** | `status: ACTIVE`, `confidence: VERIFIED`, resolvable official source |
| **Curated prototype information** | researched but not yet verified (DRAFT) |
| **Synthetic / demo data** | fixtures such as `SCH-9###` |

A scheme with no resolvable `official_source` may **not** be shown as
verified, regardless of how confident the research is.

---

## 8. Checklist

- [ ] Every scheme has a complete, resolvable `official_source`
- [ ] `effective_start_date` / `effective_end_date` copied as published
- [ ] Every condition cites document, clause, page and quoted text
- [ ] Only supported `predicate_type`/`operator` pairs used
- [ ] Thresholds stated in the same unit as the Project Fact
- [ ] `unresolved_behavior: UNKNOWN` everywhere
- [ ] New fact keys listed separately, not mapped onto existing ones
- [ ] `benefits_summary` quotes, never computes
- [ ] `last_verified` filled for anything marked VERIFIED
- [ ] Nothing ACTIVE that is not VERIFIED
- [ ] `application_status`, if set, is from the allowed vocabulary (§3.2) and never inferred from `status`/`confidence`
- [ ] `application_window.as_of_date` is set whenever `application_status` is set
- [ ] `VERIFIED_OPEN` + `FIXED_WINDOW` has a real `closes` date (or use a different `mode`)
- [ ] `supersedes`/`superseded_by`, if set, resolve to a real `scheme_id`
- [ ] Benefits remain descriptive — `benefits_summary` is never computed into a figure
- [ ] Production `scheme-data/` remains empty until this content is formally delivered and reviewed
- [ ] Test fixtures use `SCH-9###` and are marked synthetic
