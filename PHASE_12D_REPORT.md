# Phase 12D — authoritative snapshot and execution design

Status: LOCAL IMPLEMENTATION COMPLETE — awaiting human review.

Recommendation: CONDITIONAL GO for acceptance of this fictional contract/design phase; NO-GO for production execution. Approval authentication, authoritative database reads, durable provenance/receipts and an exact-operation executor are not implemented. No subsequent phase has started.

## 1. Baseline and scope

Verified before implementation: branch `main`, clean working tree, HEAD `02ae3a0b957d901244f117ca0e48c616e0446dd8`. Phase 12B staging, Phase 12C projection and their repository reports were present. Railway Auto Deploy is intentionally OFF according to the owner-confirmed state; Railway was not queried. Phase 12A findings were available in conversation; no standalone Phase 12A report was found in the checkout.

Only these nine new files form this phase:

- `PHASE_12D_REPORT.md`
- `importer/execution_design/__init__.py`
- `importer/execution_design/snapshot.py`
- `importer/execution_design/materializer.py`
- `importer/execution_design/preconditions.py`
- `importer/execution_design/concurrency.py`
- `importer/execution_design/receipt.py`
- `tests/fixtures/execution-design-fictional.json`
- `tests/test_execution_design.py`

No existing tracked file was changed. No legacy behavior, runtime configuration, API, dependencies, generated artifact or migration was changed. Work remains uncommitted and unpushed.

## 2. Existing importer review

Reviewed staging/identity validation, projection, canonical serialization, planning and approval verification; importer schemas, planner, runner, provenance and dry-run behavior; production set/card/variant/image/keyword/source models and importer tests.

Safe reuse: pure Pydantic importer schemas for representational compatibility; Phase 12C immutable plan structures, canonical hashes and approval binding verification; the pure source-order comparison for checking operation integrity. Phase 12D does not call projection or planning to choose operations. Tests replace those entry points with failures and still prepare the approved candidate.

Unsafe reuse: the legacy importer planner imports database models and derives its own operations. The runner can apply writes and replan independently. Full-object defaults can imply nulls, full updates can overwrite fields, and blanket provenance writes do not distinguish carried-forward values from approved modifications. Internal row UUID generation is not public identity approval. No Phase 12D module imports or calls the legacy planner/runner.

Reviewed constraints include unique public IDs, card `(set_id, card_number)` uniqueness, keyword slug uniqueness and association keys; restricted set deletion and cascading card child relationships; PostgreSQL image ownership constraints. Polymorphic source provenance does not provide a complete authenticated field baseline or durable approval/receipt store. These are future architecture requirements, not migrations in this phase.

An exact approved plan can be represented safely for the supported complete subset. That does not make the legacy writer safe. Payloads explicitly declare `legacy_schema_compatible=true` and `legacy_writer_safe=false`.

## 3. Architecture and snapshot reader

The public pure gate is `prepare_candidate`: validate exact plan and approval, derive scope, read fictional state, check completeness and bindings, compare approved semantic state, detect prior success, then materialize exact operations. The result is an `ExecutionPreconditionsResult` with a frozen `ExecutionCandidate`, or structured blocking reasons. There is no apply method or database session.

`SnapshotReader.read_snapshot(scope)` is a protocol. `FictionalMemoryReader` is its only implementation. Its input is the COMPLETE fictional universe, never an arbitrary partial query result. It scans that universe and returns validated copies; `simulate_change` changes only in-memory fictional state and advances a generation counter.

## 4. Deterministic scope, completeness and proven absence

`SnapshotScope` contains sorted approved entity identities, target sets and the symbolic closure `ALL_SET_CARDS_VARIANTS_KEYWORDS_AND_BASELINES`. It includes target identity observations, registry bindings, owner relationships and baselines; every card in target sets, occupied card-number inventory, every scoped card's variants and keyword associations, and associated keyword rows. Sibling rows matter even when not modified. The same approved projection produces the same scope hash.

Each required component must have exactly one exhaustive coverage observation, with a hash matching its represented value. Status is PRESENT, PROVEN_ABSENT, MISSING or AMBIGUOUS. Duplicate proof, inconsistent status/hash, missing proof or non-exhaustive coverage blocks eligibility. An empty inventory only proves absence when explicitly marked exhaustive. Target absence and missing owner relationships have explicit negative observations; an absent baseline is explicit and cannot authorize updating an existing field. Existing rows must include every required full-schema field; unknown keyword associations are incomplete rather than silently empty.

The checker verifies coverage consistency and declarations mechanically. It cannot authenticate an external reader or prove that a dishonest reader queried every real row. A future trusted reader must provide exhaustive reads under the transaction boundary. Phase 12C plans based on narrower/incomplete snapshots will fail fresh-state comparison and require a new planning/review cycle; they are never patched automatically.

## 5. Snapshot hashing and approval revalidation

The envelope carries schema version, capture time, reader reference, read context, scope hash, canonical state and coverage. Its semantic hash is exactly Phase 12C's canonical snapshot hash, including values, ownership and field baselines. Its content hash additionally binds scope, registry and sorted coverage. Capture time and read-context metadata do not change semantic state; reader/context are compared separately by the concurrency fence.

Plan canonical serialization/hash and structure are revalidated. Approval hash must match and the plan must be eligible without rejected projection or blocking conflicts. Phase 12C verification checks exact staging input/source, registry, staging/projection/planning policy bindings and approved snapshot hash. The reader's registry is also checked. Fresh relevant state must equal approved state. A mismatch returns STATE_CHANGED/STALE_APPROVAL and requires new review, never independent replanning.

Hashes provide integrity and binding, not signatures or authenticated human approval. Caller-supplied approvals and receipts remain untrusted for production authorization.

## 6. Exact materialization and sparse semantics

The exact reviewed Change records drive materialization. Duplicate/extra/missing operations, wrong counts, invalid source/baseline/current values and unsupported fields block. Source precedence and manual-baseline checks verify the approved modifications without selecting replacement operations.

- CREATE uses only approved values and identity assignments. Required missing fields produce MISSING_REQUIRED_CREATE_FIELD. Optional fields required to complete a legacy object cannot silently receive defaults: unsupported omission produces LEGACY_SCHEMA_INCOMPATIBLE.
- UPDATE and CLEAR appear in the explicit modifications list. CLEAR requires the matching clear approval reference and field semantics; clearing keyword associations means an explicitly approved empty list.
- SKIP for ABSENT/UNKNOWN never writes. UNCHANGED must match verified current state and approved field content and never becomes a modification.
- Existing fields needed for complete representation come only from the verified snapshot and carry CARRIED_FORWARD origin. Public identity fields carry APPROVED_IDENTITY; changed fields carry APPROVED_MODIFICATION.
- CONFLICT prevents a candidate. Missing, unknown and skipped fields never turn into null/default writes.

Full entities and nested catalogue representations validate against existing importer Pydantic schemas. Validation/coercion must not change canonical meaning. Empty child containers select no additional child operations, not deletion or invented row defaults. The payload retains all exact approved operations for audit, separately from actual modifications. Canonical payload JSON and hash are validated; candidate integrity also binds plan and destination idempotency key.

Clean fictional create works for fully specified new cards/variants in a complete existing set. Creating a new set currently fails when Phase 12C has not approved the extra fields needed by the full legacy schema. This is an explicit safe compatibility limit, not a reason to change defaults or legacy behavior.

## 7. Identity and relationships

Public IDs come from approved assignments, never mutable names or regenerated IDs. Full rows must agree with the approved importer identity fields. Existing card number, keyword slug, set edition/language and variant identity-field changes are blocked. Current and approved owner operations must agree; card/set and variant/card parents must be represented. Every scoped current relationship is checked, including keyword slug/name consistency. Treatment parent identity is retained through its approved variant owner.

Occupied numbers and ownership changes affect the complete approved state comparison; Phase 12C conflicts remain blocking. Registry changes also block. No relationship is silently repaired. Images are outside the current accepted projection subset, so this phase neither materializes image modifications nor claims image execution support. Future image support must extend scope, ownership validation and review contracts first.

## 8. Preconditions and authentication boundary

Technical checks cover plan integrity, approval exact match/eligibility, complete fresh snapshot, approved state equality, context/source/policy bindings, registry, successful materialization, identity/relationships and prior execution. Unsupported operations and stale state return no candidate.

Even when every technical check passes:

`approval_identity_authenticated = false`

`authentication_status = NOT_IMPLEMENTED`

`production_execution_authorized = false`

The candidate also fixes production authorization to false. Future trusted approval requires authenticated reviewer identity, authorization for destination/action, tamper-resistant plan-bound approval records, revocation/expiry policy and audited executor identity. None is invented here.

## 9. Future transaction and locking design — NOT implemented

Recommended initial strategy for the small catalogue: READ COMMITTED with SHARE ROW EXCLUSIVE table locks over all affected catalogue/association/provenance tables and future registry/receipt storage, acquired in one deterministic order before authoritative state reads. This deliberately trades concurrency for safety: ordinary concurrent inserts, updates and deletes are blocked, including manual writers that ignore advisory locking. It protects missing rows and card-number phantoms that row locks cannot cover. Lock strength and conflicts are described in the [PostgreSQL locking documentation](https://www.postgresql.org/docs/current/explicit-locking.html).

READ COMMITTED gives a fresh view after lock waits when reads begin under those locks. Repeatable Read alone does not prevent every cross-row invariant race. SERIALIZABLE is an alternative requiring serialization-failure handling and a carefully coordinated writer protocol; it does not remove approval freshness checks. See [PostgreSQL transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html).

Future exact sequence:

1. Authenticate executor and reviewer authorization; bind destination and exact approved plan. An early idempotency lookup is advisory only.
2. Begin one transaction. Acquire an optional transaction advisory importer gate, then all required table locks in stable order, before relevant reads. Coordinate the legacy importer advisory key only if a separately approved integration makes it part of the same protocol.
3. Under those locks, read the full scope, registry, baselines and durable receipt/idempotency state. Existing row FOR UPDATE locks can supplement this, but cannot protect absent rows.
4. Reject previous success; verify approval bindings and semantic hash, identity, completeness and relationships again. Materialize the exact approved operations inside this boundary.
5. Apply only the approved modifications through a future dedicated applier. Never submit carried-forward full catalogues to the legacy runner.
6. Validate uniqueness/FK and business invariants, calculate post-state, write only corresponding provenance, and persist one successful receipt/idempotency record in the same transaction.
7. Commit all together. Any mismatch/error rolls back the entire operation. No partial success is allowed. A failed audit receipt may be written separately after rollback and cannot claim success.

Use bounded lock waits, stable global/table/entity ordering and short transactions to reduce deadlocks. A deadlock, serialization failure or timeout aborts the whole transaction. Retry only by rechecking the same approved plan under locks; changed state needs renewed review. Concurrent importer attempts serialize; unique constraints remain final defense. Future receipt storage needs a unique destination/plan idempotency key.

This design assumes all relevant tables are identified and ordinary writes obey PostgreSQL locks. Privileged operational changes require their own controlled maintenance boundary. The symbolic `lock_order` helper is deterministic; it executes no SQL and takes no real locks.

## 10. TOCTOU, receipts and idempotency

`verify_fence` revalidates candidate integrity and fresh completeness, then compares scope, semantic/content hashes, reader and read context. In-memory tests demonstrate changed state rejection and generation changes even if state is restored (ABA). An unchanged outside-transaction fence is never permission to write. The future executor must prepare/reverify inside its held-lock transaction; production TOCTOU closure is designed here, not implemented.

`ExecutionReceipt` models plan/approval references, destination key, pre/post state hashes, counts, aware timestamp, executor authentication and transaction references, outcome, rollback and provenance reference. Success requires post-state/provenance and cannot claim rollback. Failure requires rollback and cannot claim changed committed post-state. No receipt is persisted or issued by candidate preparation; only fictional tests instantiate them.

Idempotency is a deterministic canonical hash of plan identity and destination. Supplied successful matching receipts yield ALREADY_EXECUTED; a different destination is a different context. Failed rolled-back attempts do not count as success, but retry still requires all checks. A future authenticated durable receipt store and atomic uniqueness enforcement are required; a caller-supplied list is only a contract demonstration.

## 11. Structured failures

Reasons include INCOMPLETE_SNAPSHOT, INCOMPLETE_FIELDS, INCOMPLETE_ASSOCIATIONS, AMBIGUOUS_ABSENCE, SNAPSHOT_SCOPE_MISMATCH, STATE_CHANGED, STALE_APPROVAL, PLAN_HASH_MISMATCH, APPROVAL_MISMATCH, BLOCKING_CONFLICT, PROJECTION_REJECTION, MATERIALIZATION_FAILED, MISSING_REQUIRED_CREATE_FIELD, LEGACY_SCHEMA_INCOMPATIBLE, IDENTITY_REBIND, RELATIONSHIP_CHANGED, UNSUPPORTED_OPERATION, PLAN_OPERATION_MISMATCH, MISSING_FIELD_BASELINE, CONFLICT_MANUAL_CHANGE, AMBIGUOUS_SOURCE_PRECEDENCE, REGISTRY_CHANGED, ALREADY_EXECUTED, INVALID_CANDIDATE and CONCURRENT_STATE_CHANGE. Authentication and absent executor are explicit limitations even on technically eligible candidates. Error boundaries return safe machine codes, not supplied credentials or payload contents.

## 12. Fictional tests and validation

The invented Ember fixture contains complete existing set state and fully specified fictional card fields. Fifty-two new tests cover create/update/clear; carried-forward, unchanged, ABSENT and UNKNOWN fields; missing required and optional create values; explicit absence, ambiguous/duplicate/non-exhaustive coverage, every inventory category, incorrect proof hash/status; incomplete fields/associations; occupied numbers, ownership and state drift, manual edits, registry/policy changes; corrupted plan/approval/operation graph, immutable payload and tampered candidate; exact-plan use without replanning; concurrency and ABA; success/failure receipt validation and replay. A fresh subprocess import guard excludes application DB modules and legacy runner/planner; the pure gate is also exercised with socket connections blocked.

Validation completed:

- Baseline full pytest: 574 passed.
- Final full pytest: 626 passed, 3 dependency deprecation warnings (Starlette/httpx, AnyIO alias, OpenAPI validator shortcut).
- Focused Phase 12D suite: 52 passed.
- Ruff check: passed.
- Ruff format validation: 114 files already formatted.
- Mypy `app importer scripts`: passed, 71 source files.
- Existing OpenAPI/export tests: passed in full suite.
- Read-only RapidAPI OpenAPI validation: passed; OpenAPI 3.0.2, 12 paths, exactly 12 GET operations.
- Artifact SHA-256 unchanged: `9c76bca79d0056051dc2538e6b6b45382bb5275699d25e941fc82dbc5311d386`.
- Artifact path: `C:\Users\elena\Downloads\naruto-mythos-api-phase4\naruto-mythos-api-dl\docs\generated\openapi.rapidapi.json`.

Tests used isolated fake settings with dotenv reads disabled in memory, including existing subprocess tests. The existing regression suite independently exercises legacy importer behavior against its test databases; the Phase 12D gate and new tests never call the legacy apply path. No production connection was used. No repository environment or test configuration was edited. The tracked OpenAPI artifact was read and validated, not regenerated.

## 13. Deferred work, limitations and recommendation

Deferred: trusted approval authentication; a real exhaustive reader; durable registry and field baselines; receipt persistence; exact-operation applier; transaction/locking integration; permissions, recovery and operational procedures. Any schema changes require a separate approved phase. PostgreSQL concurrency behavior has not been integration-tested here because this phase permits fictional mechanisms only.

Further limitations: conservative whole-set closure may require replanning more often; reader declarations need a trusted implementation; new-set and mixed-source full legacy representations can intentionally fail compatibility; images are unsupported; legacy writer is not safe for these candidates; technical eligibility is never production authorization.

Recommended next work, only after human approval: an isolated non-production executor design/integration test phase with authenticated approval contracts, durable baseline/receipt decisions and PostgreSQL transaction tests covering manual writers, absent-row races, rollback and replay. Do not enable any production path based on this phase alone. That work has NOT started.

## 14. Safety and stop record

- Real Naruto data used: NO.
- Network catalogue acquisition: NO. Only PostgreSQL technical documentation was consulted.
- Official artwork downloaded: NO.
- Production DB accessed or modified: NO.
- Existing importer apply path invoked by Phase 12D: NO (existing isolated regression tests are described above).
- Production execution path created: NO.
- Railway modified or queried: NO. Auto Deploy was not enabled.
- RapidAPI modified: NO.
- Deployment performed: NO.
- Migration created: NO.
- `.env` read: NO.
- Commit created: NO.
- Push performed: NO.
- Next phase started: NO.

Stop for human review. This report does not confer approval or authorize execution.
