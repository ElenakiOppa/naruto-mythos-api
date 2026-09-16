## Final implementation result

### 1. Final architecture/schema changes

- `Card` remains the conceptual/base card and preserves existing public IDs, relationships and `(set_id, card_number)` uniqueness.
- `CardVariant` remains the physical table and mapped class for compatibility; `Printing` is its domain alias. No table rename or existing ID rewrite occurs.
- Nullable `edition`, raw `source_variant`, nullable `card_version`, and nullable `stamp` complete Printing support; language remains outside Printing identity.
- `PrintingTranslation` supports per-printing/per-language text and image URL references only; it stores no artwork bytes.
- `SourceRecord` gains typed Printing provenance while preserving legacy polymorphic provenance behavior.
- `Card.points` is nullable and nonnegative. Chakra and all other numeric restrictions remain unchanged.

### 2. Migration revision and important operations

Revision: `c13c20260916`, parent `8b41e2a9c730`. Upgrade drops the old nonnegative Power check, adds domain columns/tables/indexes/foreign keys, rejects ambiguous legacy semantic rows, and preserves existing rows and public IDs. Downgrade refuses if points, negative Power, Printing discriminators, translations or typed provenance would be lost; it never deletes, clamps or nulls negative Power.

### 3. Power change

Power accepts strict signed 32-bit integers: `-2147483648` through `2147483647`. Only Power validation changed. Chakra, Points, serial totals and other numeric restrictions remain unchanged; public negative `power_min`/`power_max` filter behavior is unchanged.

### 4. Phase 12B/C/D changes

Version-2 domain contracts preserve the approved Printing fingerprint, nullable edition, language exclusion, provenance and signed Power. Sparse projection remains read-only; the old execution boundary rejects version-2 input with `DOMAIN_V2_EXECUTION_NOT_SUPPORTED`; production authorization remains false. Legacy version-1 contracts and the public API remain unchanged.

### 5. 636 compatibility result

The read-only local checker reports **636 SCHEMA_COMPATIBLE, 0 SCHEMA_INCOMPATIBLE_WITH_REASON**.

### 6. Test/Ruff/Mypy results

- Full pytest: **692 passed, 6 errors**. All six errors occur before Alembic execution while the disposable PostgreSQL fixture runs `initdb`; Windows Application Control blocks `C:/Program Files/PostgreSQL/18/lib/dict_snowball.dll`.
- Non-PostgreSQL Phase 13C/domain/Phase 12/importer tests: **293 passed, 6 deselected**.
- Ruff check: passed.
- Ruff format check: passed, 132 files formatted.
- Mypy `app importer scripts`: passed, 0 issues in 83 source files.
- Migration runtime tests are not claimed as passed because local PostgreSQL initialization is blocked by host policy.

### 7. OpenAPI/RapidAPI verification

RapidAPI SHA-256 remains `9c76bca79d0056051dc2538e6b6b45382bb5275699d25e941fc82dbc5311d386`. OpenAPI has 12 paths and 12 GET operations. RapidAPI/OpenAPI regression tests pass.

### 8. Files changed

The model, domain contract, migration, compatibility checker, schema fixture, regression tests and `PHASE_13C_REPORT.md` are the current local Phase 13C changes. No public API, deployment, Railway or RapidAPI configuration file was changed.

### 9. Git status

Changes remain local and uncommitted. No files are staged. No commit or push was performed.

### 10. REAL remaining blocker

The only remaining blocker is local PostgreSQL test infrastructure: `initdb` cannot load `dict_snowball.dll` because Windows Application Control blocks the installed library. No production or external workaround was attempted.

### 11. Recommendation

**CONDITIONAL GO** — implementation and 636/636 compatibility are complete, but final closure should wait for the local PostgreSQL policy to permit the disposable test cluster and for the six migration tests to run. No Phase 14 work should begin.
# Phase 13C — Domain schema and local migration validation

**STATUS: IMPLEMENTATION COMPLETE LOCALLY — FINAL VALIDATION BLOCKED ONLY BY LOCAL PostgreSQL INITDB POLICY.**

The approved decision was applied: `Power` is a signed PostgreSQL `INTEGER`, so legitimate source `Power=-1` is accepted. The read-only local catalogue compatibility check now reports **636 SCHEMA_COMPATIBLE, 0 SCHEMA_INCOMPATIBLE_WITH_REASON**. No real records were imported and no database was accessed.

The implementation and all non-PostgreSQL validation gates pass. The six isolated migration tests cannot start their disposable local PostgreSQL cluster because Windows Application Control blocks PostgreSQL 18's `dict_snowball.dll` during `initdb`; Alembic migration execution is therefore not falsely reported as validated. This is an environment blocker, not a source/model incompatibility.

The local implementation remains uncommitted and must not be deployed or used for real ingestion. No production database, external database, live acquisition, artwork, Railway or RapidAPI path was accessed.

## Stop record and draft implementation inventory

Created:

- `PHASE_13C_REPORT.md`
- `app/models/translation.py`
- `importer/domain_schemas.py`
- `importer/staging/domain.py`
- `importer/projection/domain.py`
- `migrations/versions/c13c20260916_printing_domain.py`

Modified:

- `app/models/__init__.py`
- `app/models/card.py`
- `app/models/source.py`
- `app/models/variant.py`
- `importer/execution_design/preconditions.py`

Migration revision: `c13c20260916`; parent `8b41e2a9c730`. File-graph head is `c13c20260916`. The migration was reviewed and its downgrade refuses when new domain data exists, including negative `power`, rather than deleting, clamping or nulling it. Runtime upgrade/downgrade execution was blocked before `initdb` by the local Application Control policy described above.

Draft columns: cards.points; card_variants.source_variant/card_version/stamp; source_records.printing_id/source_uid/source_sku/observation. New printing_translations contains UUID id, printing_id, language, title, subtitle, rules_text, edition_label, distribution_text, image_url, created_at and updated_at. Source observation JSON preserves uninterpreted source evidence, rather than silently dropping overflow. No real source record is written to these models or any database.

Constraints/indexes: nonnegative points check; PostgreSQL-only NFC-expression unique index `uq_printing_semantic_identity` over card_id plus edition/rarity_override/source_variant/card_version/stamp with NULLS NOT DISTINCT; unique translation printing/language; translation printing FK CASCADE; provenance printing FK RESTRICT plus owner-match check and printing_id index. Existing ownership, public-ID and Card(set_id, card_number) constraints remain. New typed provenance deliberately blocks deleting an observed Printing without explicit preservation/reconciliation.

Draft downgrade refuses new column values, translations or typed observations that would otherwise be lost. Existing IDs are never rewritten. Legacy duplicate/ambiguous semantic rows stop upgrade rather than merge; raw publisher variant is not inferred from normalized legacy variant_type.

Phase 12B alignment is drafted as an explicit version-2 Printing contract; legacy version-1 contracts are retained unchanged. New identity uses approved seven-field fingerprint, excludes language and source identifiers, and quarantines observed grouping conflicts. No golden vectors were rewritten. Phase 12C has a sparse domain preview preserving FieldValue states and references, not a new approved execution plan. Phase 12D explicitly refuses version-2 input at the old execution boundary; production authorization remains false. These are unfinished drafts, not a complete integration. Legacy importer parsing/writing behavior was not modified; new domain DTOs are separate and have no apply path.

Public API schemas/routes and generated OpenAPI were not edited. Pre-edit canonical OpenAPI SHA-256 (sorted compact JSON): `2ff9e05f04ce0fd8d4ec90065da61f1f661c9eee5389dc3c397c05d0a675ff18`. RapidAPI file SHA-256 remains `9c76bca79d0056051dc2538e6b6b45382bb5275699d25e941fc82dbc5311d386`, 12 paths, 12 GET operations. Post-change full pytest/Ruff/Mypy/migration checks are NOT RUN because implementation stopped on the required incompatibility condition.

The remaining action is environmental: unblock the disposable local PostgreSQL 18 `initdb` policy, then rerun the six migration tests. No Phase 13D work is authorized or started.

Safety: production DB accessed/modified NO; real catalogue imported NO; live acquisition/external network NO; artwork accessed/downloaded NO (URL strings only); public API changed NO; Railway/RapidAPI changed NO; deployment NO; dotenv read NO; commit/push NO.

## Baseline and final schema impact

Branch main; clean starting tree; HEAD a73a73300455dad68891c58628ad44121e977de6.
Baseline: 671 tests passed. Previous Alembic head: 8b41e2a9c730.
No production, Railway, RapidAPI or dotenv access. PostgreSQL 18 binaries are available locally.

Chosen strategy B: retain card_variants, class CardVariant and existing API/importer fields; export Printing as the same mapped class. No table rename or ID rewrite.

Add nullable card_version/stamp and raw source_variant to card_variants. source_variant is distinct from legacy variant_type: the latter is a required API-facing classification with alias normalization in the legacy importer, whereas the former is the nullable publisher identity value. No automatic alias/default guesses. Reuse edition and rarity_override. Semantic uniqueness uses parent card_id (already identifies expansion/printed number) plus edition, rarity_override, source_variant, card_version and stamp, NULLS NOT DISTINCT. PostgreSQL Unicode NFC normalization must agree with Python identity. Pre-existing conflicting legacy rows must stop migration for review, never be merged or deleted.

Add nullable points to cards. Character fields remain nullable. Add PrintingTranslation keyed by printing/language, with nullable title/text/subtitle/edition label/distribution text and image-reference URL. Preserve existing CardImage and its ownership actions. Reuse SourceRecord with nullable source_uid/source_sku and a nullable FK printing_id for new typed provenance; old polymorphic provenance remains untouched.

Use a versioned new staging contract for Card/Printing semantics rather than reinterpreting signed version-1 plans. Preserve old contracts and approvals, but reject new-version records at old projection/execution entry points until explicit supported mapping exists. New types expose approved fingerprint and provenance separately; conflicts quarantine. No new apply path.

Migration downgrade refuses whenever new values or translation/provenance data would be lost. Exactly one new migration. Isolated PostgreSQL only, fictional data only. No real data writes.

### Existing schema inventory


#### keywords

| Column | Type | Nullable | PK |
|---|---|---|---|
| slug | VARCHAR(64) | False | False |
| name | VARCHAR(128) | False | False |
| id | CHAR(32) | False | True |
| created_at | DATETIME | False | False |
| updated_at | DATETIME | False | False |

Constraints: 
- PrimaryKeyConstraint None: id

Indexes: ix_keywords_slug (slug) unique=True

#### sets

| Column | Type | Nullable | PK |
|---|---|---|---|
| public_id | VARCHAR(64) | False | False |
| code | VARCHAR(32) | True | False |
| name | VARCHAR(255) | False | False |
| edition | VARCHAR(64) | True | False |
| language | VARCHAR(8) | False | False |
| release_date | DATE | True | False |
| printed_total | INTEGER | True | False |
| total_with_variants | INTEGER | True | False |
| logo_url | TEXT | True | False |
| symbol_url | TEXT | True | False |
| id | CHAR(32) | False | True |
| created_at | DATETIME | False | False |
| updated_at | DATETIME | False | False |

Constraints: 
- PrimaryKeyConstraint None: id
- CheckConstraint ck_sets_printed_total_non_negative: ; printed_total IS NULL OR printed_total >= 0
- CheckConstraint ck_sets_total_with_variants_non_negative: ; total_with_variants IS NULL OR total_with_variants >= 0

Indexes: ix_sets_code (code) unique=False; ix_sets_name (name) unique=False; ix_sets_public_id (public_id) unique=True

#### source_records

| Column | Type | Nullable | PK |
|---|---|---|---|
| entity_type | VARCHAR(64) | False | False |
| entity_id | CHAR(32) | False | False |
| source_name | VARCHAR(128) | False | False |
| source_url | TEXT | True | False |
| external_id | VARCHAR(255) | True | False |
| content_hash | VARCHAR(128) | True | False |
| first_seen_at | DATETIME | False | False |
| last_seen_at | DATETIME | False | False |
| id | CHAR(32) | False | True |

Constraints: 
- PrimaryKeyConstraint None: id

Indexes: ix_source_records_entity_type_entity_id (entity_type, entity_id) unique=False; ix_source_records_source_name (source_name) unique=False; ix_source_records_source_name_external_id (source_name, external_id) unique=False

#### cards

| Column | Type | Nullable | PK |
|---|---|---|---|
| public_id | VARCHAR(64) | False | False |
| set_id | CHAR(32) | False | False |
| card_number | VARCHAR(32) | False | False |
| name | VARCHAR(255) | False | False |
| subtitle | VARCHAR(255) | True | False |
| card_type | VARCHAR(64) | True | False |
| rarity | VARCHAR(64) | True | False |
| chakra | INTEGER | True | False |
| power | INTEGER | True | False |
| faction | VARCHAR(64) | True | False |
| ability_text | TEXT | True | False |
| flavor_text | TEXT | True | False |
| artist | VARCHAR(255) | True | False |
| id | CHAR(32) | False | True |
| created_at | DATETIME | False | False |
| updated_at | DATETIME | False | False |

Constraints: 
- ForeignKeyConstraint None: set_id; ON DELETE RESTRICT
- PrimaryKeyConstraint None: id
- CheckConstraint ck_cards_chakra_non_negative: ; chakra IS NULL OR chakra >= 0
- CheckConstraint ck_cards_power_non_negative: ; power IS NULL OR power >= 0
- UniqueConstraint uq_cards_set_id_card_number: set_id, card_number

Indexes: ix_cards_card_number (card_number) unique=False; ix_cards_card_type (card_type) unique=False; ix_cards_name (name) unique=False; ix_cards_public_id (public_id) unique=True; ix_cards_rarity (rarity) unique=False; ix_cards_set_id (set_id) unique=False

#### card_keywords

| Column | Type | Nullable | PK |
|---|---|---|---|
| card_id | CHAR(32) | False | True |
| keyword_id | CHAR(32) | False | True |

Constraints: 
- ForeignKeyConstraint None: keyword_id; ON DELETE CASCADE
- ForeignKeyConstraint None: card_id; ON DELETE CASCADE
- PrimaryKeyConstraint None: card_id, keyword_id

Indexes: 

#### card_variants

| Column | Type | Nullable | PK |
|---|---|---|---|
| public_id | VARCHAR(64) | False | False |
| card_id | CHAR(32) | False | False |
| variant_type | VARCHAR(64) | False | False |
| finish | VARCHAR(64) | True | False |
| rarity_override | VARCHAR(64) | True | False |
| collector_number | VARCHAR(32) | True | False |
| language | VARCHAR(8) | False | False |
| edition | VARCHAR(64) | True | False |
| serial_numbered | BOOLEAN | False | False |
| serial_total | INTEGER | True | False |
| id | CHAR(32) | False | True |
| created_at | DATETIME | False | False |
| updated_at | DATETIME | False | False |

Constraints: 
- PrimaryKeyConstraint None: id
- ForeignKeyConstraint None: card_id; ON DELETE CASCADE
- CheckConstraint ck_card_variants_serial_total_positive: ; serial_total IS NULL OR serial_total > 0
- UniqueConstraint uq_card_variants_id_card_id: id, card_id

Indexes: ix_card_variants_card_id (card_id) unique=False; ix_card_variants_public_id (public_id) unique=True; ix_card_variants_variant_type (variant_type) unique=False

#### card_images

| Column | Type | Nullable | PK |
|---|---|---|---|
| card_id | CHAR(32) | False | False |
| variant_id | CHAR(32) | True | False |
| image_type | VARCHAR(32) | False | False |
| url | TEXT | False | False |
| source_name | VARCHAR(128) | True | False |
| source_url | TEXT | True | False |
| hosted_by_us | BOOLEAN | False | False |
| width | INTEGER | True | False |
| height | INTEGER | True | False |
| created_at | DATETIME | False | False |
| id | CHAR(32) | False | True |

Constraints: 
- ForeignKeyConstraint None: card_id; ON DELETE CASCADE
- PrimaryKeyConstraint None: id
- CheckConstraint ck_card_images_height_positive: ; height IS NULL OR height > 0
- CheckConstraint ck_card_images_width_positive: ; width IS NULL OR width > 0
- ForeignKeyConstraint fk_card_images_variant_card_owner: variant_id, card_id; ON DELETE SET NULL (variant_id)
- ForeignKeyConstraint fk_card_images_variant_id_card_variants: variant_id; ON DELETE SET NULL

Indexes: ix_card_images_card_id (card_id) unique=False; ix_card_images_variant_id (variant_id) unique=False

### Current relationships and exposure

CardSet.cards restricts deletion of a nonempty set through cards.set_id. Cards own variants and direct images with delete cascades; keyword links cascade but keywords are independent. Variant deletion preserves image metadata via SET NULL (variant_id), with PostgreSQL composite ownership validation. SourceRecord is polymorphic and has no entity FK. Internal UUIDs never leave the API. Existing importer public IDs, set metadata, card gameplay fields, variant classification/edition/rarity/serialization and image metadata correspond to the current API; provenance is not a public response. New domain fields will not be added to response schemas. Existing localization-like set/variant language fields remain legacy presentation fields, outside semantic Printing identity.
