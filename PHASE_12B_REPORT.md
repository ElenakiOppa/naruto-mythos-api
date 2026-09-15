# Phase 12B — Normalized Phase 12B has passed human review and is APPROVED.

Commit the existing Phase 12B implementation exactly as currently validated.

STRICT SCOPE:
- Do not modify any files before committing.
- Do not regenerate anything.
- Do not change code, tests, fixtures, documentation, configuration, dependencies, migrations, or generated OpenAPI.
- Do not modify Railway.
- Do not modify RapidAPI.
- Do not deploy or redeploy.
- Do not access or modify production PostgreSQL.
- Do not import catalogue data.
- Do not start Phase 12C.
- Do not enable Railway Auto Deploy.

Before committing:
1. Confirm the only repository changes are the seven previously reviewed untracked files:
   - PHASE_12B_REPORT.md
   - importer/staging/__init__.py
   - importer/staging/identity.py
   - importer/staging/models.py
   - importer/staging/validator.py
   - tests/fixtures/staging-fictional.json
   - tests/test_staging.py
2. Confirm no existing tracked file is modified.
3. Confirm git HEAD is still:
   d221ef5a14137c7ca0d72c9ddc232bc4b4037e49

Then:

1. Add exactly those seven files.
2. Commit with message:

   Implement Phase 12B staging identity layer

3. Push the commit to origin/main.

Do NOT deploy.

After pushing report:
- new commit hash
- push result
- git status
- confirmation local main == origin/main
- exact committed file list
- confirmation no other files changed
- confirmation no Railway deployment was initiated
- confirmation no Railway/RapidAPI configuration changed
- confirmation no production database was accessed or modified
- confirmation no real catalogue data was imported
- confirmation Phase 12C was NOT started

STOP after the push.staging contract and identity validator

Status: implemented locally for review; fictional fixtures only. No commit or push.

## Baseline and boundary

- Started on clean `main` at `d221ef5a14137c7ca0d72c9ddc232bc4b4037e49`, which includes the completed Phase 11 acceptance report.
- Railway Auto Deploy OFF is the owner-confirmed state, also recorded in Phase 11. It was not independently queried in this phase; Railway and production credentials were not accessed.
- Production catalogue emptiness is the previously owner-confirmed state. No production connection or import was performed to recheck it.
- No external catalogue pages, guides, artwork, or real card data were fetched or used.
- This package is not connected to the existing importer planner/apply path, public routes, application configuration, or database. Staging acceptance does not authorize ingestion or redistribution.

## Files added

| File | Purpose |
| --- | --- |
| `importer/staging/__init__.py` | Isolated package boundary |
| `importer/staging/models.py` | Versioned Pydantic contract and explicit approval policy |
| `importer/staging/identity.py` | Canonical identities, deterministic IDs, registry snapshot |
| `importer/staging/validator.py` | Pure batch validation, proposals and quarantine report |
| `tests/fixtures/staging-fictional.json` | Clearly fictional scopes, printings and treatment |
| `tests/test_staging.py` | Contract, identity, collision, parent and safety regressions |
| `PHASE_12B_REPORT.md` | Architecture, validation and remaining boundaries |

No existing tracked file, production model, migration, dependency, configuration, route, or generated artifact was changed.

## Contract and usage

`Record` version `1` carries source, independent metadata/text/image rights, printing identity, display labels, typed card fields, optional treatment metadata, rarity, keywords, images, availability, field evidence, unresolved questions and review status. Unknown language, number and serialization remain null. Rights default to UNKNOWN; review defaults to UNREVIEWED.

Source metadata includes name, optional HTTP(S) URL, timezone-aware retrieval time, optional revision and SHA-256 content hash, and one of the four controlled authority classifications. Source/evidence/image URLs reject embedded username/password credentials. No URL is fetched. Availability includes a validated date, territory and release status.

Call `validate_records(records, policy, registry=None)` with dictionaries or `Record` instances. It returns a Pydantic `Result` and has no database or file-write side effects. Instances are revalidated to catch invalid `model_copy` updates. There is no CLI, source parser, persisted staging store or projection into the old importer.

The policy explicitly enumerates approved expansion/edition/language/territory scopes, namespaces, treatment keys and finish keys. It never infers a cross-product of edition and language availability. Initial namespaces are STANDARD, MISSION, PROMO and SPECIAL; additional controlled keys can be approved through policy without a migration.

## Identity and stable IDs

Printing identity uses immutable expansion and edition keys, language, optional territory, numbering namespace and the entire printed identifier. Labels, names, rarity, source URLs, retrieval dates and artwork URLs are excluded. Missing required identity components are quarantined; no surrogate collector number is invented.

Canonical representation is versioned JSON with sorted keys, compact separators and Unicode NFC normalization. Original input text is retained. Numbers are strings; no case folding, integer conversion, suffix stripping or whitespace collapse occurs. Surrounding number whitespace is rejected. NFC-equivalent identifiers deliberately collide and are quarantined as duplicates.

IDs use `cpr_` or `trt_` followed by the first 56 hexadecimal characters of SHA-256 of canonical UTF-8 identity: 60 characters total, 224 digest bits. A golden-vector test freezes version 1 behavior. Hash collisions are still explicitly detected; hashing is not treated as proof of uniqueness.

`Registry` copies an explicit canonical-identity-to-public-ID snapshot. Existing assignments take precedence and are never replaced. All batch proposals are checked against each other and reserved IDs, including records absent from the batch. Invalid existing assignments fail rather than silently deriving replacements. A record declaring an existing ID must have that exact assignment registered.

Registry persistence, completeness across batches, and authorization to change approved identity components are future responsibilities. Callers must supply the authoritative snapshot for existing IDs. Changing a true identity component is not a name correction and needs a separate reviewed identity decision.

## Treatments and gameplay protection

A treatment names an explicit parent record in the same batch, repeats its printing identity, and provides VERIFIED equivalence with an evidence reference resolving in its evidence map. The parent must be an accepted printing, not another treatment. Similar names or numbers never create a relationship.

Treatment identity consists of the parent's canonical identity plus approved treatment key, optional approved finish key and optional collector-number override. Serialization flag and print-run quantity are metadata, not physical-copy identity. A known serial total requires serialization to be explicitly true.

Supplied gameplay values are compared against the parent: name, subtitle, type, chakra, power, faction, effect text, Mission points and rank. Differences, attempted clears, or unavailable parent values quarantine the relationship. Keyword overrides are conservatively compared too. Omitted/unknown child fields do not override parent values. Parent failures, including later public-ID collisions, invalidate dependent treatments. Image owner kind must match its containing record.

## Missing, null and explicit clear

Typed `FieldValue` operations avoid default-null overwrite semantics:

| State | Meaning |
| --- | --- |
| ABSENT | Field not supplied; no instruction to change it |
| UNKNOWN | Explicitly unknown/null; no instruction to clear it |
| VALUE | A validated non-null value is supplied |
| CLEAR | Explicit clear instruction with a required nonblank approval reference |

Omitted card fields produce ABSENT; bare null produces UNKNOWN. Rarity fields and optional collections also support null as UNKNOWN. State envelopes survive JSON round trips, including absence. Contradictory states and values fail validation. Required card name cannot be cleared. Card field presence and clear lists are derived properties, so independently supplied contradictory lists cannot be accepted.

The approval reference is an asserted review reference, not authentication or an approval signature. A future approval-bound projection must verify it. No operation currently modifies a stored value. In particular, a VALUE containing an empty list is distinct from CLEAR; its eventual collection-update policy must be reviewed before projection.

## Quarantine and reporting

Every unresolved input has an index, record key when parseable, machine reason, explanation and available evidence references. Structurally malformed inputs retain their index and field locations without echoing their raw values. No input is silently dropped.

The deterministic report contains accepted/unresolved counts, accepted identity/ID proposals, all proposed IDs (including subsequently collided proposals), warnings, collision and duplicate groups, full source summaries and per-content rights summaries. Consumers must use `accepted`, not the diagnostic proposal list. Malformed records cannot contribute validated source/rights metadata.

All claimants to duplicate identities are quarantined. Missing identity, unapproved scope/namespace, unapproved review, unresolved questions, ambiguous/unverified parents, unsupported treatments, gameplay conflicts, invalid existing IDs and ID collisions have explicit reasons. Source and rights warnings remain visible even for staging-valid records. UNSUITABLE fictional sources can pass staging structure checks; this never makes them publishing inputs.

## Fictional fixtures and tests

The fixture explicitly declares its fictional nature and uses `example.invalid` URLs. It contains Ember Trials first/second editions, EN/FR scopes, the same identifier in different scopes and namespaces, and a serialized prism treatment with invented equivalence evidence. It contains no image binaries or real-source content.

101 added parametrized test cases cover all 24 requested categories plus NFC identity behavior, complete-number preservation, territory separation, existing registry assignments, reserved/forced ID collisions, dependent quarantine, duplicate treatments, serialization, field-state round trips, malformed metadata, nested credential URLs, image ownership, deterministic nonmutating output and the package import boundary. Invalid fixtures are generated by explicit mutations of the fictional fixture in tests.

## Validation

- Full pytest suite: **511 passed**, with three dependency deprecation warnings (Starlette/httpx, anyio alias, OpenAPI validator shortcut).
- Ruff check: **passed**.
- Ruff format validation: **98 files already formatted**.
- Mypy `app importer scripts`: **passed, 59 source files**.
- Existing OpenAPI/export tests: **passed as part of the full suite**.
- RapidAPI artifact: unchanged OpenAPI **3.0.2**, **12 paths**, **12 GET operations**.
- Artifact SHA-256 remains `9c76bca79d0056051dc2538e6b6b45382bb5275699d25e941fc82dbc5311d386`.

Tests ran with dummy local test settings and in-memory suppression of dotenv reads, including the Python subprocess used by the docs configuration test. No local `.env` was opened. Repository test files/configuration were not altered for this isolation; normal assertions ran. Existing tests use isolated SQLite or mocked database connectivity. No production database was used. Routine ignored tool/test caches may update locally.

## Deferred decisions and limitations

- Expansion/printing tables, namespace-aware database uniqueness, unnumbered-card identity, Mission fields and variant-aware public filtering remain deferred. No migration is necessary for this isolated staging phase.
- Registry persistence, cross-batch completeness and authenticated human approval are not implemented.
- Evidence/rights assertions are recorded, not independently authenticated. No publisher rights or real-source completeness is established here.
- Variant equivalence checks are intentionally conservative; keyword ordering differences can require review. Unknown gameplay is not repaired.
- No fetcher, parser, durable quarantine store, importer projection, dry-run plan binding, overwrite protection in the existing writer, or production ingestion is introduced. The old writer's omission behavior is unchanged because this staging layer cannot call it.

## Recommendation

Phase 12B: **GO for local human review**, not committed or pushed.

Phase 12C: **CONDITIONAL GO only after explicit approval** for fictional-only, read-only projection design and approval-bound dry-run planning. First resolve how unsupported staging dimensions are rejected, preserve missing/null/clear semantics through projection, and add manual-edit/stale-source conflict handling. Do not connect the production apply path or acquire real catalogue data as an implicit next step.

Real-source acquisition and production ingestion remain NO-GO until separate source, licensing, identity and production-approval gates are satisfied. Phase 12C has not started.

## Safety confirmation

Real catalogue data used: NO. Official artwork downloaded: NO. Production database accessed for writes or modified: NO. Railway/RapidAPI modified: NO. Deployment: NO. Migration: NO. Commit: NO. Push: NO.
