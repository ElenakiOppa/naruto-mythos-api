"""Add Edition collector snapshots and official Printing provenance.

Revision ID: g13c20260927
Revises: f13c20260926
"""

from __future__ import annotations

import hashlib
import json
import uuid

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import text

revision = "g13c20260927"
down_revision = "f13c20260926"
branch_labels = None
depends_on = None

WORKBOOK_SOURCE = "konoha_shido_1st_edition_master"
WORKBOOK_REFERENCE_COUNT = 396


def _identity_digest(edition_public_id: str, identities: list[dict[str, str]]) -> str:
    payload = {
        "edition_public_id": edition_public_id,
        "expected_printing_count": WORKBOOK_REFERENCE_COUNT,
        "identity_schema_version": "printing-reference-set-v1",
        "identities": sorted(identities, key=lambda item: item["reference_key"]),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _backfill_konoha_first_snapshot() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    edition = (
        bind.execute(
            text(
                "SELECT e.id, e.set_id, e.public_id FROM editions e "
                "JOIN sets s ON s.id = e.set_id "
                "WHERE s.name = :set_name AND e.normalized_name = :edition_name"
            ),
            {"set_name": "Set 1: Konoha Shidō", "edition_name": "1st edition"},
        )
        .mappings()
        .first()
    )
    if edition is None:
        return
    rows = (
        bind.execute(
            text(
                "SELECT pr.id, pr.reference_key, pr.source_sha256, cv.id AS printing_id, "
                "cv.public_id AS printing_public_id FROM printing_references pr "
                "JOIN card_variants cv ON cv.id = pr.printing_id "
                "WHERE cv.edition_id = :edition_id AND pr.source_name = :source_name"
            ),
            {"edition_id": edition["id"], "source_name": WORKBOOK_SOURCE},
        )
        .mappings()
        .all()
    )
    if not rows:
        return
    hashes = {row["source_sha256"] for row in rows}
    keys = [row["reference_key"] for row in rows]
    printing_ids = [row["printing_id"] for row in rows]
    if (
        len(rows) != WORKBOOK_REFERENCE_COUNT
        or len(hashes) != 1
        or len(set(keys)) != WORKBOOK_REFERENCE_COUNT
        or len(set(printing_ids)) != WORKBOOK_REFERENCE_COUNT
    ):
        raise RuntimeError("Cannot backfill snapshot: Konoha 1st reference set is incomplete")

    snapshot_id = uuid.uuid4()
    identities = []
    for row in rows:
        fingerprint = hashlib.sha256(row["printing_public_id"].encode("utf-8")).hexdigest()
        bind.execute(
            text(
                "UPDATE printing_references SET semantic_fingerprint = :fingerprint "
                "WHERE id = :reference_id"
            ),
            {"fingerprint": fingerprint, "reference_id": row["id"]},
        )
        identities.append(
            {
                "reference_key": row["reference_key"],
                "semantic_fingerprint": fingerprint,
                "printing_public_id": row["printing_public_id"],
            }
        )

    source_hash = next(iter(hashes))
    digest = _identity_digest(edition["public_id"], identities)
    bind.execute(
        text(
            "INSERT INTO edition_collector_snapshots "
            "(id, edition_id, set_id, source_type, source_url, transport_url, "
            "source_snapshot_sha256, retrieved_at, expected_printing_count, identity_digest, "
            "identity_schema_version, exhaustive, created_at, updated_at) "
            "VALUES (:id, :edition_id, :set_id, 'CURATED_WORKBOOK', "
            "'data/reference/konoha_shido_1st_edition_master.json', NULL, :source_hash, NULL, "
            ":expected_count, :identity_digest, 'printing-reference-set-v1', false, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {
            "id": snapshot_id,
            "edition_id": edition["id"],
            "set_id": edition["set_id"],
            "source_hash": source_hash,
            "expected_count": WORKBOOK_REFERENCE_COUNT,
            "identity_digest": digest,
        },
    )
    bind.execute(
        text(
            "UPDATE printing_references pr SET snapshot_id = :snapshot_id "
            "FROM card_variants cv WHERE cv.id = pr.printing_id "
            "AND cv.edition_id = :edition_id AND pr.source_name = :source_name"
        ),
        {
            "snapshot_id": snapshot_id,
            "edition_id": edition["id"],
            "source_name": WORKBOOK_SOURCE,
        },
    )


def upgrade() -> None:
    op.create_table(
        "edition_collector_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("edition_id", sa.Uuid(), nullable=False),
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("transport_url", sa.Text(), nullable=True),
        sa.Column("source_snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_printing_count", sa.Integer(), nullable=False),
        sa.Column("identity_digest", sa.String(length=64), nullable=False),
        sa.Column("identity_schema_version", sa.String(length=64), nullable=False),
        sa.Column("exhaustive", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "expected_printing_count > 0",
            name="ck_edition_collector_snapshots_expected_count_positive",
        ),
        sa.CheckConstraint(
            "length(source_snapshot_sha256) = 64 AND length(identity_digest) = 64",
            name="ck_edition_collector_snapshots_hash_lengths",
        ),
        sa.ForeignKeyConstraint(
            ["edition_id", "set_id"],
            ["editions.id", "editions.set_id"],
            name="fk_edition_collector_snapshots_edition_set",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "edition_id",
            "source_type",
            "source_snapshot_sha256",
            name="uq_edition_collector_snapshot_source_hash",
        ),
    )
    op.create_index(
        "ix_edition_collector_snapshots_edition_id", "edition_collector_snapshots", ["edition_id"]
    )
    op.add_column("printing_references", sa.Column("snapshot_id", sa.Uuid(), nullable=True))
    op.add_column(
        "printing_references", sa.Column("source_uid", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "printing_references", sa.Column("source_sku", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "printing_references",
        sa.Column("semantic_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column("printing_references", sa.Column("image_url", sa.Text(), nullable=True))
    op.alter_column(
        "printing_references", "worksheet", existing_type=sa.String(length=128), nullable=True
    )
    op.alter_column(
        "printing_references", "workbook_row", existing_type=sa.Integer(), nullable=True
    )
    op.drop_constraint(
        "ck_printing_references_workbook_row_positive", "printing_references", type_="check"
    )
    op.create_check_constraint(
        "ck_printing_references_workbook_row_positive",
        "printing_references",
        "workbook_row IS NULL OR workbook_row > 0",
    )
    op.create_foreign_key(
        "fk_printing_references_snapshot",
        "printing_references",
        "edition_collector_snapshots",
        ["snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_printing_references_snapshot_id", "printing_references", ["snapshot_id"])
    _backfill_konoha_first_snapshot()


def downgrade() -> None:
    if not context.is_offline_mode():
        bind = op.get_bind()
        snapshots = bind.execute(
            text("SELECT EXISTS (SELECT 1 FROM edition_collector_snapshots)")
        ).scalar_one()
        references = bind.execute(
            text("SELECT EXISTS (SELECT 1 FROM printing_references WHERE snapshot_id IS NOT NULL)")
        ).scalar_one()
        if snapshots or references:
            raise RuntimeError(
                "Unsafe downgrade: Edition collector verification provenance would be lost"
            )
    op.drop_index("ix_printing_references_snapshot_id", table_name="printing_references")
    op.drop_constraint("fk_printing_references_snapshot", "printing_references", type_="foreignkey")
    op.drop_constraint(
        "ck_printing_references_workbook_row_positive", "printing_references", type_="check"
    )
    op.create_check_constraint(
        "ck_printing_references_workbook_row_positive", "printing_references", "workbook_row > 0"
    )
    op.alter_column(
        "printing_references", "worksheet", existing_type=sa.String(length=128), nullable=False
    )
    op.alter_column(
        "printing_references", "workbook_row", existing_type=sa.Integer(), nullable=False
    )
    op.drop_column("printing_references", "semantic_fingerprint")
    op.drop_column("printing_references", "image_url")
    op.drop_column("printing_references", "source_sku")
    op.drop_column("printing_references", "source_uid")
    op.drop_column("printing_references", "snapshot_id")
    op.drop_index(
        "ix_edition_collector_snapshots_edition_id", table_name="edition_collector_snapshots"
    )
    op.drop_table("edition_collector_snapshots")
