"""Add Set-scoped Editions and Printing ownership constraints.

Revision ID: d13c20260926
Revises: c13c20260916
"""

import sqlalchemy as sa
from alembic import op

revision = "d13c20260926"
down_revision = "c13c20260916"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("LOCK TABLE sets, cards, card_variants IN ACCESS EXCLUSIVE MODE")
    op.create_table(
        "editions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("set_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("normalized_name", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["set_id"], ["sets.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_editions_name_nonblank"),
        sa.CheckConstraint(
            "normalized_name = lower(normalize(regexp_replace(btrim(name), E'\\\\s+', ' ', 'g'), NFC))",
            name="ck_editions_normalized_name",
        ),
        sa.UniqueConstraint("set_id", "normalized_name", name="uq_editions_set_normalized_name"),
        sa.UniqueConstraint("id", "set_id", name="uq_editions_id_set_id"),
    )
    op.create_index("ix_editions_public_id", "editions", ["public_id"], unique=True)
    op.create_index("ix_editions_set_id", "editions", ["set_id"])
    op.create_unique_constraint("uq_cards_id_set_id", "cards", ["id", "set_id"])
    op.add_column("card_variants", sa.Column("set_id", sa.Uuid(), nullable=True))
    op.add_column("card_variants", sa.Column("edition_id", sa.Uuid(), nullable=True))

    op.execute(r"""
        WITH normalized AS (
            SELECT c.set_id,
                   regexp_replace(btrim(v.edition), E'\\s+', ' ', 'g') AS clean_name,
                   lower(normalize(
                       regexp_replace(btrim(v.edition), E'\\s+', ' ', 'g'), NFC
                   )) AS normalized_name
            FROM card_variants v
            JOIN cards c ON c.id = v.card_id
            WHERE v.edition IS NOT NULL AND btrim(v.edition) <> ''
        ), grouped AS (
            SELECT set_id, normalized_name,
                   CASE normalized_name
                       WHEN '1st edition' THEN '1st Edition'
                       WHEN '2nd edition' THEN '2nd Edition'
                       ELSE min(clean_name)
                   END AS name
            FROM normalized
            GROUP BY set_id, normalized_name
        )
         INSERT INTO editions (id, public_id, set_id, name, normalized_name)
         SELECT gen_random_uuid(),
             'edn_' || md5(length(s.public_id)::text || ':' || s.public_id || g.normalized_name),
             g.set_id, g.name, g.normalized_name
         FROM grouped g
         JOIN sets s ON s.id = g.set_id
    """)
    op.execute("""
        UPDATE card_variants v
        SET set_id = c.set_id
        FROM cards c
        WHERE c.id = v.card_id
    """)
    op.execute(r"""
        UPDATE card_variants v
        SET edition_id = e.id
        FROM cards c, editions e
        WHERE c.id = v.card_id
          AND e.set_id = c.set_id
          AND e.normalized_name = lower(normalize(
              regexp_replace(btrim(v.edition), E'\\s+', ' ', 'g'), NFC
          ))
          AND v.edition IS NOT NULL
          AND btrim(v.edition) <> ''
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM card_variants
                WHERE edition IS NOT NULL AND btrim(edition) <> '' AND edition_id IS NULL
            ) THEN
                RAISE EXCEPTION 'Nonblank Printing edition could not be resolved; migration aborted';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM card_variants
                GROUP BY card_id, edition_id, normalize(rarity_override),
                    normalize(source_variant), normalize(card_version), normalize(stamp)
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Edition normalization creates ambiguous Printing identities';
            END IF;
        END $$
    """)
    op.alter_column("card_variants", "set_id", nullable=False)
    op.create_index("ix_card_variants_set_id", "card_variants", ["set_id"])
    op.create_index("ix_card_variants_edition_id", "card_variants", ["edition_id"])
    op.create_foreign_key(
        "fk_card_variants_card_set_owner",
        "card_variants",
        "cards",
        ["card_id", "set_id"],
        ["id", "set_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_card_variants_edition_set_owner",
        "card_variants",
        "editions",
        ["edition_id", "set_id"],
        ["id", "set_id"],
        ondelete="RESTRICT",
    )
    op.drop_index("uq_printing_semantic_identity", table_name="card_variants")
    op.execute("""
        CREATE UNIQUE INDEX uq_printing_semantic_identity ON card_variants
        (card_id, edition_id, normalize(rarity_override), normalize(source_variant),
         normalize(card_version), normalize(stamp)) NULLS NOT DISTINCT
    """)


def downgrade():
    op.execute("LOCK TABLE editions, cards, card_variants IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM editions)
            OR EXISTS (SELECT 1 FROM card_variants WHERE edition_id IS NOT NULL)
            THEN
                RAISE EXCEPTION 'Unsafe Edition downgrade: Edition identities would be lost';
            END IF;
        END $$
    """)
    op.drop_index("uq_printing_semantic_identity", table_name="card_variants")
    op.execute("""
        CREATE UNIQUE INDEX uq_printing_semantic_identity ON card_variants
        (card_id, normalize(edition), normalize(rarity_override), normalize(source_variant),
         normalize(card_version), normalize(stamp)) NULLS NOT DISTINCT
    """)
    op.drop_constraint("fk_card_variants_edition_set_owner", "card_variants", type_="foreignkey")
    op.drop_constraint("fk_card_variants_card_set_owner", "card_variants", type_="foreignkey")
    op.drop_index("ix_card_variants_edition_id", table_name="card_variants")
    op.drop_index("ix_card_variants_set_id", table_name="card_variants")
    op.drop_column("card_variants", "edition_id")
    op.drop_column("card_variants", "set_id")
    op.drop_constraint("uq_cards_id_set_id", "cards", type_="unique")
    op.drop_index("ix_editions_set_id", table_name="editions")
    op.drop_index("ix_editions_public_id", table_name="editions")
    op.drop_table("editions")
