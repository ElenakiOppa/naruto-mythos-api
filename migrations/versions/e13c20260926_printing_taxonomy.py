"""Add non-identity normalized taxonomy fields to Printings.

Revision ID: e13c20260926
Revises: d13c20260926
"""

import sqlalchemy as sa
from alembic import op

revision = "e13c20260926"
down_revision = "d13c20260926"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("LOCK TABLE cards, card_variants IN ACCESS EXCLUSIVE MODE")
    op.add_column("card_variants", sa.Column("normalized_rarity", sa.String(64), nullable=True))
    op.add_column("card_variants", sa.Column("collector_class", sa.String(64), nullable=True))
    op.add_column("card_variants", sa.Column("normalized_treatment", sa.String(64), nullable=True))
    op.add_column(
        "card_variants", sa.Column("rarity_resolution_status", sa.String(16), nullable=True)
    )
    op.add_column(
        "card_variants", sa.Column("variant_resolution_status", sa.String(16), nullable=True)
    )

    op.execute("""
        UPDATE card_variants AS printing
        SET normalized_rarity = CASE printing.rarity_override
                WHEN 'C' THEN 'Common'
                WHEN 'Common' THEN 'Common'
                WHEN 'UC' THEN 'Uncommon'
                WHEN 'Uncommon' THEN 'Uncommon'
                WHEN 'R' THEN 'Rare'
                WHEN 'Rare' THEN 'Rare'
                WHEN 'RA' THEN 'Rare ART'
                WHEN 'Rare ART' THEN 'Rare ART'
                WHEN 'S' THEN 'Secret'
                WHEN 'Secret' THEN 'Secret'
                WHEN 'SV' THEN 'Secret Variant'
                WHEN 'Secret Variant' THEN 'Secret Variant'
                WHEN 'L' THEN 'Legendary'
                WHEN 'Legendary' THEN 'Legendary'
                WHEN 'M' THEN 'Mythos'
                WHEN 'Mythos' THEN 'Mythos'
                ELSE NULL
            END,
            collector_class = CASE
                WHEN printing.rarity_override = 'Mission' AND cards.card_type = 'Mission'
                    THEN 'Mission'
                ELSE NULL
            END,
            rarity_resolution_status = CASE
                WHEN printing.rarity_override IN (
                    'C', 'Common', 'UC', 'Uncommon', 'R', 'Rare', 'RA', 'Rare ART',
                    'S', 'Secret', 'SV', 'Secret Variant', 'L', 'Legendary', 'M', 'Mythos'
                ) THEN 'MAPPED'
                WHEN printing.rarity_override = 'Mission' AND cards.card_type = 'Mission'
                    THEN 'MAPPED'
                ELSE 'UNRESOLVED'
            END,
            normalized_treatment = CASE printing.source_variant
                WHEN 'Normal' THEN 'Normal'
                WHEN 'Full Art' THEN 'FullArt'
                WHEN 'FullArt' THEN 'FullArt'
                WHEN 'Holo' THEN 'Holographic'
                WHEN 'Holographic' THEN 'Holographic'
                WHEN 'Gold' THEN 'Gold'
                ELSE NULL
            END,
            variant_resolution_status = CASE
                WHEN printing.source_variant IS NULL OR printing.source_variant = ''
                    THEN 'UNSPECIFIED'
                WHEN printing.source_variant IN (
                    'Normal', 'Full Art', 'FullArt', 'Holo', 'Holographic', 'Gold'
                ) THEN 'MAPPED'
                ELSE 'UNRESOLVED'
            END
        FROM cards
        WHERE cards.id = printing.card_id
    """)

    op.alter_column(
        "card_variants",
        "rarity_resolution_status",
        existing_type=sa.String(16),
        nullable=False,
        server_default="UNRESOLVED",
    )
    op.alter_column(
        "card_variants",
        "variant_resolution_status",
        existing_type=sa.String(16),
        nullable=False,
        server_default="UNSPECIFIED",
    )
    op.alter_column(
        "card_variants",
        "serial_numbered",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )
    op.create_check_constraint(
        "ck_card_variants_rarity_resolution_status",
        "card_variants",
        "rarity_resolution_status IN ('MAPPED', 'UNRESOLVED')",
    )
    op.create_check_constraint(
        "ck_card_variants_variant_resolution_status",
        "card_variants",
        "variant_resolution_status IN ('MAPPED', 'UNSPECIFIED', 'UNRESOLVED')",
    )


def downgrade():
    op.execute("LOCK TABLE card_variants IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM card_variants
                WHERE normalized_rarity IS NOT NULL
                   OR collector_class IS NOT NULL
                   OR normalized_treatment IS NOT NULL
                         OR rarity_resolution_status <> 'UNRESOLVED'
                         OR variant_resolution_status <> 'UNSPECIFIED'
                   OR serial_numbered IS NULL
            ) THEN
                RAISE EXCEPTION 'Unsafe taxonomy downgrade: normalized or unknown-serial data would be lost';
            END IF;
        END $$
    """)
    op.drop_constraint("ck_card_variants_variant_resolution_status", "card_variants", type_="check")
    op.drop_constraint("ck_card_variants_rarity_resolution_status", "card_variants", type_="check")
    op.alter_column(
        "card_variants",
        "serial_numbered",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )
    for column in (
        "variant_resolution_status",
        "rarity_resolution_status",
        "normalized_treatment",
        "collector_class",
        "normalized_rarity",
    ):
        op.drop_column("card_variants", column)
