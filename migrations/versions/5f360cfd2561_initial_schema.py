"""initial schema: sets, cards, card_variants, keywords, card_keywords, card_images, source_records

Revision ID: 5f360cfd2561
Revises:
Create Date: 2026-09-13 00:00:00.000000

This migration was hand-written to match app/models/*.py exactly, rather
than trusted blindly from `alembic revision --autogenerate` output, per
project policy. It was reviewed column-by-column against the models before
being committed. See PHASE_2_REPORT.md for why it could not be executed
against a live PostgreSQL instance in the environment this was authored in,
and the exact commands to run it against a real development database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f360cfd2561"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- sets -----------------------------------------------------------
    op.create_table(
        "sets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("edition", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="EN"),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("printed_total", sa.Integer(), nullable=True),
        sa.Column("total_with_variants", sa.Integer(), nullable=True),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("symbol_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "printed_total IS NULL OR printed_total >= 0",
            name="ck_sets_printed_total_non_negative",
        ),
        sa.CheckConstraint(
            "total_with_variants IS NULL OR total_with_variants >= 0",
            name="ck_sets_total_with_variants_non_negative",
        ),
    )
    # public_id is unique AND indexed via a single unique index (matching the
    # model's `Column(..., unique=True, index=True)`), not a separate unique
    # constraint plus a separate plain index -- that would create two
    # redundant index structures over the same column.
    op.create_index("ix_sets_public_id", "sets", ["public_id"], unique=True)
    op.create_index("ix_sets_code", "sets", ["code"])
    op.create_index("ix_sets_name", "sets", ["name"])

    # -- keywords ---------------------------------------------------------
    op.create_table(
        "keywords",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_keywords_slug", "keywords", ["slug"], unique=True)

    # -- cards --------------------------------------------------------------
    op.create_table(
        "cards",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("set_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("card_number", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("subtitle", sa.String(length=255), nullable=True),
        sa.Column("card_type", sa.String(length=64), nullable=True),
        sa.Column("rarity", sa.String(length=64), nullable=True),
        sa.Column("chakra", sa.Integer(), nullable=True),
        sa.Column("power", sa.Integer(), nullable=True),
        sa.Column("faction", sa.String(length=64), nullable=True),
        sa.Column("ability_text", sa.Text(), nullable=True),
        sa.Column("flavor_text", sa.Text(), nullable=True),
        sa.Column("artist", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["set_id"], ["sets.id"], name="fk_cards_set_id_sets", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("set_id", "card_number", name="uq_cards_set_id_card_number"),
        sa.CheckConstraint("chakra IS NULL OR chakra >= 0", name="ck_cards_chakra_non_negative"),
        sa.CheckConstraint("power IS NULL OR power >= 0", name="ck_cards_power_non_negative"),
    )
    op.create_index("ix_cards_public_id", "cards", ["public_id"], unique=True)
    op.create_index("ix_cards_set_id", "cards", ["set_id"])
    op.create_index("ix_cards_card_number", "cards", ["card_number"])
    op.create_index("ix_cards_name", "cards", ["name"])
    op.create_index("ix_cards_card_type", "cards", ["card_type"])
    op.create_index("ix_cards_rarity", "cards", ["rarity"])

    # -- card_variants --------------------------------------------------
    op.create_table(
        "card_variants",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("card_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("variant_type", sa.String(length=64), nullable=False),
        sa.Column("finish", sa.String(length=64), nullable=True),
        sa.Column("rarity_override", sa.String(length=64), nullable=True),
        sa.Column("collector_number", sa.String(length=32), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="EN"),
        sa.Column("edition", sa.String(length=64), nullable=True),
        sa.Column("serial_numbered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("serial_total", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["cards.id"], name="fk_card_variants_card_id_cards", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "serial_total IS NULL OR serial_total > 0",
            name="ck_card_variants_serial_total_positive",
        ),
    )
    op.create_index("ix_card_variants_public_id", "card_variants", ["public_id"], unique=True)
    op.create_index("ix_card_variants_card_id", "card_variants", ["card_id"])
    op.create_index("ix_card_variants_variant_type", "card_variants", ["variant_type"])

    # -- card_images ----------------------------------------------------
    op.create_table(
        "card_images",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("card_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("variant_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("image_type", sa.String(length=32), nullable=False, server_default="front"),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("hosted_by_us", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["cards.id"], name="fk_card_images_card_id_cards", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["card_variants.id"],
            name="fk_card_images_variant_id_card_variants",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("width IS NULL OR width > 0", name="ck_card_images_width_positive"),
        sa.CheckConstraint("height IS NULL OR height > 0", name="ck_card_images_height_positive"),
    )
    op.create_index("ix_card_images_card_id", "card_images", ["card_id"])
    op.create_index("ix_card_images_variant_id", "card_images", ["variant_id"])

    # -- card_keywords (association table) -------------------------------
    op.create_table(
        "card_keywords",
        sa.Column("card_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("keyword_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["card_id"], ["cards.id"], name="fk_card_keywords_card_id_cards", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name="fk_card_keywords_keyword_id_keywords",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("card_id", "keyword_id", name="pk_card_keywords"),
    )

    # -- source_records -----------------------------------------------
    op.create_table(
        "source_records",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # No ForeignKeyConstraint on entity_id: source_records references
        # rows across multiple different tables depending on entity_type.
        # See app/models/source.py docstring for the full rationale.
    )
    op.create_index("ix_source_records_source_name", "source_records", ["source_name"])
    op.create_index(
        "ix_source_records_entity_type_entity_id", "source_records", ["entity_type", "entity_id"]
    )
    op.create_index(
        "ix_source_records_source_name_external_id",
        "source_records",
        ["source_name", "external_id"],
    )


def downgrade() -> None:
    # Reverse dependency order relative to upgrade().
    op.drop_index("ix_source_records_source_name_external_id", table_name="source_records")
    op.drop_index("ix_source_records_entity_type_entity_id", table_name="source_records")
    op.drop_index("ix_source_records_source_name", table_name="source_records")
    op.drop_table("source_records")

    op.drop_table("card_keywords")

    op.drop_index("ix_card_images_variant_id", table_name="card_images")
    op.drop_index("ix_card_images_card_id", table_name="card_images")
    op.drop_table("card_images")

    op.drop_index("ix_card_variants_variant_type", table_name="card_variants")
    op.drop_index("ix_card_variants_card_id", table_name="card_variants")
    op.drop_index("ix_card_variants_public_id", table_name="card_variants")
    op.drop_table("card_variants")

    op.drop_index("ix_cards_rarity", table_name="cards")
    op.drop_index("ix_cards_card_type", table_name="cards")
    op.drop_index("ix_cards_name", table_name="cards")
    op.drop_index("ix_cards_card_number", table_name="cards")
    op.drop_index("ix_cards_set_id", table_name="cards")
    op.drop_index("ix_cards_public_id", table_name="cards")
    op.drop_table("cards")

    op.drop_index("ix_keywords_slug", table_name="keywords")
    op.drop_table("keywords")

    op.drop_index("ix_sets_name", table_name="sets")
    op.drop_index("ix_sets_code", table_name="sets")
    op.drop_index("ix_sets_public_id", table_name="sets")
    op.drop_table("sets")
