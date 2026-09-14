"""Enforce variant image ownership with column-specific SET NULL.

Revision ID: 8b41e2a9c730
Revises: 5f360cfd2561
"""

from alembic import op

revision = "8b41e2a9c730"
down_revision = "5f360cfd2561"
branch_labels = None
depends_on = None


def upgrade():
    # Lock both sides before preflight to close the check/DDL writer race.
    # SQL preflight works for both online migration and offline SQL export.
    op.execute("LOCK TABLE card_variants, card_images IN SHARE ROW EXCLUSIVE MODE")
    op.execute("""
        DO $$
        DECLARE mismatch_count bigint;
        BEGIN
            SELECT count(*) INTO mismatch_count
            FROM card_images i JOIN card_variants v ON v.id = i.variant_id
            WHERE i.variant_id IS NOT NULL AND i.card_id <> v.card_id;
            IF mismatch_count > 0 THEN
                RAISE EXCEPTION 'Variant image ownership mismatch: % row(s); resolve explicitly before retrying migration.', mismatch_count;
            END IF;
        END $$
    """)
    op.create_unique_constraint("uq_card_variants_id_card_id", "card_variants", ["id", "card_id"])
    op.drop_constraint("fk_card_images_variant_id_card_variants", "card_images", type_="foreignkey")
    op.create_foreign_key(
        "fk_card_images_variant_card_owner",
        "card_images",
        "card_variants",
        ["variant_id", "card_id"],
        ["id", "card_id"],
        ondelete="SET NULL (variant_id)",
    )


def downgrade():
    op.drop_constraint("fk_card_images_variant_card_owner", "card_images", type_="foreignkey")
    op.create_foreign_key(
        "fk_card_images_variant_id_card_variants",
        "card_images",
        "card_variants",
        ["variant_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("uq_card_variants_id_card_id", "card_variants", type_="unique")
