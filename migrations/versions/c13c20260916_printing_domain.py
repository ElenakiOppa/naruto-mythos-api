"""Printing semantics and localized observations, without rewriting existing IDs.

Revision ID: c13c20260916
Revises: 8b41e2a9c730
"""

import sqlalchemy as sa
from alembic import op

revision = "c13c20260916"
down_revision = "8b41e2a9c730"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("LOCK TABLE cards, card_variants, source_records IN ACCESS EXCLUSIVE MODE")
    op.drop_constraint("ck_cards_power_non_negative", "cards", type_="check")
    op.add_column("cards", sa.Column("points", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_cards_points_non_negative", "cards", "points IS NULL OR points >= 0"
    )
    for name, length in (("source_variant", 64), ("card_version", 64), ("stamp", 255)):
        op.add_column("card_variants", sa.Column(name, sa.String(length), nullable=True))
    # No unreviewed inference from legacy normalized classification into raw identity.
    # Colliding existing rows abort the entire transaction, never merge or lose data.
    op.execute("""
        DO $$ BEGIN
            IF current_setting('server_version_num')::integer < 150000 THEN
                RAISE EXCEPTION 'Phase 13C requires PostgreSQL 15 or newer';
            END IF;
            IF EXISTS (SELECT 1 FROM card_variants
                GROUP BY card_id, normalize(edition), normalize(rarity_override),
                    normalize(source_variant), normalize(card_version), normalize(stamp)
                HAVING count(*) > 1) THEN
                RAISE EXCEPTION 'Legacy Printing identity is ambiguous; explicit reconciliation required';
            END IF;
        END $$
    """)
    op.execute("""CREATE UNIQUE INDEX uq_printing_semantic_identity ON card_variants
        (card_id, normalize(edition), normalize(rarity_override), normalize(source_variant),
         normalize(card_version), normalize(stamp)) NULLS NOT DISTINCT""")
    op.create_table(
        "printing_translations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "printing_id",
            sa.Uuid(),
            sa.ForeignKey("card_variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("subtitle", sa.String(255)),
        sa.Column("rules_text", sa.Text()),
        sa.Column("edition_label", sa.String(64)),
        sa.Column("distribution_text", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("printing_id", "language", name="uq_printing_translation_language"),
    )
    op.add_column("source_records", sa.Column("printing_id", sa.Uuid(), nullable=True))
    op.add_column("source_records", sa.Column("source_uid", sa.String(255), nullable=True))
    op.add_column("source_records", sa.Column("source_sku", sa.String(255), nullable=True))
    op.add_column("source_records", sa.Column("observation", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_source_records_printing_id_card_variants",
        "source_records",
        "card_variants",
        ["printing_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_source_records_printing_id", "source_records", ["printing_id"])
    op.create_check_constraint(
        "ck_source_printing_owner",
        "source_records",
        "printing_id IS NULL OR (entity_type = 'card_variants' AND entity_id = printing_id)",
    )


def downgrade():
    op.execute(
        "LOCK TABLE cards, card_variants, source_records, printing_translations IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM cards WHERE points IS NOT NULL OR power < 0)
            OR EXISTS (SELECT 1 FROM card_variants WHERE source_variant IS NOT NULL OR card_version IS NOT NULL OR stamp IS NOT NULL)
            OR EXISTS (SELECT 1 FROM printing_translations)
            OR EXISTS (SELECT 1 FROM source_records WHERE printing_id IS NOT NULL OR source_uid IS NOT NULL OR source_sku IS NOT NULL OR observation IS NOT NULL)
            THEN RAISE EXCEPTION 'Unsafe Phase 13C downgrade: new domain data requires explicit preservation';
            END IF;
        END $$
    """)
    op.drop_constraint("ck_source_printing_owner", "source_records", type_="check")
    op.drop_index("ix_source_records_printing_id", table_name="source_records")
    op.drop_constraint(
        "fk_source_records_printing_id_card_variants", "source_records", type_="foreignkey"
    )
    for name in ("observation", "source_sku", "source_uid", "printing_id"):
        op.drop_column("source_records", name)
    op.drop_table("printing_translations")
    op.drop_index("uq_printing_semantic_identity", table_name="card_variants")
    for name in ("stamp", "card_version", "source_variant"):
        op.drop_column("card_variants", name)
    op.drop_constraint("ck_cards_points_non_negative", "cards", type_="check")
    op.drop_column("cards", "points")

    op.create_check_constraint(
        "ck_cards_power_non_negative", "cards", "power IS NULL OR power >= 0"
    )
