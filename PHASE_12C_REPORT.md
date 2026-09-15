# Phase 12C — Safe staging projection and approval-bound dry-run planning

Status: implemented locally for human review. Fictional inputs only. No execution path,
commit, push, deployment or Phase 12D work.

## 1. Baseline and architecture

The repository started clean on `main` at
`16c594565b5f8d2d3b7337ecd347733cfabd1268`. Phase 12B was present. Auto Deploy OFF is
the recorded owner-confirmed state; no Railway query or configuration change was made.
No production database connection, environment-file read or catalogue acquisition occurred.

The new `importer/projection` package implements:

1. Revalidation of the exact submitted records using the unchanged Phase 12B validator.
2. Explicit, loss-checked projection into sparse importer-compatible field fragments.
3. Field-level comparison against a supplied in-memory snapshot.
4. An immutable, deterministically hashed review plan.
5. Approval metadata bound to that plan and pure verification against supplied current context.

It stops there. No database engine, transaction, application settings, FastAPI route,
network client or legacy importer runner is used by the new package.

## 2. Files added

| File | Purpose |
| --- | --- |
| `importer/projection/__init__.py` | Isolated package boundary |
| `importer/projection/canonical.py` | NFC canonical JSON and SHA-256 |
| `importer/projection/models.py` | Policies, snapshots, changes, immutable plan and approval contracts |
| `importer/projection/projector.py` | Phase 12B validation, explicit mappings and structured rejection |
| `importer/projection/planner.py` | Offline snapshot validation and field-level dry-run planning |
| `importer/projection/approval.py` | Exact-plan/context verification without execution |
| `importer/projection/README.md` | API usage and safety semantics |
| `tests/fixtures/projection-fictional.json` | Invented mapping and revision-order policies |
| `tests/test_projection.py` | Fictional projection, conflict and approval regressions |
| `PHASE_12C_REPORT.md` | This review report |

No existing tracked file was modified. Production models, migrations, dependencies,
configuration, routes, the existing importer and the Phase 12B implementation are unchanged.

## 3. Existing importer review and reuse

Inspected staging models/validator/identity, importer schemas, planner, runner, provenance
handling and dry-run/report behavior before implementing this layer.

Reused only pure importer field constraints (`ImportSet`, `ImportCard`, `ImportVariant`,
`ImportKeyword`, `ImportSource`) and Phase 12B validation/registry behavior. Projection
rejects values that the existing schemas would truncate semantically through whitespace
or other normalization; it does not quietly replace them with normalized values.

The existing planner cannot safely be reused: it queries a database, materializes default
nulls, generates internal UUIDs and builds database application structures. Its existing
dry run and real run independently rebuild plans. Existing provenance has entity-level
hashes and first/last observation times, not field baselines or publisher revision ordering.
The runner defaults to application and can commit a transaction. None of these paths is
connected to Phase 12C, and their behavior was not changed.

## 4. Projection policy and supported mappings

The classification is also available as `projector.DIMENSIONS`.

| Dimension | Classification and behavior |
| --- | --- |
| Expansion / edition | SUPPORTED_WITH_MAPPING: immutable scope keys map to a policy-supplied importer set ID/name/edition label |
| Language | SUPPORTED: carried explicitly; never defaults from UNKNOWN |
| Territory | UNSUPPORTED: identity-bearing territory rejects projection |
| Numbering namespace | SUPPORTED_WITH_MAPPING: scope plus namespace must have one explicit target set |
| Printed identifier | SUPPORTED: complete string retained, subject to importer length constraints |
| Ordinary card fields | SUPPORTED: typed field operations and existing importer constraints |
| Mission points/rank | UNSUPPORTED when supplied, including explicitly unknown values |
| Rarity label | SUPPORTED: card rarity or variant rarity override |
| Rarity abbreviation/normalized key | UNSUPPORTED when supplied; not silently dropped |
| Keywords | SUPPORTED_WITH_MAPPING: keys/labels map to slug/name, with shared keyword entity planning and association operations |
| Treatment | SUPPORTED_WITH_MAPPING: verified accepted parent, approved treatment key and owner public ID |
| Finish | SUPPORTED: preserved separately from rarity |
| Serialization | REQUIRES_REVIEW if unknown; known flag/quantity map after Phase 12B checks |
| Images | REQUIRES_REVIEW: VALUE/CLEAR rejected; ABSENT/UNKNOWN remain SKIP; no image fetch |
| Availability | UNSUPPORTED when supplied |
| Provenance | SUPPORTED_WITH_MAPPING: source metadata and complete validated record evidence retained in the review plan; no provenance write |

Mappings are one-to-one: two scope/namespace combinations cannot collapse onto the same
importer set. This is a narrowly approved fictional projection strategy, not a migration or
a final decision about the public expansion model. Unsupported records are rejected, so a
safe subset can be planned without changing the production schema.

Importer-compatible output is intentionally a sparse fragment plus explicit operations and
owner references, not an executable full `ImportCatalogue` payload. Required fields for
new entities are checked during planning. Default nulls from the old full-snapshot writer
are never copied into update instructions. Fragment compatibility is tested against the
existing Pydantic importer models.

## 5. Missing, unknown, value and clear semantics

- ABSENT: SKIP; omitted from the sparse importer fragment.
- UNKNOWN: SKIP and retained in evidence; never converted to CLEAR.
- VALUE: CREATE for a new entity, UPDATE for an authorized newer observation, or UNCHANGED.
- CLEAR: retains its explicit review reference and proposes a null clear. Keyword clears
  explicitly propose an empty association list. Clearing a new entity is SKIP.
- An empty keyword VALUE cannot remove existing links without explicit CLEAR.
- Conflicting/incomplete-state clears remain blocked and retain their review references.

Approval references remain assertions, not signatures or authenticated override authority.
There is no manual-edit override execution in this phase.

## 6. Snapshot and changeset design

`Snapshot` contains a version and supplied entities keyed by kind/public ID. Sets and
keywords have no owner; cards/variants name their parent public ID. Each entity carries
current importer-named field values and optional per-field last-imported value/source
observations. Keyword slugs and stored IDs are checked. Card number inventories are
required for supplied cards so occupied-number collisions can be detected.

Snapshots are validated without database access. Duplicate snapshot identities are invalid;
duplicate occupied card numbers, owner changes and card-number rebinding block plans.
Snapshot completeness is a caller responsibility that cannot be proven without a future
authoritative reader. Missing field/current baseline information never authorizes an update.

Changes include kind/public ID, field, current/proposed values, operation, reason, proposed
source, prior field observation where available and explicit clear reference. Operations
are CREATE, UPDATE, CLEAR, UNCHANGED, CONFLICT and SKIP. Owner relationships are reviewed
as explicit changes too. Counts describe proposed entities and field operations, not SQL
row counts or the final size of a production catalogue.

## 7. Manual edits and source ordering

If current value B differs from last-imported value A, emit `CONFLICT_MANUAL_CHANGE`, even
when the incoming value agrees with B. Do not silently adopt a manual edit as an import.
Shared keyword names receive the same protection, separately from card associations.

An older retrieval or an explicitly older approved revision conflicts. Different source
names, missing revision ordering or changed values under an equal revision require review.
Only a policy-supplied revision order establishes publisher precedence; retrieval time
alone never proves a newer publisher revision. An older identical observation remains
UNCHANGED with a stale-observation warning, without a provenance refresh.

Source ordering, registry assignments, rights assertions and policy mappings are supplied
review inputs. Their authenticity is not established by this package.

## 8. Immutable content and hash

Plan content includes schema version, source metadata/content hashes where available,
validated evidence, raw staging input hash, staging-policy hash, registry hash, projection
policy version/hash, supplied snapshot hash, complete planning policy, ordered changes,
conflicts, warnings, rejected projections and expected counts.

Canonical JSON uses sorted object keys, compact UTF-8 encoding and Unicode NFC. Non-finite
numbers and normalized-key collisions are rejected. Snapshot entity ordering is normalized;
input record ordering is retained in its bound input hash. Identical inputs produce the
same content/hash. SHA-256 is used, never Python `hash()`.

`Plan` is a frozen envelope containing the canonical content string, its verified hash and
an incidental creation timestamp. The timestamp is outside deterministic content. Parsing
`plan.content` returns a fresh copy, so nested mutations cannot change the frozen plan.
Integrity is checked again during approval verification, including bypassed model copies.

The version-1 fictional golden plan hash is:
`21a2a70381d058f697cfdbcb71d2bff097be91fe28127350b3fc43aa449c02cc`.

## 9. Approval binding and eligibility

Approval carries plan hash, approver reference, aware approval timestamp and optional review
reference. Verification recomputes/checks plan integrity and compares the supplied current
snapshot, staging records, staging policy, projection policy, planning policy and registry.
Any bound difference invalidates the previous approval. Tests cover field/record/source/
policy/state/clear-reference changes and corrupted hashes.

Conflicts and projection rejections always make a plan ineligible. Warnings block by default;
only explicitly named nonblocking warning codes are allowed. Fictional tests explicitly
allow their unsuitable-source/unknown-rights warnings solely to exercise binding. This is
not redistribution approval.

Verification always reports `identity_authenticated=false` and `execution_enabled=false`.
No apply, execute, commit, transaction, database-read or plan-file-write function exists.

## 10. TOCTOU design

Before any separately approved future execution, an authoritative reader must re-read the
complete relevant state, hash it and compare against the approved plan's snapshot hash.
A mismatch must refuse execution and require a new plan/review. Transaction isolation or
locking must prevent state changing between comparison and future write. The approved
plan's exact operations must be used, not independently rebuilt application instructions.

This phase implements only pure verification using supplied fictional snapshots. It does
not implement the authoritative reader, locking, transaction, execution or retry behavior.

## 11. Fixtures and tests

The new fixture contains only invented scope mappings, set labels and revision-order policy,
using the existing fictional Phase 12B records. Tests create fictional current snapshots
and mutate them for creates, updates, unchanged values, explicit clears, unknown/absent
fields, manual changes, stale sources, unsupported dimensions, parent failures, keyword
conflicts, number collisions and approval/state/policy changes. No official source or art
was acquired; `example.invalid` references are not fetched.

63 new parametrized test cases cover the requested projection/approval categories plus
shared keyword protection, deep plan immutability, source normalization rejection, preserved
clear references on conflicts, conservative source precedence and import-boundary guards.

## 12. Validation results

- Full pytest: **574 passed**, including all existing Phase 12B and importer regressions.
- Three dependency deprecation warnings: Starlette/httpx integration, anyio portal alias,
  OpenAPI validator shortcut. No test failures.
- Ruff check: **passed**.
- Ruff formatting: **107 files already formatted**.
- Mypy `app importer scripts`: **passed, 65 source files**.
- Existing OpenAPI/export regression tests: **passed**.
- RapidAPI artifact remains OpenAPI **3.0.2**, **12 paths**, **12 GET operations**.
- Artifact SHA-256 unchanged:
  `9c76bca79d0056051dc2538e6b6b45382bb5275699d25e941fc82dbc5311d386`.

Tests ran with dummy settings and in-memory dotenv suppression, also applied to Python
test subprocesses. No `.env` or production credentials were read. The normal legacy
importer regressions exercise their existing writer against isolated test databases;
Phase 12C itself never imports or invokes that write path. There were no production
database reads/writes. Routine ignored test/tool caches may update locally.

## 13. Deferred decisions, limitations and next phase

- No production migration is needed for the accepted subset. Territory, Mission fields,
  availability, image projection and richer rarity mapping remain rejected/deferred.
- Full importer-payload materialization is deliberately deferred; sparse fragments are not
  safe inputs to the unchanged legacy writer.
- Snapshot completeness, authenticated source/approver identities, persistent registries,
  approval signatures, durable review storage and operational locking remain unimplemented.
- Multi-source shared-entity disagreements reject rather than choosing a winner. Conservative
  comparisons can require additional review. No unsupported information is auto-repaired.
- Plan hashes detect content differences; they are not authorization signatures or proof
  that a supplied snapshot is truthful/current. Future execution requires fresh state and
  transaction-level protection, not merely successful metadata verification.

Phase 12C: **GO for local human review**. No commit or push.

Phase 12D: **CONDITIONAL GO only after explicit approval**, recommended as a fictional-only
review of complete snapshot capture and safe full-payload materialization with manual-edit
protection, identity mapping and transaction/locking design. Do not infer permission for
real catalogue acquisition, production access or application. Phase 12D has not started.

## Safety confirmation

Real Naruto data used: NO. Network catalogue acquisition: NO. Official artwork downloaded:
NO. Production DB accessed: NO. Production DB modified: NO. Existing importer apply path
invoked by Phase 12C: NO. Railway modified: NO. RapidAPI modified: NO. Deployment performed:
NO. Migration created: NO. Commit created: NO. Push performed: NO.
