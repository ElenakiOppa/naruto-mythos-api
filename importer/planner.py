"""Read-only batched comparison. Planning never inserts, updates, deletes, or flushes."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC

from pydantic import AnyUrl
from sqlalchemy import select

from app.models import Card, CardImage, CardSet, CardVariant, Keyword, SourceRecord
from app.models.keyword import card_keywords
from importer.hashing import canonical_hash

TABLES = {
    "sets": CardSet.__table__,
    "cards": Card.__table__,
    "variants": CardVariant.__table__,
    "keywords": Keyword.__table__,
    "images": CardImage.__table__,
    "provenance": SourceRecord.__table__,
}
TYPES = {
    "sets": "set",
    "cards": "card",
    "variants": "variant",
    "keywords": "keyword",
    "images": "image",
}


class ImportConflict(ValueError):
    """Safe user-facing preflight error."""


def chunks(values, size=400):
    values = list(values)
    for index in range(0, len(values), size):
        yield values[index : index + size]


def fetch(connection, table, column, values):
    rows = {}
    for batch in chunks(sorted(set(values), key=str)):
        for row in connection.execute(select(table).where(column.in_(batch))).mappings():
            rows[row["id"]] = dict(row)
    return list(rows.values())


def fields(model, exclude=(), aliases=None):
    return {
        (aliases or {}).get(key, key): str(value) if isinstance(value, AnyUrl) else value
        for key, value in model.model_dump(exclude=set(exclude)).items()
    }


@dataclass
class Record:
    kind: str
    key: str
    attrs: dict
    semantic: dict
    owner: tuple | None = None
    row: dict | None = None
    internal_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Plan:
    changes: dict
    records: list
    inserts: dict
    updates: dict
    links_created: list
    links_removed: list
    normalizations: list


def build_plan(connection, catalogue):
    changes = {
        kind: {action: [] for action in ("created", "updated", "unchanged")} for kind in TABLES
    }
    changes["relationships"] = {action: [] for action in ("created", "removed", "unchanged")}
    records = []
    bykey = {}
    card_inputs = {}
    normalizations = []

    def add(kind, key, attrs, owner=None):
        rec = Record(kind, key, attrs, dict(attrs), owner)
        rec.semantic["owner"] = owner
        records.append(rec)
        bykey[kind, key] = rec
        return rec

    keyword_defs = {}
    for st in sorted(catalogue.sets, key=lambda x: x.id):
        add("sets", st.id, fields(st, ("cards",), {"id": "public_id"}))
        for card in sorted(st.cards, key=lambda x: x.id):
            card_inputs[card.id] = card
            add(
                "cards",
                card.id,
                fields(
                    card,
                    ("keywords", "variants", "images"),
                    {"id": "public_id", "number": "card_number", "type": "card_type"},
                ),
                ("sets", st.id),
            )
            for keyword in card.keywords or []:
                keyword_defs[keyword.slug] = keyword
            for v in sorted(card.variants, key=lambda x: x.id):
                attrs = fields(
                    v,
                    ("images",),
                    {"id": "public_id", "type": "variant_type", "rarity": "rarity_override"},
                )
                normalized = catalogue.variant_aliases.get(v.type, v.type)
                if normalized != v.type:
                    normalizations.append(
                        {"variant": v.id, "original": v.type, "normalized": normalized}
                    )
                attrs["variant_type"] = normalized
                add("variants", v.id, attrs, ("cards", card.id))
            owners = [(None, card.images)] + [(v.id, v.images) for v in card.variants]
            for variant_id, images in owners:
                for image in images:
                    identity = {
                        "card": card.id,
                        "variant": variant_id,
                        "type": image.type,
                        "url": str(image.url),
                    }
                    key = "image:" + canonical_hash(identity)
                    attrs = fields(image, aliases={"type": "image_type"})
                    attrs["hosted_by_us"] = False
                    add("images", key, attrs, (card.id, variant_id))
    for slug, keyword in sorted(keyword_defs.items()):
        add("keywords", slug, fields(keyword))
    records.sort(key=lambda x: (list(TABLES).index(x.kind), x.key))
    existing = {}
    for kind in ("sets", "cards", "variants", "keywords"):
        table = TABLES[kind]
        column = table.c.slug if kind == "keywords" else table.c.public_id
        existing[kind] = fetch(
            connection, table, column, [r.key for r in records if r.kind == kind]
        )
        lookup = {r["slug" if kind == "keywords" else "public_id"]: r for r in existing[kind]}
        for rec in (r for r in records if r.kind == kind):
            rec.row = lookup.get(rec.key)
            if rec.row:
                rec.internal_id = rec.row["id"]
    card_ids = [r.internal_id for r in records if r.kind == "cards" and r.row]
    existing["images"] = fetch(connection, TABLES["images"], TABLES["images"].c.card_id, card_ids)
    image_lookup = {}
    for row in existing["images"]:
        key = (row["card_id"], row["variant_id"], row["image_type"], row["url"])
        image_lookup.setdefault(key, []).append(row)
    for rec in records:
        if rec.kind == "cards":
            rec.attrs["set_id"] = bykey[rec.owner].internal_id
            if rec.row and rec.row["set_id"] != rec.attrs["set_id"]:
                raise ImportConflict(f"Card cannot be moved to another set: {rec.key}")
        elif rec.kind == "variants":
            rec.attrs["card_id"] = bykey[rec.owner].internal_id
            if rec.row and rec.row["card_id"] != rec.attrs["card_id"]:
                raise ImportConflict(f"Variant cannot be moved to another card: {rec.key}")
        elif rec.kind == "images":
            card, variant = rec.owner
            rec.attrs["card_id"] = bykey["cards", card].internal_id
            rec.attrs["variant_id"] = bykey["variants", variant].internal_id if variant else None
            candidates = image_lookup.get(
                (
                    rec.attrs["card_id"],
                    rec.attrs["variant_id"],
                    rec.attrs["image_type"],
                    rec.attrs["url"],
                ),
                [],
            )
            if len(candidates) > 1:
                raise ImportConflict("Ambiguous pre-existing duplicate image identity")
            rec.row = candidates[0] if candidates else None
            if rec.row:
                rec.internal_id = rec.row["id"]
    # Detect DB number collisions, including records omitted from the import.
    sets = [r.internal_id for r in records if r.kind == "sets" and r.row]
    occupied = {
        (row["set_id"], row["card_number"]): row["public_id"]
        for row in fetch(connection, TABLES["cards"], TABLES["cards"].c.set_id, sets)
    }
    for rec in (r for r in records if r.kind == "cards"):
        conflict = occupied.get((rec.attrs["set_id"], rec.attrs["card_number"]))
        if conflict is not None and conflict != rec.key:
            raise ImportConflict(f"Card number already occupied in set: {rec.key}")
    associations = {}
    for batch in chunks(card_ids):
        rows = connection.execute(
            select(card_keywords.c.card_id, card_keywords.c.keyword_id, Keyword.slug)
            .join(Keyword, Keyword.id == card_keywords.c.keyword_id)
            .where(card_keywords.c.card_id.in_(batch))
        )
        for card, keyword, slug in rows:
            associations.setdefault(card, {})[slug] = keyword
    created_links = []
    removed_links = []
    for rec in (r for r in records if r.kind == "cards"):
        old = associations.get(rec.internal_id, {})
        supplied = card_inputs[rec.key].keywords
        desired = set(old) if supplied is None else {kw.slug for kw in supplied}
        rec.semantic["keywords"] = sorted(desired)
        for slug in sorted(desired - set(old)):
            created_links.append(
                {"card_id": rec.internal_id, "keyword_id": bykey["keywords", slug].internal_id}
            )
            changes["relationships"]["created"].append(rec.key + " -> " + slug)
        for slug in sorted(set(old) - desired):
            removed_links.append({"card_id": rec.internal_id, "keyword_id": old[slug]})
            changes["relationships"]["removed"].append(rec.key + " -> " + slug)
        for slug in sorted(desired & set(old)):
            changes["relationships"]["unchanged"].append(rec.key + " -> " + slug)
    provenance = {}
    rows = fetch(
        connection,
        TABLES["provenance"],
        TABLES["provenance"].c.entity_id,
        [r.internal_id for r in records if r.row],
    )
    for row in rows:
        if row["source_name"] != catalogue.source.name:
            continue
        key = (row["entity_type"], row["entity_id"])
        if key in provenance:
            raise ImportConflict("Ambiguous existing provenance for entity/source")
        provenance[key] = row
    inserts = {k: [] for k in TABLES}
    updates = {k: [] for k in TABLES}

    def classify(kind, key, row, attrs, internal_id):
        action = (
            "created"
            if row is None
            else "updated"
            if any(row[k] != v for k, v in attrs.items())
            else "unchanged"
        )
        changes[kind][action].append(key)
        if action == "created":
            inserts[kind].append(dict(attrs, id=internal_id))
        elif action == "updated":
            updates[kind].append(dict(attrs, _pk=internal_id))

    def utc(value):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    for rec in records:
        classify(rec.kind, rec.key, rec.row, rec.attrs, rec.internal_id)
        prior = provenance.get((TYPES[rec.kind], rec.internal_id))
        seen = utc(catalogue.source.retrieved_at)
        attrs = {
            "entity_type": TYPES[rec.kind],
            "entity_id": rec.internal_id,
            "source_name": catalogue.source.name,
            "source_url": str(catalogue.source.url) if catalogue.source.url else None,
            "external_id": rec.key,
            "content_hash": canonical_hash(rec.semantic),
            "first_seen_at": utc(prior["first_seen_at"]) if prior else seen,
            "last_seen_at": max(utc(prior["last_seen_at"]), seen) if prior else seen,
        }
        if prior:
            prior = dict(
                prior,
                first_seen_at=utc(prior["first_seen_at"]),
                last_seen_at=utc(prior["last_seen_at"]),
            )
        classify(
            "provenance",
            TYPES[rec.kind] + ":" + rec.key,
            prior,
            attrs,
            prior["id"] if prior else uuid.uuid4(),
        )
    for group in changes.values():
        for values in group.values():
            values.sort()
    return Plan(changes, records, inserts, updates, created_links, removed_links, normalizations)
