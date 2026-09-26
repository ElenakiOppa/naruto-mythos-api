"""Add curated Printing references without rewriting upstream identities.

Revision ID: f13c20260926
Revises: e13c20260926
"""

import sqlalchemy as sa
from alembic import op

revision = "f13c20260926"
down_revision = "e13c20260926"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("LOCK TABLE card_variants IN ACCESS EXCLUSIVE MODE")
    op.add_column("card_variants", sa.Column("reference_identity", sa.String(64), nullable=True))
    op.drop_index("uq_printing_semantic_identity", table_name="card_variants")
    op.execute("""
        CREATE UNIQUE INDEX uq_printing_semantic_identity ON card_variants
        (card_id, edition_id, normalize(rarity_override), normalize(source_variant),
         normalize(card_version), normalize(stamp), normalize(reference_identity))
        NULLS NOT DISTINCT
    """)
    op.create_table(
        "printing_references",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("printing_id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("reference_key", sa.String(64), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("worksheet", sa.String(128), nullable=False),
        sa.Column("workbook_row", sa.Integer(), nullable=False),
        sa.Column("collector_number", sa.String(64), nullable=False),
        sa.Column("card_name", sa.String(255), nullable=False),
        sa.Column("rarity_raw", sa.String(64), nullable=False),
        sa.Column("variant_raw", sa.String(128), nullable=False),
        sa.Column("normalized_rarity", sa.String(64), nullable=True),
        sa.Column("collector_class", sa.String(64), nullable=True),
        sa.Column("normalized_treatment", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["printing_id"], ["card_variants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "source_name", "reference_key", name="uq_printing_reference_source_key"
        ),
        sa.UniqueConstraint(
            "printing_id", "source_name", "reference_key", name="uq_printing_reference_owner_key"
        ),
        sa.CheckConstraint("workbook_row > 0", name="ck_printing_references_workbook_row_positive"),
    )
    op.create_index("ix_printing_references_printing_id", "printing_references", ["printing_id"])


def downgrade():
    op.execute("LOCK TABLE printing_references, card_variants IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM printing_references)
            OR EXISTS (SELECT 1 FROM card_variants WHERE reference_identity IS NOT NULL)
            THEN
                RAISE EXCEPTION 'Unsafe curated-reference downgrade: reference identities would be lost';
            END IF;
        END $$
    """)
    op.drop_index("ix_printing_references_printing_id", table_name="printing_references")
    op.drop_table("printing_references")
    op.drop_index("uq_printing_semantic_identity", table_name="card_variants")
    op.drop_column("card_variants", "reference_identity")
    op.execute("""
        CREATE UNIQUE INDEX uq_printing_semantic_identity ON card_variants
        (card_id, edition_id, normalize(rarity_override), normalize(source_variant),
         normalize(card_version), normalize(stamp)) NULLS NOT DISTINCT
    """)
