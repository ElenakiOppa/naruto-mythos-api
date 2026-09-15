# Offline projection API

`project(records, staging_policy, projection_policy, registry=None)` reruns Phase 12B
validation on the exact records. Its importer-compatible proposals are **sparse field
fragments**, with owner public IDs and explicit field operations beside them. They are
not full `ImportCatalogue` payloads and must never be passed to the old full-snapshot
writer. Creating such a payload now would reintroduce default-null updates.

`build_plan(records, staging_policy, projection_policy, snapshot, planning_policy,
registry=None, created_at=None)` performs an in-memory dry run. Supply a `Snapshot`;
there is no database adapter. The resulting `Plan` stores canonical content as an
immutable string. Reading `plan.content` returns a new parsed copy. `plan.plan_hash`
binds source records, evidence, rights, policies, registry snapshot, current-state
snapshot, field changes and all review outcomes. Generation time is outside the hash.

`verify_approval(plan, approval, snapshot=..., inputs=..., staging_policy=...,
projection_policy=..., planning_policy=..., registry=None)` checks the hash and all
current supplied context. It returns verification metadata only. No execute/apply
function exists. Approver identity is not authenticated and execution is always disabled.

Mapping rules are exposed in `projector.DIMENSIONS`. Each approved printing scope and
namespace maps one-to-one to a policy-supplied importer set. This is an explicit test
projection, not a decision to change the public expansion model. No territory mapping
is allowed. Mission fields, availability, extra rarity dimensions, images needing review
and unknown serialization are rejected rather than discarded. Evidence stays in the plan.

Snapshots use importer field names. Each entity has an owner public ID (except sets),
current field values and optional per-field last-imported value/source observations.
Missing baseline or current values block changed fields. Manual differences block even
when the new source agrees with the edited value. Revision ordering must be supplied
explicitly by source name; retrieval timestamps alone never establish a newer publisher
revision. Older retrievals or approved older revisions conflict. Equal values can remain
UNCHANGED without authorizing an overwrite.

ABSENT/UNKNOWN are SKIP. VALUE proposes CREATE/UPDATE/UNCHANGED. CLEAR keeps its review
reference and becomes a null clear (or an explicit empty keyword association list).
Clearing on a new entity is SKIP. An empty keyword VALUE cannot remove existing links
without an explicit CLEAR. A reference is not a verified human signature.

Conflicts and rejected records always block approval eligibility. Warnings block by
default; only codes explicitly listed in the planning policy are nonblocking. Fictional
fixtures explicitly allow their unsuitable-source and unknown-rights warnings solely
to exercise plan binding, never to authorize publication.

Future TOCTOU rule: read a complete authoritative current-state snapshot inside the
future execution transaction, hash it, compare with the approved snapshot hash, and
refuse on any difference. Locking/isolation must prevent changes between comparison and
write. This package neither reads that state nor performs any write.
