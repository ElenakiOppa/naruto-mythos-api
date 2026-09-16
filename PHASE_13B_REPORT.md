# Phase 13B — Real catalogue identity & schema design

Status: LOCAL DESIGN + VALIDATION ONLY — read-only analysis of the Phase 13A local acquisition. No migration, no import, no API change. Not committed. Implementation phase NOT started.

**Revision note (identity-closure review, section 24A): human review did not approve `source_uid` as part of canonical semantic Printing identity.** The design has been revised: `source_uid` is now excluded from the canonical identity hash entirely. Re-analysis found the 7 residual semantic collisions (15 records) are fully resolved by two evidence-backed, publisher-assigned fields already present on every record — `card_version` and `stamp` — with **zero remaining collisions and zero dependency on `source_uid` or any opaque/random identifier**. See section 24A for the full closure review.

Recommendation: **GO** for an implementation phase, scoped exactly to the schema changes in section 33, with the revised identity design in section 24A treated as the accepted contract (section 24 is retained below for history but is **superseded** by 24A).

## 1. Executive summary

This phase analyzed all 636 real card print-records from the Phase 13A local acquisition to design (not implement) a catalogue identity and schema architecture. An analysis-only, dependency-free Python package (`importer/catalogue_design/`) was built to make every finding reproducible and testable.

Headline result: **all 636 real records map cleanly (636 MAPPED, 0 AMBIGUOUS, 0 REJECTED)** onto a two-level `Card` → `Printing` model, using `(expansion, printed_identifier)` as a validated, title-invariant `Card` grouping key (318 distinct Cards) and, **after the identity-closure revision**, `(expansion, edition, printed_identifier, rarity, variant, card_version, stamp)` — with no `source_uid` — as a collision-free `Printing` identity (636 Printings, one per source record). The original semantic fields alone (without `card_version`/`stamp`) are collision-free for 628/636 records; the remaining 7 residual collisions (15 records) are all Mythos/Special promotional prints, and are fully resolved by `card_version` (13/15 records) plus `stamp` (the final 2) — both already-present, publisher-assigned, non-opaque fields. `source_uid`/`SKU` are preserved as source-record provenance only, never as canonical identity (section 24A).

A significant discovery: **Phase 12B's existing (fictional) staging identity design already anticipated this exact two-level shape** (`importer/staging/models.py`/`identity.py`), but with the two levels named oppositely to this phase's brief — Phase 12B's `"PRINTING"` kind structurally matches this phase's `Card` concept, and Phase 12B's `"TREATMENT"` kind structurally matches this phase's `Printing` concept. This is a naming/terminology reconciliation, not a structural rebuild (see sections 9, 24, 30).

Also significant: the existing production `CardVariant` model (`variant_type`, `finish`, `rarity_override`, `collector_number`, `edition`, `serial_numbered`, `serial_total`) is already close to the required `Printing` shape, and the existing `Card(set_id, card_number)` uniqueness constraint turns out to be **compatible as-is**, provided `card_number` maps to the printed identifier at the Card level and rarity/edition/variant differentiation stays on `CardVariant`.

## 2. Baseline

- Branch: `main`. Working tree: clean. HEAD: `cd980931b4418cae9e237768ed184e65609f7c94` — matches expected exactly.
- Phase 12B/12C/12D packages and reports, and the Phase 13A acquisition package/report, are present.
- Baseline full test suite (before this phase's files): 642 passed, 0 failed.
- Railway, RapidAPI, production PostgreSQL and `.env` were not queried/read.

## 3. Input snapshot

All 636 records were loaded from the already-acquired Phase 13A local files (no live fetch performed):

- `data/acquisition/manifest.json` → located the most recent `cards.narutotcgmythos.com/api/cards?lang={en,fr,it,es}` entries.
- Raw bodies loaded from `data/acquisition/raw/*.json` (content-addressed by SHA-256, exactly as captured in Phase 13A).
- Record counts: `en`=636, `fr`=636, `it`=636 (byte-identical to `en`, per Phase 13A), `es`=636.

## 4. Source field inventory

Fields observed on the 636 `en` records (same set found in Phase 13A, confirmed again here): `Uid`, `SKU`, `ID`, `Set`, `Edition`, `Langs`, `CardType`, `Title`, `Rarity`, `Variant`, `Illustration`, `CardVersion`, `Version`, `Group`, `Chakra`, `Power`, `Points`, `Keyword1`, `Keyword2`, `Text`, `Obtain`, `Stamp`, `Image`, `Order`. One stray record carries an extra blank-string key (`""`) — preserved as `extra` overflow by `SourceCardRecord.from_raw`, never dropped. No other unknown fields were found in this snapshot.

## 5. Uid findings

`importer.catalogue_design.analyzer.audit_uid` over all 636 `en` records:

- **Uniqueness**: 636/636 unique, 0 nulls, 0 duplicates.
- **Type**: `int` for all records.
- **Range**: 203–867, **not contiguous** (12 gaps > 1) — consistent with an internal auto-increment database primary key that has had rows deleted/reassigned elsewhere in the vendor's system, not a curated sequence.
- **Relationship to SKU**: 1:1 in this snapshot (every Uid maps to exactly one SKU and vice versa).
- **Relationship to printed ID**: many-to-one (many Uids can share one printed ID — this is the collision pattern in section 7/11).
- **Localized responses**: identical Uid set across `en`/`fr`/`es`/`it` (same 636 Uids, same associated identity fields — see section 20).
- **Reuse**: not observed in the real snapshot; the mapping pipeline explicitly detects reuse as `AMBIGUOUS` (tested in `test_mapping_detects_reused_uid_as_ambiguous_not_merged`) rather than assuming it can't happen.

**Conclusion**: Uid is empirically unique and stable within this snapshot, but its non-contiguous, auto-increment-like shape means it should be preserved as **source evidence and a disambiguating tiebreaker**, not adopted as the sole canonical identity (per the brief's explicit caution).

## 6. SKU findings

`audit_sku` over all 636 records:

- **Uniqueness**: 636/636 unique, 0 nulls.
- **Grammar**: 620/636 (97.5%) match `NM-S{set}E{edition}-{RarityCode}{3-digit-or-MSS-number}{TreatmentSuffix}V{version}`, e.g. `NM-S1E1-L133V1`, `NM-S1E1-C001FAV1`, `NM-S2E1-C079HV1`.
- **16 unmatched** are all Mythos/Special promos using a **different, still-structured** grammar: `NM-S{set}E0-{RarityCode}{number}V{version}-{DistributionCode}`, e.g. `NM-S1E0-M104V2-W`, `NM-S2E0-M126V2-RC`. Two features stand out:
  - `E0` is the vendor's own sentinel for **"no edition"** — direct source-side confirmation of the editionless-promo pattern found in Phase 13A.
  - The trailing suffix (`-W`, `-SC`, `-RC`, `-RE`) encodes **distribution channel** (Weekly OP kit, Store Championship, Regional Championship, Release Event) directly in the SKU — useful corroborating evidence for section 21, but not adopted as a contractual parser per the brief's caution ("do not treat inferred SKU grammar as contractual unless verified").
- **Stability vs Uid**: SKU is human-readable and semantically structured (encodes set/edition/rarity/number/treatment/version), whereas Uid is an opaque row id. SKU is a better candidate for a human-facing external reference; Uid is a better candidate for a guaranteed-unique tiebreaker. Neither is treated as sufficient alone.

## 7. Printed identifier findings

Reproducing and extending the Phase 13A collision analysis with the real records (`collision_key_progression`):

| Candidate key | Unique keys | Colliding keys | Max group size |
|---|---|---|---|
| `(set, id)` | 318 | 185 | 7 |
| `(set, edition, id)` | 483 | 103 | 7 |
| `(set, edition, id, rarity)` | 628 | 7 | 3 |
| `(set, edition, id, rarity, variant)` | 628 | 7 | 3 |

Adding `variant` on top of `rarity` produces **no further improvement** in this snapshot (no observed case where two records share identical `set/edition/id/rarity` and differ only by `variant`). The 7 residual collisions at the richest semantic key are enumerated in section 24 — every one is a Mythos or Special promo pair distinguishable only by freeform `Stamp`/`Obtain` text and by `SKU`/`Uid`.

Correction to a Phase 13A hypothesis: Phase 13A speculated the ordinary `001/130`-style collisions were "Normal vs Full-Art" pairs. Real per-record inspection shows this specific example, and most of the `(set,id)`-only collisions, are actually **edition reprints** (e.g. `001/130` = the same Common Full-Art Hiruzen Sarutobi printed once in `1st edition` and once in `2nd edition`) — Normal/Full-Art pairing does also occur elsewhere, but edition reprinting is the dominant pattern at that key level. This is now stated with direct per-record evidence rather than inference.

## 8. Card concept

**Grouping evidence** (`card_grouping_report`): grouping by `(expansion=Set, printed_identifier=ID)` alone (no edition/rarity/variant) produces 318 groups; of the 185 groups with more than one printing, **100% are Title+CardType invariant** — zero mismatches. This was true across every rarity tier tested, including cross-rarity groups like `133/130` (Legendary + Secret Variant + Secret all sharing the printed number, all titled "Naruto Uzumaki").

**Conclusion**: `Card` = `(expansion, printed_identifier)` is a safe, evidence-backed grouping key, validated without any name-only heuristic (title was used only to *confirm* the grouping, never to *form* it). No ambiguous grouping case was found in the real 636 records.

**Scope of this finding (identity-closure review)**: the 318-Card grouping is retained because it continues to show zero `CardType`/title conflicts after the identity revision in section 24A (grouping is independent of the `Printing`-level fields that changed). This is explicitly a grouping rule **supported by the current 636-record snapshot, not asserted as permanent identity law.** `card_grouping_report` reports mismatches rather than silently grouping through them; a future record set that produces even one Title/CardType mismatch within a `(expansion, printed_identifier)` group must be quarantined (treated as `AMBIGUOUS`/held for review), not forced into an existing Card.

## 9. Printing concept

Do all 636 records map one-to-one to a `Printing`? **Yes, without exception** — `map_all_records` classifies all 636 as `MAPPED`, 0 `AMBIGUOUS`, 0 `REJECTED` (section 26).

Candidate `Printing` fields, evaluated against real data: `public_id` (to be derived), `card_id` (parent), `source_uid`, `source_sku`, `printed_identifier`, `edition` (nullable), `rarity`, `source_variant`, `finish`/`illustration`, serialization metadata (section 19), distribution metadata (section 21), source provenance. All of these have direct evidence in the 636 records; none were invented.

## 10. CardVariant decision

The existing `CardVariant` model already carries: `variant_type`, `finish`, `rarity_override`, `collector_number`, `language`, `edition`, `serial_numbered`, `serial_total`. Mapped against the real evidence:

| CardVariant field | Real-data fit |
|---|---|
| `rarity_override` | Directly matches source `Rarity` (already exists — no new column needed) |
| `edition` | Directly matches source `Edition`, already nullable (matches editionless promos exactly) |
| `collector_number` | Can hold the source `ID`/printed identifier, and already supports a *per-printing override* distinct from the parent `Card.card_number` — a good fit for promo prints that reuse or override a number |
| `finish` | Candidate home for `Illustration`/finish-like data (constant `"Standard"` in this snapshot; not yet exercised by real variation) |
| `serial_numbered` / `serial_total` | Matches the catalogue-level (not per-physical-copy) serialization concept exactly (section 19) |
| `language` | Exists, but must **not** become part of any future uniqueness key — evidence (section 20) shows language is presentation-only |
| *(missing)* `source_uid`, `source_sku` | Not columns on `CardVariant` — see recommendation below |

**Decision (evidence-based): (A) `CardVariant` should become `Printing`** — i.e. extend the existing table/model in place rather than introduce a parallel entity. A brand-new `Printing` table would duplicate a model that is already ~80% structurally correct. The two gaps are: no composite uniqueness constraint (only the trivial `(id, card_id)` constraint exists today) and no columns for source `Uid`/`SKU`.

For the `Uid`/`SKU` gap: the existing **`SourceRecord`** provenance table (`entity_type`, `entity_id`, `source_name`, `external_id`, `content_hash`) is *already designed* to hold exactly this (`entity_type="card_variants"`, `external_id=<Uid or SKU>`, `source_name="narutotcgmythos_api"`). No new column is obviously required for this purpose — reusing `SourceRecord` is the minimal-change path (see section 29).

Phase 12 assumption under each choice (brief's options A–E): choosing (A) keeps Phase 12B's `Treatment` concept (section 30) intact structurally — Phase 12B's `Treatment.parent_record_key`, `treatment_key`, `finish_key`, `collector_number`, `serial_numbered/total` map almost directly onto the extended `CardVariant`/`Printing` row. Choosing (C) "replaced by Printing" would require re-deriving those same fields under a new name for no structural gain. (B)/(D)/(E) were not supported by evidence found in this phase.

**Naming authority (identity-closure review)**: this phase's terminology is authoritative going forward — `Card` = the conceptual/base card (identity: `expansion` + `printed_identifier`), `Printing` = one collectible publisher print/design record (identity: section 24A). `CardVariant` should be **renamed to `Printing`** when the implementation phase touches this table, or, if a rename is deferred for migration-risk reasons, **retained temporarily as a compatibility layer** with `Printing` as a documented alias — either is acceptable, but no third name should be introduced. Its future composite uniqueness constraint (section 33) should be widened to include `card_version` and `stamp` alongside `rarity_override`/`edition`/`collector_number`, per the revised identity in section 24A.

## 11. Edition model

Real evidence: Set 1 has `1st edition` (186), `2nd edition` (187), and blank/editionless (21, all Mythos) records; Set 2 currently has only `1st edition` (242) but the SKU grammar (`E0` sentinel, section 6) shows the vendor's own system already anticipates editionless Set 2 promos.

Evaluated against the two structures in the brief:

- **`Expansion → ExpansionEdition → Printing` (with a parallel editionless-Printing branch)**: adds a real entity for a concept (`edition`) that, per evidence, only ever needs to be a nullable *label* attached to a printing — no edition-level aggregate field (release date, printed total, etc.) was found to differ meaningfully from the parent `Expansion`/`Set 1: Konoha Shidō` in the acquired data. Building an intermediate entity for this would require inventing scope not evidenced by the source.
- **`Expansion → Printing.edition nullable`**: matches the existing `CardVariant.edition` (nullable) column exactly, and matches all 636 real records without exception, including editionless Mythos promos (verified: `edition=None` is `MAPPED`, never forced into a fake edition value — `test_editionless_promo_is_mapped_not_rejected`).

**Decision: edition belongs on `Printing` (nullable), not as an intermediate entity or a `CardSet`/`Expansion`-level column.** This also means `CardSet` does not need to be split per edition (one `CardSet` row per real `Set` value is sufficient) — a smaller change than initially suspected in Phase 13A section 24.

## 12. Normal/Full-Art relationships

Ordinary `C`/`UC` records sharing a printed ID were inspected directly (e.g. `001/130` group). Within this snapshot, most same-number `C`/`UC` pairs observed differ by **edition** (1st vs 2nd) rather than by `Variant` alone; genuine Normal-vs-Full-Art pairing (same edition, same rarity, differing only by `Variant`) also exists elsewhere in the catalogue (`Variant` distribution from Phase 13A: 285 "Full Art", 31 "Holo", 317 blank). In every case checked: same `Title`, same `CardType`, same `Set`; `SKU`/`Uid` always differ. This is exactly the pattern a `Card` → multiple `Printing` rows model represents cleanly, without needing a separate "finish" entity for this snapshot.

## 13. Holo relationships

`Variant="Holo"` appears on 31 records, concentrated in `Attachment` cards (31 of 32 Attachments are `Holo`, 1 is `Full Art` — a likely data-entry inconsistency in the source, flagged not resolved). Holo records share the same `Card` grouping key as their non-Holo counterparts where a counterpart exists, and are `MAPPED` as ordinary `Printing` rows differentiated by `Variant`. No evidence supports Holo as an independent `Card`; it is a `Printing`-level attribute (treatment/finish), consistent with section 12's conclusion.

## 14. Secret / Secret Variant analysis

`S` (30) and `SV` (12) records: printed-number reuse confirmed (e.g. `133/130` shared by `L`/`SV`/`S` in edition 1, plus a 2nd-edition `S` reprint). Title/gameplay fields (`Title`, `CardType`) are invariant with their same-number siblings (validated by the same 100%-invariant grouping check in section 8 — no separate check was needed because Secret/Secret Variant records participate in the same `(set,id)` groups already tested). Edition behaves normally (both editions observed). SKU pattern matches the ordinary grammar. **Conclusion**: Secret/Secret Variant share the `Card` parent of their base-numbered sibling; no name-only inference was used — the shared `(set,id)` key and confirmed title invariance is the evidence.

## 15. Mythos/promos analysis

39 `Rarity=M` records total. Edition breakdown (corrects a Phase 13A imprecision): **21 blank, 14 `1st edition`, 4 `2nd edition`** — i.e. `blank edition ⟹ Mythos` holds, but `Mythos ⟹ blank edition` does **not** hold (18/39 Mythos records do carry an edition). `SKU` for the blank-edition subset uses the `E0` sentinel and a distribution-code suffix (section 6); `Obtain`/`Stamp` carry freeform provenance text (Weekly OP kit, Store Championship, Release Event, "UK GAMES EXPO", Regional Championship). Every Mythos record shares its `(set,id)` `Card` grouping with the character it depicts (never inferred by name — the grouping key is `(set,id)`, and title/cardtype invariance was already confirmed catalogue-wide). Mythos records are `Printing`s of an existing `Card`, not separate `Card`s.

## 16. Mission analysis

30 `CardType="Mission"` records; 20 in Set 1 (10 `MSS 01`–`MSS 10` × 2 editions), 10 in Set 2 (single edition so far). Direct field-by-field comparison of every Set 1 Mission pair across editions (`Title`, `Text`, `Points`, `Group`): **identical in every case except `Order`** (a display/sort field, not gameplay content). `Chakra`/`Power` are absent (blank) for all 30 Mission records; `Points` is present. **Conclusion**: each edition reprint of a Mission is a legitimate, separate `Printing` (distinguished by `SKU`/`Uid`/`edition`) under one shared `Card`, with zero gameplay-content difference — exactly the same pattern validated for ordinary cards.

## 17. Attachment analysis

32 `CardType="Attachment"` records, Set 2 only (matches marketing exactly). `Rarity`: `UC` 17, `C` 15. `Points`: always blank (Attachments don't use this scoring field). `Variant`: `Holo` 31, `Full Art` 1 (anomaly, not invented-around). `Keyword1` populates category-like tags: `Weapon`(8), `Armor`(4), `Food`(3), `Scroll`(3), `Location`(3), etc. `Chakra`/`Power` are present (unlike Missions). No source field was found describing an "attach target" or slot — the current `Card`/`CardVariant` model does not lose any *exposed* Attachment-specific information, because the source itself exposes no additional Attachment-only field beyond what ordinary Character/Mission cards already have (`CardType="Attachment"` is itself sufficient to flag the semantics). No new field is invented here.

## 18. CHIBI/SP/Shinobi/POP analysis

Co-occurrence check — for every record in each of these four rarities, do other rarities appear at the *same* `(set,id)`? Answer: **overwhelmingly yes**:

| Rarity | Count | Co-occurring rarities at same (set,id) |
|---|---|---|
| `CHIBI` | 13 | L:4, UC:1, R:9, Shinobi:7, RA:9, SP:8, M:4, POP:3, S:3, SV:1 |
| `SP` | 11 | RA:9, Shinobi:6, R:9, CHIBI:9, M:6, POP:3, L:2, S:2, SV:1 |
| `Shinobi` | 10 | R:10, RA:10, CHIBI:7, SP:5, M:3, POP:1 |
| `POP` | 4 | RA:2, CHIBI:3, R:2, M:3, Shinobi:1, SP:3, S:2, SV:2, L:1 |

Almost every record in these four rarities shares its printed number with an ordinary `R`/`RA`/`L`/`S`/`M` sibling of the same title/card-type. **Classification: PRINTING CLASS (evidence-supported), living in the source's `Rarity` field.** These four values behave functionally like alternate-print treatments layered onto an existing `Card` (same pattern as `L`/`S`/`SV`), even though the source encodes them in `Rarity` rather than a separate treatment axis. The raw `Rarity` value is preserved verbatim regardless of this interpretation (`test_unknown_rarity_value_preserved_verbatim` demonstrates the general mechanism); no renaming/merging is performed.

## 19. Serialization

Per Phase 13A: POP = 4 catalogue designs (marketing: "300 individually serialized copies each"); Legendary = 7 catalogue designs (marketing: "unique, individually numbered" 22K gold). **No source field carries a serial-run count or per-copy identifier** — this is prose-only in the acquired sources. Consistent with the brief's instruction, no `is_serialized`/`serial_total`/etc. field was added to any model in this phase; the existing `CardVariant.serial_numbered`/`serial_total` columns (already present, unused by any real value observed) are structurally exactly what would be needed **if and when** a source ever exposes a structured count — until then, the print-run figures remain narrative evidence recorded in prose/report form only, not structured data.

## 20. Language

`language_invariance_check` compared `en` against `fr`/`it`/`es` for every shared `Uid` across identity-relevant fields (`id`, `set`, `edition`, `rarity`, `variant`, `sku`): **1908 pairs checked (636 × 3 language comparisons), 0 mismatches.** Image URLs, by contrast, **do** vary by language (391/636 differ between `en` and `fr` for the same `Uid` — confirmed directly, not assumed). 

**Recommendation**: localization belongs in a `PrintingTranslation`-style structure (or equivalent per-language content table) holding `Title`/`Version`/`Text`/`Obtain`/localized `Edition` label/`Image` URL, keyed by `(printing_id, language)`. `Printing`'s own canonical identity must **not** include `language` — confirmed both by direct evidence and by a passing test (`test_language_invariance_ignores_mutable_title_but_checks_identity_fields`, and its inverse `test_language_invariance_detects_real_identity_drift` proving the check would catch a genuine violation if one existed).

## 21. Provenance / distribution

`Obtain` (51/636 populated) and `Stamp` (19/636 populated) are inconsistent with each other: some Mythos records have descriptive `Obtain` text but a **blank** `Stamp` (e.g. Uid 307/316/525/361/371/372/751/752 in the residual-collision list, section 24), meaning `Stamp` alone under-counts distribution-channel cards. The SKU suffix (`-W`/`-SC`/`-RC`/`-RE`, section 6) is a **more complete** structured signal than `Stamp` for the records it applies to, but was not observed on all Obtain-bearing records either. **Conclusion: no fully consistent structured distribution model exists in the source today.** A normalized `distribution_type` field is plausible for the future (design only, not implemented) but must retain the raw `Obtain`/`Stamp`/`SKU` values as evidence rather than discarding them — several concrete inconsistencies (a typo "Relese Event Winner", blank-`Stamp`-but-descriptive-`Obtain` cases) would otherwise be silently lost.

## 22. Image-reference findings

- **Uniqueness**: 636/636 unique URLs in the `en` response (one per record).
- **Language-specific**: confirmed — 391/636 differ between `en` and `fr` for the same `Uid` (different filename hash and language segment, e.g. `.../000000-en-d0030a5b.webp` vs `.../000000-fr-b267acad.webp`).
- **Mutable-looking**: filenames embed a content hash suffix, suggesting the URL would change if the vendor re-rendered/replaced an image, independent of any catalogue metadata change.
- **Identity role**: confirmed **excluded** from canonical `Printing` identity — `CanonicalPrintingKey` has no `image` field at all, and `test_canonical_identity_excludes_image_url` proves two otherwise-identical records with different image URLs produce the identical canonical hash. Image URL is source metadata only (candidate home: a `PrintingImageReference`-style row or the existing `CardImage.source_url`-equivalent field), never identity.
- No image bytes were downloaded or inspected in this phase.

## 23. Proposed domain model

| Entity | Meaning | Identity | Mutable fields | Relationships | Source provenance |
|---|---|---|---|---|---|
| `Expansion` (existing `CardSet`) | One printed set/expansion, edition-unversioned | `(name)` | `printed_total`, etc. | has many `Card` | n/a |
| `Card` (existing `Card`) | Gameplay/design concept independent of print/treatment | `(expansion, printed_identifier)` | `name`(title), `card_type`, gameplay fields | belongs to `Expansion`; has many `Printing` | via `SourceRecord` |
| `Printing` (extended `CardVariant`) | One publisher catalogue print/treatment record | `(expansion, edition\|null, printed_identifier, rarity, variant\|null, source_uid)` | `rarity_override` semantics N/A (rarity is source-labeled, preserved), serialization flags | belongs to `Card` | `source_uid`/`source_sku` via `SourceRecord.external_id` |
| `PrintingTranslation` (new, or per-language content table) | Localized presentation content | `(printing_id, language)` | `title`, `version`, `text`, `obtain`, localized `edition` label, `image_url` | belongs to `Printing` | n/a |
| `Keyword` (existing) | Reusable tag | `slug` | `name` | many-to-many with `Card` | n/a |
| `PrintingImageReference` (existing `CardImage`, generalized) | Image URL reference only, never bytes | `(printing_id, language)` or existing PK | `url`, dimensions/attribution | belongs to `Printing` | `SourceRecord` |
| `SourceObservation` (existing `SourceRecord`) | Provenance/audit trail | existing PK | `content_hash`, timestamps | polymorphic reference to any entity | is itself the provenance mechanism |

This is presented as evidence-derived, not blindly adopted from the brief's suggested list — every entity above is justified by a specific finding in sections 5–22, and three of the seven (`Expansion`, `Card`/`Printing`, `Keyword`, `SourceObservation`) map onto **existing** models with little or no structural change.

## 24. Canonical Printing identity

Design (implemented as `CanonicalPrintingKey` in `importer/catalogue_design/identity.py`, analysis-only):

```
payload = {
  "version": 1,
  "kind": "PRINTING_ANALYSIS",
  "expansion": <source Set string>,
  "edition": <source Edition string, or null>,
  "printed_identifier": <source ID string>,
  "rarity": <source Rarity string, verbatim>,
  "variant": <source Variant string, or null>,
  "source_uid": <source Uid integer>,
}
identity_hash = SHA-256(NFC(sort_keys, compact-separator JSON(payload)))
```

Verified against every requirement in the brief:

- Distinguishes all 636 legitimate print records: **yes** (636/636 MAPPED, 0 collisions after including `source_uid`).
- Survives title corrections / localized text changes: **yes** — title and all localized fields are absent from the payload (`test_canonical_identity_excludes_mutable_title`).
- Does not depend on image URL: **yes** (`test_canonical_identity_excludes_image_url`).
- Does not depend on mutable rarity labels unless proven identity-bearing: rarity **is** included because evidence (section 7) shows it is necessary to resolve 178 of 185 `(set,id)` collisions; the raw label is preserved verbatim, never renamed.
- Preserves edition where identity-bearing, supports editionless promos: **yes**, `edition: None` is a first-class, tested value (`test_editionless_promo_is_mapped_not_rejected`).
- Preserves printed identifier and treatment/printing distinction: **yes**.
- Unicode: NFC-normalized before hashing (`test_unicode_nfc_normalization_makes_equivalent_forms_identical`).

**SKU decision**: external source key / fallback evidence only — not part of canonical identity (SKU already fully determined by the same semantic fields plus version suffix in 620/636 cases; including it would duplicate information already in the payload and would import the vendor's own versioning quirks, e.g. `V1`/`V2` reprint suffixes, into our identity).

**Uid decision (original, superseded by 24A)**: originally proposed as a mandatory tiebreaker component. Human review did not approve this — see section 24A for the revised, `source_uid`-free design.

## 24A. Identity closure review (human-review round)

Human reviewer did not approve `source_uid` as part of canonical semantic Printing identity. This section identifies every collision that remains when `source_uid` is removed, determines *why* each is distinct, evaluates `SKU` as an alternative, and proposes a revised design using only evidence-backed, publisher-assigned fields.

### 24A.1 Exact collision groups with source_uid removed

Removing `source_uid` from the key `(expansion, edition, printed_identifier, rarity, variant)` leaves **7 collision groups, 15 affected records** (unchanged from the original 628/636 finding, since that key never included `source_uid` in the first place). Full structural detail for every group (Text/Image compared only by equality and a 12-hex-character SHA-256 prefix — no rules text or artwork reproduced):

| Group | Set | Edition | ID | Rarity | Members (Uid / SKU / CardVersion / Stamp / Obtain / Order) | Text equal? | Image equal? |
|---|---|---|---|---|---|---|---|
| 1 | Konoha Shidō | *(blank)* | 104/130 | M | 307/`M104V1`/V1/`""`/"WEEKLY 2 OP KIT"/373 · 513/`M104V2-W`/V2/"Weekly Tournaments"/"Weekly OP"/374 | identical (hash `665f3e3fd9c2`) | differ |
| 2 | Konoha Shidō | *(blank)* | 107/130 | M | 523/`M107V1-W`/V1/"Weekly Tournaments"/"Weekly OP"/376 · 524/`M107V2-SC`/V2/"Store Championship"/"Store Championship Winner"/377 | identical (`04c6d33569c9`) | differ |
| 3 | Konoha Shidō | *(blank)* | 108/130 | M | 316/`M108V1`/V1/`""`/"WINNER CARD - WEEKLY 2 OP KIT"/379 · 525/`M108V2`/V2/`""`/`""`/380 · 405/`M108V2-SC`/V2/"Store Championship"/"Exclusive participation card…"/378 | **V1 differs** from the two V2 rows (`ecaaebffe88d` vs `ac50af15fb06`); the two V2 rows match each other | all three differ |
| 4 | Konoha Shidō | *(blank)* | 128/130 | M | 361/`M128V1`/V1/`""`/"RELEASE EVENT OP KIT"/387 · 568/`M128V2`/V2/"Weekly Tournaments"/"Weekly OP"/388 | identical (`c383f92a647e`) | differ |
| 5 | Konoha Shidō | *(blank)* | 133/130 | M | 371/`M133V1`/V1/`""`/"UK GAMES EXPO"/389 · 372/`M133V2`/V2/`""`/`""`/390 | identical (`959637d0a522`) | differ |
| 6 | Shinobi Shiren | 1st edition | 121/140 | SP | 751/`SP121V1`/V1/`""`/`""`/566 · 752/`SP121V2`/V2/`""`/`""`/567 | identical (`d7050a3ac660`) | differ |
| 7 | Shinobi Shiren | 1st edition | 126/140 | M | 859/`M126V2-RE`/V2/"Release Event"/"Relese Event Winner"[sic]/583 · 867/`M126V2-RC`/V2/"Regional Championship"/"Regional Championship 01 Top16"/584 | identical (`b2b943c56580`) | differ |

Every group is `Rarity ∈ {M, SP}` (Mythos or Special) — no ordinary Character/Mission/Attachment record collides once `source_uid` is removed at this key. `Image` differs in every single pairing (each print gets its own rendered art asset, even for otherwise-near-duplicate rows) — confirming again that Image carries no identity information either way.

### 24A.2 Why each group is distinct

| Group | Distinguishing source fields | Category |
|---|---|---|
| 1, 2, 4, 5, 6 | `CardVersion` (V1→V2), a unique flavor `Version` quote, a unique `Image`, and (for 1/2/4) `Obtain`/`Stamp` describing a specific giveaway event | **A — genuinely different collectible printings** (new art + new flavor line per version; some also tied to a specific distribution event, which is additional evidence, not the sole cause) |
| 3 | V1 vs V2 differ in `Text`/`Chakra`/`Power`/flavor `Version` (a real gameplay-content difference) — **and** the two V2 rows differ only by `Stamp`/`Obtain`/`Image`/`Order` | **Mixed**: V1-vs-V2 is category A; the two V2 rows are **category B — distribution variants of the same printing** |
| 7 | Identical `CardVersion` (`V2`); differ only by `Stamp` (`Release Event` vs `Regional Championship`), `Obtain` text, flavor `Version`, and `Image` | **B — distribution variants of the same printing** (same design, two different tournament-prize channels) |

No group is a duplicate catalogue record (C) or an unresolvable anomaly (D/E) — every one has at least one clean, non-prose, structural discriminator (`CardVersion` and/or `Stamp`).

`Obtain` was deliberately **not** chosen as a discriminator: it is freeform prose with observed data-quality defects (a typo, `"Relese Event Winner"`; inconsistent capitalization, `"WEEKLY 2 OP KIT"` vs `"Weekly OP"`) — unsuitable as an identity component even though it correlates with the same distinction. `Stamp` is a small, controlled vocabulary (`Weekly Tournaments`, `Store Championship`, `Release Event`, `Regional Championship`, or blank) and was chosen instead.

### 24A.3 SKU as source identity

- **Uniqueness across all 636**: confirmed unique (636/636), reconfirmed in this review.
- **Uniqueness inside every collision group**: yes — `SKU` already differs for every member of every one of the 7 groups (it encodes the same `CardVersion`/distribution suffix that resolves the collisions).
- **Stable semantic information**: yes, but only descriptively — `SKU` encodes set/edition/rarity/number/version/distribution-suffix in a recognizable but *not formally specified* grammar (620/636 match one shape, 16/636 — the Mythos promos — match a second, `E0`-sentinel shape). Treated as descriptive evidence only, per the brief's caution.
- **Malformed/duplicated**: none found; 0 nulls, 0 duplicates.
- **Stability across language responses**: **100% stable** — all 15 affected-group Uids were checked across `en`/`fr`/`it`/`es`; every `SKU` value is byte-identical in all four languages.
- **Conclusion**: `SKU` *could* mechanically resolve every one of the 7 groups (it's unique and stable), but it is **not** added to canonical semantic identity either, per the brief's explicit instruction not to do so automatically. It remains source/provenance evidence. The chosen discriminators (`CardVersion`, `Stamp`) were preferred because they are individually-meaningful, already-decomposed fields rather than substrings of an unspecified external string format.

### 24A.4 Revised design: semantic fingerprint / source identity / public ID

Three explicitly separate concepts, implemented in `importer/catalogue_design/identity.py`:

**SEMANTIC PRINTING FINGERPRINT** (`CanonicalPrintingKey`, revised) — a deterministic description of known collectible semantics, no opaque identifiers:

```
payload = {
  "version": 2,
  "kind": "PRINTING_SEMANTIC_FINGERPRINT",
  "expansion": <Set>,
  "edition": <Edition or null>,
  "printed_identifier": <ID>,
  "rarity": <Rarity, verbatim>,
  "variant": <Variant or null>,
  "card_version": <CardVersion or null>,
  "stamp": <Stamp or null>,
}
identity_hash = SHA-256(NFC(sort_keys, compact-separator JSON(payload)))
public_printing_id = "prn_" + identity_hash[:56]
```

Verified over all 636 real records (`importer.catalogue_design.run_analysis`): **636 unique fingerprints, 0 collisions**, with no `source_uid` or `SKU` anywhere in the payload.

**SOURCE RECORD IDENTITY** (`SourceIdentity`, new) — publisher-assigned evidence only, never hashed into identity:

```
SourceIdentity(source_uid: int | None, source_sku: str | None)
```

**PUBLIC PRINTING ID** — `public_printing_id = analysis_public_id()` of the semantic fingerprint, i.e. a pure function of collectible semantics. Assigned deterministically whenever the fingerprint is unambiguous (proven true for all 636 records).

**Registry design** (evaluated, not implemented):

```
PrintingIdentityRegistry
    semantic_fingerprint      -- CanonicalPrintingKey.identity_hash()
    public_printing_id        -- CanonicalPrintingKey.analysis_public_id()
    source_uid                -- SourceIdentity.source_uid (evidence)
    source_sku                -- SourceIdentity.source_sku (evidence)
    first_seen_source_hash    -- content hash of the raw record at first acquisition
```

The public ID is assigned from the semantic fingerprint alone. If a future source record's fingerprint collides with an existing one under a *different* `source_uid`, the correct behavior is `AMBIGUOUS` — a human-reviewed decision to approve a new discriminator (as happened here with `card_version`/`stamp`), never a silent fallback to incorporating `source_uid`.

### 24A.5 Source-Uid instability simulation

Simulated in `test_public_printing_id_stable_across_source_uid_change`: a record with `source_uid=100` and one with `source_uid=999`, identical in every semantic field (including `card_version`/`stamp`) — **the two produce the identical `public_printing_id`.** This is the desired stability property: a vendor-side Uid reassignment does not, by itself, change our public identity, because `source_uid` is not part of the hash at all.

Other simulated changes, classified:

| Simulated change | Identity-hash effect | Classification |
|---|---|---|
| Title correction | none (not in payload) | **KEEP SAME PRINTING** |
| Localized text (`Text`/`Version`/`Obtain`) correction | none (not in payload) | **KEEP SAME PRINTING** |
| Image URL change | none (not in payload) | **KEEP SAME PRINTING** |
| `SKU` change | none (not in payload — provenance only) | **KEEP SAME PRINTING** (logged as source-identity drift) |
| `source_uid` change (this simulation) | none (not in payload) | **KEEP SAME PRINTING** |
| Rarity label correction | **hash changes** (rarity is identity-bearing — section 7) | **REQUIRE REVIEW** — mechanically looks like a new printing; must be reconciled via matching `source_uid`/`source_sku` against a prior row before deciding merge vs. genuine new printing |
| Edition correction | **hash changes** (edition is identity-bearing — section 11) | **REQUIRE REVIEW**, same reconciliation logic as rarity |
| `card_version`/`stamp` correction | **hash changes** (both now identity-bearing, section 24A.4) | **REQUIRE REVIEW** |
| Genuinely new record: no `source_uid`/`source_sku` match to any known row | new hash, no prior evidence link | **CREATE NEW PRINTING** |

No production reconciliation/migration logic was implemented — this is a design classification only, backed by `test_rarity_correction_changes_identity_hash`, `test_edition_correction_changes_identity_hash`, `test_canonical_identity_excludes_sku`, and `test_public_printing_id_stable_across_source_uid_change`.

### 24A.6 Revised recommendation

The identity design is now **fully evidence-backed with zero opaque or random components**: `Card` = `(expansion, printed_identifier)`; `Printing` = `(expansion, edition, printed_identifier, rarity, variant, card_version, stamp)`; `source_uid`/`source_sku` = provenance evidence only, tracked separately. All 636 real records remain **636 MAPPED, 0 AMBIGUOUS, 0 REJECTED** under this revised design (re-verified via `importer.catalogue_design.run_analysis`), so no capability was lost by removing `source_uid` from the identity.

## 25. Public ID strategy

Evaluated continuing Phase 12B's deterministic strategy. Important reconciliation: Phase 12B's `importer/staging/identity.py` **already** defines a two-kind scheme — `"PRINTING"` (prefix `cpr_`, built from `scope` + `numbering_namespace` + `printed_identifier`) and `"TREATMENT"` (prefix `trt_`, built from a `parent_record_key` + `treatment_key`/`finish_key`/`collector_number`). Comparing structurally to this phase's real-data findings:

- Phase 12B's `"PRINTING"` kind (scope-and-number, no rarity) **structurally matches this phase's `Card` concept** (section 8) — both group by expansion+number without rarity.
- Phase 12B's `"TREATMENT"` kind (parent + treatment/finish/collector_number) **structurally matches this phase's `Printing` concept** (section 9) — both are the finer-grained, rarity/treatment-bearing child row.

The two designs are compatible in shape but **inverted in name**. Recommendation: the implementation phase should either (a) rename Phase 12B's kinds/prefixes (`PRINTING`→`CARD`/`crd_`, `TREATMENT`→`PRINTING`/`prn_`) to match this phase's terminology, or (b) keep Phase 12B's existing names and treat this phase's report as using `Card`/`Printing` purely as descriptive brief-terminology. Either is a naming-only decision; **do not introduce a third, competing prefix scheme.** The analysis code in this phase uses `exp_`/`crd_`/`prn_` prefixes strictly for isolated, clearly-labeled analysis output (`CanonicalExpansionKey`/`CanonicalCardKey`/`CanonicalPrintingKey.analysis_public_id()`), never written into production data.

One required extension either way: Phase 12B's `printing_identity()` function currently **raises on any `None` scope field** (`scope.edition`, `scope.language`) — real data requires `edition=None` to be valid (editionless promos) and `language` to be excluded from the identity-affecting scope entirely (section 20). This is a concrete, scoped code change for the implementation phase, not made here.

## 26. All-636 mapping results

Using `map_all_records` over all 636 `en` records, **re-verified after the identity-closure revision (section 24A, source_uid removed from the hash)**:

- **MAPPED: 636**
- **AMBIGUOUS: 0**
- **REJECTED: 0**

No record was silently dropped or merged (`MappingSummary.total == len(input)` always, enforced by construction and covered by `test_mapping_classifies_every_record_and_never_drops_one`). For every `MAPPED` record: unique `Printing` identity (verified — 636 distinct `analysis_public_id` values computed from the `source_uid`-free semantic fingerprint), source `Uid` and `SKU` retained as provenance, printed `ID` retained exactly, `edition` retained exactly or explicit `None`, `rarity`/`variant`/`card_version`/`stamp` retained, and full raw record retained for provenance (`preserved_fields` + `raw`).

The `AMBIGUOUS` and `REJECTED` code paths were validated with invented fixtures, since no real record triggers them: `test_mapping_detects_fingerprint_collision_across_different_uids` (general fingerprint collision, independent of `source_uid`), `test_mapping_detects_reused_uid_as_ambiguous_not_merged` (same-Uid variant), `test_mapping_classifies_every_record_and_never_drops_one` (missing required field → `REJECTED`).

## 27. Grouping validation

- Proposed **Cards: 318** — `(expansion, printed_identifier)` groups.
- Proposed **Printings: 636** — one per source record.
- Distribution of Printings per Card: 133 Cards with exactly 1 Printing; 185 Cards with 2+ Printings.
- **Maximum Printings per Card: 7** (e.g. `133/130`: L, SV, S ×2 editions, M ×2 distribution variants).
- **Ambiguous parent groups: 0** — every group is Title+CardType invariant (section 8).
- **Grouping rule**: `(expansion, printed_identifier)` equality, confirmed (never assumed) via Title/CardType invariance check over the full 636-record set.
- **Fields compared for the invariance proof**: `Title`, `CardType` (the two fields a name-only heuristic would risk getting wrong if inferred rather than checked).
- **Conflicts within grouped gameplay data**: none found.

## 28. Round-trip validation

For every `MAPPED` record, `round_trip_ok` verifies `Uid`, `SKU`, `ID`, `Set`, `Edition`, `CardType`, `Rarity`, `Variant`, `Langs` are recoverable, unmodified, from the analysis record: **636/636 pass.** Intentionally excluded fields from the normalized identity/preserved-set (still retained in `raw`, just not asserted individually in the round-trip check): `Title`, `Version`, `Text`, `Group`, `Chakra`, `Power`, `Points`, `Keyword1`, `Keyword2`, `Obtain`, `Stamp`, `Image`, `Order`, `Illustration`, `CardVersion` — all remain accessible via `MappingResult`'s underlying `SourceCardRecord.raw`, they are simply not part of the minimal round-trip assertion set named in the brief.

## 29. Compatibility with existing DB

| Existing model | Impact | Notes |
|---|---|---|
| `CardSet` | **KEEP** | One row per real `Set` value; no edition split needed (section 11) |
| `Card` | **KEEP** (constraint validated) | `UniqueConstraint(set_id, card_number)` is compatible **once** `card_number` = printed identifier and rarity/edition/variant stay off `Card` — resolves the Phase 13A "UNSUPPORTED" finding |
| `CardVariant` | **EXTEND** | Add a composite uniqueness constraint over `card_id, rarity_override, edition, collector_number` **plus `card_version`/`stamp`-equivalent columns** (section 24A); no rename required to be usable, though renaming to `Printing` is recommended for clarity (section 10) |
| `CardImage` | **KEEP** | Already URL/metadata-only, already supports optional `variant_id`; per-language image needs a `language` column or a `PrintingTranslation`-owned reference (design decision, not made here) |
| `Keyword` / `card_keywords` | **KEEP** | No change indicated by evidence |
| `SourceRecord` | **EXTEND (usage only)** | Reuse as the home for `source_uid`/`source_sku` via `entity_type="card_variants"`, `external_id`; no schema change needed, just population |
| New: per-language content (`PrintingTranslation` or equivalent) | **SPLIT / new entity** | Required by section 20's findings; does not exist today |
| New: `Points` (Mission/Attachment scoring) | **EXTEND** | No existing column on `Card`; needed if Mission/Attachment scoring is to be represented at all |

No entity requires **DEPRECATE** or **REPLACE** based on evidence gathered in this phase.

## 30. Compatibility with Phase 12

| Package | Classification | Notes |
|---|---|---|
| Phase 12B staging/identity | **MAJOR_EXTENSION** | Structurally compatible (section 25) but requires: (1) allow `scope.edition = None` as valid rather than "incomplete", (2) remove `scope.language` from identity-affecting fields, (3) reconcile `PRINTING`/`TREATMENT` naming with `Card`/`Printing` (section 25), (4) add `card_version`/`stamp`-equivalent discriminator fields to the `Treatment`/`Printing` identity (section 24A) -- **no opaque source id is required**, per the identity-closure revision |
| Phase 12C projection/planning | **MINOR_EXTENSION** | Projection logic itself doesn't hardcode edition-required or language-identity assumptions as far as reviewed; needs to correctly pass through the corrected Phase 12B identities once those change, and must not treat same-number/different-rarity siblings as a conflict |
| Phase 12D snapshot/execution | **MINOR_EXTENSION** | Same dependency chain as 12C; snapshot completeness/scope logic is generic over whatever entities are defined, but was designed against Phase 12B's original (pre-correction) identity assumptions and would need re-validation once 12B changes |

None of these packages were modified in this phase.

## 31. Future API impact

Design-only, no change made. Existing endpoints (`/v1/cards`, `/v1/cards/{public_id}`, `/v1/sets/{public_id}/cards`, `/v1/search`) can remain **backward compatible**: today's response shape already represents one `Card` with nested `variants`; the proposed model keeps that same shape, just fills `CardVariant`/`Printing` more completely (real `edition`, `rarity_override`, `collector_number`). Future clients would likely want additive, optional fields: `printing_id` (public id), `source_number` (printed identifier, if different from `card_number`), `edition`, `rarity`, `variant` — all of which fit as additional fields on the existing `CardVariant`/`Printing`-nested representation without breaking existing consumers. No endpoint needs to be removed or restructured based on this analysis.

## 32. PDF corroboration decision

**Not needed in this phase.** The first-party JSON API provided complete, structured, field-level evidence sufficient to resolve every identity question posed by the brief (sections 5–28) without ambiguity that only a PDF could resolve. `pypdf` was **not** added to any dependency file. If a future phase needs to corroborate serialization print-run counts or officially-printed collector numbering against the collection-guide PDFs (the only gaps identified — section 19), that would be a new, explicit, narrowly-scoped stop-and-report per the brief's section 32 process, not undertaken here.

## 33. Required schema changes (not implemented)

1. `CardVariant`: add a composite uniqueness constraint over the fields that make a printing distinct -- `card_id, rarity_override, edition, collector_number`, **plus a `card_version` and a `stamp` (or distribution-class) column** per the identity-closure revision (section 24A).
2. Populate `SourceRecord` rows for `card_variants` carrying `external_id = Uid` (and/or `SKU`) as **provenance only** -- never part of the uniqueness/identity key -- no new column required.
3. Add a per-language content structure (`PrintingTranslation` or equivalent) for `Title`/`Version`/`Text`/`Obtain`/localized `Edition` label/`Image` URL, keyed by `(printing_id, language)`.
4. Decide and add a `Points` field (Mission/Attachment scoring) — likely on `Card` (gameplay rule value) pending confirmation that it never varies by printing (not explicitly re-verified in this phase; flagged as an open item for the implementation phase).
5. Update Phase 12B's `printing_identity()`/`Scope` to accept `edition = None`, exclude `language` from identity, and add `card_version`/`stamp`-equivalent fields to the `Treatment` identity — see sections 24A/25.
6. Reconcile Phase 12B `PRINTING`/`TREATMENT` naming with this phase's `Card`/`Printing` terminology (naming-only).
7. Design (not implement) a `REQUIRE REVIEW` reconciliation workflow for rarity/edition/card_version/stamp corrections that change the identity hash but match a known `source_uid`/`source_sku` (section 24A.5) -- distinct from ordinary new-record creation.

None of these were created or migrated in this phase.

## 34. Tests/validation

New: `tests/test_catalogue_design.py` — 29 tests, all passing, using only small invented fixtures (a synthetic `"Test Set"`/`"001/999"` card family), never the real 636-record catalogue and never bulk copyrighted text. Covers: canonical identity determinism, identity excluding title/image/SKU/source_uid, identity requiring core fields, Card identity ignoring rarity/edition/variant, NFC normalization equivalence, Uid duplicate/null detection, SKU pattern-mismatch detection, collision-key resolution by rarity and by edition, Normal/Full-Art grouping, title-mismatch (non-silent) grouping, full-record mapping never dropping a record, fingerprint collision across different Uids (general case) and reused-Uid (specific case) → `AMBIGUOUS` (not merged), editionless promo → `MAPPED` (not rejected), unknown rarity preserved verbatim, deterministic repeated runs, round-trip pass/fail, language invariance (pass and deliberately-broken cases), **public-Printing-ID stability across a simulated `source_uid` change**, and **mechanical identity-hash change on rarity/edition correction** (the trigger for the `REQUIRE REVIEW` lifecycle classification).

Full-suite results: **671 passed**, 0 failed (642 baseline + 29 new). Ruff check: pass (0 errors, whole repo). Ruff format --check: pass, 132 files already formatted. Mypy (`app importer scripts`): pass, 0 issues, 83 source files. RapidAPI/OpenAPI regression (`test_rapidapi_export.py`, `test_rapidapi.py`, `test_openapi.py`): 54 passed. RapidAPI artifact SHA-256 verified unchanged: `9c76bca79d0056051dc2538e6b6b45382bb5275699d25e941fc82dbc5311d386`. OpenAPI: 12 paths, 12 GET operations.

## 35. Risks/limitations

- This design is based on a single point-in-time snapshot (2026-09-15/16); recurring acquisition would strengthen confidence that the 0-collision, 0-ambiguity result holds as the real catalogue grows (e.g. once Set 2 gets a 2nd edition, or Set 3 releases).
- `Points`' invariance across printings of the same `Card` was not explicitly re-verified in this phase (flagged in section 33 as an open item).
- The `Illustration` field is constant (`"Standard"`) in this snapshot; the proposed `finish` mapping is unexercised by real variation and could need revision once/if the source ever populates a different value.
- SKU grammar (both the ordinary and the promo forms) is descriptive, not contractual; a future vendor change could silently break any code that parses it, so it must remain evidence, never a validation gate.
- No corroboration against the printed collection-guide PDFs was performed (section 32) — the design is API-evidence-only.

## 36. Recommendation for implementation phase

**GO**, scoped exactly to the seven items in section 33, in this order: (1) Phase 12B identity-model correction (editionless + language exclusion + `card_version`/`stamp` discriminators + naming reconciliation), (2) `CardVariant` composite uniqueness constraint, (3) `SourceRecord` population convention for `Uid`/`SKU` (provenance only), (4) new per-language content structure, (5) `Points` field decision, (6) naming reconciliation, (7) `REQUIRE REVIEW` reconciliation workflow design, all followed by a real Alembic migration and importer/staging wiring — none of which is authorized by this phase.

---

## Final response summary

- **Proposed final domain architecture**: `Expansion` (existing `CardSet`, one row per Set, no edition split) → `Card` (existing `Card`, identity = `(expansion, printed_identifier)`) → `Printing` (extended `CardVariant`, identity = `(expansion, edition|null, printed_identifier, rarity, variant|null, card_version|null, stamp|null)` — **no `source_uid`**), plus a new per-language content structure and reuse of the existing `SourceRecord` table for source `Uid`/`SKU` provenance only.
- **Source identity decision (revised)**: `source_uid`/`SKU` = provenance/reconciliation evidence only, never canonical identity. `SKU` was confirmed capable of mechanically resolving all 7 residual collisions too, but was not adopted into identity either, per the brief's instruction.
- **Canonical Printing identity decision (revised)**: SHA-256 of NFC-normalized, sorted-key JSON over `{expansion, edition, printed_identifier, rarity, variant, card_version, stamp}` — see section 24A. Zero opaque/random components.
- **Card grouping decision**: `(expansion, printed_identifier)`, proven 100% Title/CardType-invariant over all 636 records — no name-only heuristic used; explicitly a snapshot-supported rule, not permanent law (section 8).
- **Edition decision**: nullable field on `Printing`, not an intermediate entity, not a `CardSet`-level split.
- **Rarity/treatment decision**: raw `Rarity` value always preserved verbatim; `CHIBI`/`SP`/`Shinobi`/`POP` classified as printing-class/alternate-treatment values based on strong co-occurrence evidence, without renaming the source label.
- **Localization decision**: presentation-only; new `PrintingTranslation`-style table keyed by `(printing_id, language)`; identity excludes language (proven with both a passing and a deliberately-failing test).
- **Number of raw records analyzed**: 636 (all four languages loaded; `en` used as the analysis reference; `en`/`fr`/`it`/`es` cross-checked for invariance).
- **MAPPED count**: 636. **AMBIGUOUS count**: 0. **REJECTED count**: 0.
- **Proposed Card count**: 318. **Printing count**: 636.
- **Collision results for candidate keys**: `set+id` 185 colliding; `set+edition+id` 103 colliding; `set+edition+id+rarity` 7 colliding (15 records); `+variant` no further change; **`+card_version` reduces to 2 colliding groups (4 records); `+stamp` reaches 0 colliding groups (636 unique) — all without `source_uid`.**
- **Unresolved identity collisions**: 0.
- **Round-trip result**: 636/636 pass.
- **Existing DB impact**: mostly KEEP; `CardVariant` EXTEND (uniqueness constraint, now including `card_version`/`stamp`); new per-language content entity; `SourceRecord` reused as provenance-only.
- **Phase 12 impact**: 12B MAJOR_EXTENSION (editionless + language-exclusion + `card_version`/`stamp` discriminators + naming reconciliation); 12C/12D MINOR_EXTENSION (pass-through once 12B changes).
- **Future API impact**: none required now; additive optional fields only, fully backward compatible.
- **Required schema changes**: seven items listed in section 33 — none implemented.
- **Tests/results**: 29 new tests, 671 total passing; Ruff/Mypy clean; RapidAPI artifact/paths/GETs unchanged.
- **Git status**: see below.
- **Recommendation: GO** for the implementation phase, scoped to section 33.

Real records analyzed: **636** (as expected)
New live acquisition performed: **NO**
Artwork downloaded/accessed: **NO**
Production DB accessed: **NO**
Production DB modified: **NO**
Migration created: **NO**
Public API modified: **NO**
Railway modified: **NO**
RapidAPI modified: **NO**
Deployment performed: **NO**
Commit created: **NO**
Push performed: **NO**

STOP. Implementation/migration phase not started.
