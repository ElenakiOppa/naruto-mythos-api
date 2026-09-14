# Approved local catalogue importer

Phase 8 accepts approved/local normalized JSON datasets. It does not automatically scrape Naruto Mythos, discover remote endpoints, fetch source URLs, or download artwork. All shipped examples are fictional.

## Usage

From the project root, with the configured PostgreSQL database and existing migrations applied:

```powershell
python -m importer.cli data/examples/fictional-catalogue.json --dry-run --report dry-run.json
python -m importer.cli data/examples/fictional-catalogue.json --report import-report.json
```

The first command is read-only. The second persists the supplied fictional example; use an approved dataset for actual catalogue work. Reports are JSON on stdout, structured execution summaries are on stderr, and exit status is 0 for success or 1 for failure. `--report` writes a local copy and cannot overwrite the input file. A failure saving the report returns 1; an import already committed remains committed. Keep the stdout report in that case.

## Format and validation

See `data/schema/catalogue.schema.json` and `data/examples/fictional-catalogue.json`. Top-level fields are `source`, optional `variant_aliases`, and `sets`. Source requires `name` and timezone-aware `retrieved_at`; `url` is optional. Sets nest cards; cards nest keywords, variants, and direct images; variants nest their own images. Parent references are established by nesting, not internal UUIDs. Dedicated Pydantic importer models reject unknown fields and invalid references expressed as unsupported fields.

Required IDs/names must be nonempty and fit database lengths. Numbers and collector numbers remain strings, including leading zeros. Counts/stats are strict nonnegative integers; image dimensions and serial totals are positive integers within PostgreSQL integer range. `serial_total` requires `serial_numbered=true`. HTTP(S) URLs are validated structurally; embedded credentials are rejected. No network validation occurs.

Duplicate JSON keys, set/card/variant IDs, numbers within a set, keywords within a card, scoped images, and conflicting keyword definitions are rejected before writes. Existing card/set or variant/card reassignment is rejected. Existing number collisions (including omitted cards), ambiguous image identities, and duplicate provenance for the same entity/source also fail planning. Number swaps between existing cards require separate correction; simultaneous swaps are deliberately rejected.

## Normalization and entity identity

Surrounding whitespace is trimmed. Empty optional strings become null. Keyword slugs are lowercase. Card names, meaningful internal whitespace, text, stats, rarity, and string numbers are otherwise preserved. URLs use Pydantic's structural canonicalization. Optional scalar omissions resolve to schema defaults/null: each supplied entity is a complete scalar snapshot, not a sparse patch.

Variant aliases are exact, case-sensitive mappings explicitly provided by the input (for example `{"Holo":"holographic"}`). Chains/cycles are rejected. Unknown labels pass through. Original and normalized aliases appear in the report; the existing provenance table has no raw-value column, so raw alias strings are not persisted there. Retain the approved input and report for that audit detail.

Sets/cards/variants match by public ID, keywords by normalized slug. Images match by owning card, optional variant, image type, and canonical URL. Changing an image URL creates another image and preserves the old one. Dimensions and attribution can update in place. Public image keys in plans are SHA-256 identifiers, not internal UUIDs. Every imported image has `hosted_by_us=false`; image bytes are never fetched.

## Provenance, hashing, and precedence

Each imported set, card, variant, keyword, and image receives a `source_records` row keyed logically by entity type, internal entity UUID, and source name. Source URL, external ID, content hash, first_seen_at and last_seen_at are stored. First seen is preserved; last seen is the maximum prior/input retrieval time. Reimporting the same retrieval time and content produces no writes. A newer retrieval time updates provenance observations even if entity content is unchanged.

Hashes use sorted-key compact JSON, explicit null, UTF-8, and SHA-256. They include normalized scalar content and parent public identity, never internal UUIDs or timestamps. Card hashes include the effective sorted keyword slugs. Nested entity contents are hashed independently: a card name update does not change its set hash. Hashes describe each source's last observed content, not an immutable import history.

Each explicit import wins for the supplied scalar snapshots regardless of retrieval date. Source B can update shared entities while Source A's provenance remains intact. This is deterministic import precedence, with no automatic conflict reconciliation or source priority inference.

## Change plan and deletion policy

Plans list sorted created/updated/unchanged keys separately for sets, cards, variants, keywords, images, and provenance; relationships list created/removed/unchanged card-to-keyword pairs. Counts mirror these lists. One changed card scalar produces one card update plus its provenance hash update. Relationship-only changes are reported under relationships and provenance rather than as scalar card updates.

Missing sets, cards, variants, keywords, and images are retained. There is no destructive sync mode. Missing/null keywords preserve a card's existing associations; an explicit list replaces that card's associations; `[]` clears them. Keyword entities remain. Omitted variants/images remain even when their arrays are empty.

## Transactions and scale

Validation precedes DB access; batched read-only planning precedes all writes. Actual application uses a single transaction, including entities, associations, and provenance. Any write failure rolls back everything. PostgreSQL dry runs use a repeatable-read, read-only transaction and emit no DML. Plans are previews of their snapshot; a later actual run replans.

The importer preloads relevant IDs in chunks of 400, batches inserts/updates, and obtains a transaction advisory lock for actual PostgreSQL imports. This serializes cooperating importer runs because existing image/provenance tables do not enforce their logical keys with unique constraints. External writers must coordinate separately. Existing constraints remain the final concurrent-write safeguard. Very large inputs are held in memory; this is a batch importer, not a streaming pipeline.

## Verification

`python -m pytest -q` runs isolated importer and public API regressions. `python -m scripts.verify_phase8` explicitly exercises the configured PostgreSQL database with uniquely prefixed fictional data, records exact created UUIDs in memory, and cleans those IDs in a finally block. It checks complete database snapshots before/after cleanup and writes `phase8_verification_results.json`. Run against a quiet development database: unrelated concurrent writes would fail the exact-snapshot assertion. The verification script is not an importer cleanup command for user datasets.
