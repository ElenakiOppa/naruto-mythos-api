"""Fictional Phase 13C domain tests, including a disposable localhost PostgreSQL cluster.

Never reads DATABASE_URL for migration tests. The test owns its initdb directory,
loopback port and server process; no existing database/server is contacted.
"""

import os
import shutil
import socket
import subprocess
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.models import (
    Card,
    CardVariant,
    Printing,
    PrintingTranslation,
    SourceRecord,
)

HEAD = "c13c20260916"
PREVIOUS = "8b41e2a9c730"


@pytest.fixture(scope="session")
def local_postgres(tmp_path_factory):
    initdb = shutil.which("initdb")
    if initdb is None:
        pytest.skip("Local PostgreSQL binaries required; no external database fallback")
    binary = Path(initdb).parent
    root = tmp_path_factory.mktemp("phase13c_postgres")
    data = root / "cluster"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def run(*args):
        return subprocess.run(
            list(map(str, args)),
            check=True,
            capture_output=True,
            text=True,
            creationflags=flags,
        )

    run(initdb, "-D", data, "-U", "phase13c_test", "--auth=trust", "--encoding=UTF8", "--no-locale")
    ctl = binary / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl")
    run(ctl, "-D", data, "-l", root / "server.log", "-o", f"-h 127.0.0.1 -p {port}", "-w", "start")
    engine = sa.create_engine(f"postgresql+psycopg://phase13c_test@127.0.0.1:{port}/postgres")
    try:
        with engine.connect() as c:
            assert int(c.scalar(sa.text("SHOW server_version_num"))) >= 150000
        yield engine
    finally:
        engine.dispose()
        run(ctl, "-D", data, "-m", "fast", "-w", "stop")


@pytest.fixture
def pg(local_postgres):
    schema = "fictional_" + uuid.uuid4().hex
    with local_postgres.connect() as c:
        c.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        c.execute(sa.text(f'SET search_path TO "{schema}"'))
        c.commit()
        try:
            yield c
        finally:
            c.rollback()
            c.execute(sa.text("SET search_path TO public"))
            c.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
            c.commit()


def migrate(c, revision=HEAD, downgrade=False):
    cfg = Config("alembic.ini")
    cfg.attributes["connection"] = c
    (command.downgrade if downgrade else command.upgrade)(cfg, revision)
    c.commit()


def base_rows(c):
    ids = {k: uuid.uuid4() for k in ("set", "card", "variant", "image", "keyword", "source")}
    c.execute(
        sa.text(
            "INSERT INTO sets(id,public_id,name) VALUES (:id,'fictional-set','Ember Expansion')"
        ),
        {"id": ids["set"]},
    )
    c.execute(
        sa.text(
            "INSERT INTO cards(id,public_id,set_id,card_number,name,power) VALUES (:id,'fictional-card',:parent,'001/999','Ember Scout',3)"
        ),
        {"id": ids["card"], "parent": ids["set"]},
    )
    c.execute(
        sa.text(
            "INSERT INTO card_variants(id,public_id,card_id,variant_type) VALUES (:id,'legacy-visible-id',:parent,'legacy-holo')"
        ),
        {"id": ids["variant"], "parent": ids["card"]},
    )
    c.execute(
        sa.text(
            "INSERT INTO card_images(id,card_id,variant_id,url) VALUES (:id,:card,:variant,'https://example.invalid/front.png')"
        ),
        {"id": ids["image"], "card": ids["card"], "variant": ids["variant"]},
    )
    c.execute(
        sa.text("INSERT INTO keywords(id,slug,name) VALUES (:id,'fictional','Fictional')"),
        {"id": ids["keyword"]},
    )
    c.execute(
        sa.text("INSERT INTO card_keywords(card_id,keyword_id) VALUES (:card,:keyword)"),
        {"card": ids["card"], "keyword": ids["keyword"]},
    )
    c.execute(
        sa.text(
            "INSERT INTO source_records(id,entity_type,entity_id,source_name,external_id) VALUES (:id,'card_variants',:variant,'Fictional source','old-source-id')"
        ),
        {"id": ids["source"], "variant": ids["variant"]},
    )
    c.commit()
    return ids


def test_clean_upgrade_and_safe_downgrade(pg):
    migrate(pg)
    assert pg.scalar(sa.text("SELECT version_num FROM alembic_version")) == HEAD
    assert "printing_translations" in sa.inspect(pg).get_table_names()
    pg.commit()
    migrate(pg, PREVIOUS, downgrade=True)
    assert "printing_translations" not in sa.inspect(pg).get_table_names()
    pg.commit()
    migrate(pg)


def test_existing_rows_survive_upgrade_and_downgrade(pg):
    migrate(pg, PREVIOUS)
    ids = base_rows(pg)
    tables = (
        "sets",
        "cards",
        "card_variants",
        "card_images",
        "keywords",
        "card_keywords",
        "source_records",
    )
    before = {
        t: [dict(r) for r in pg.execute(sa.text(f"SELECT * FROM {t}")).mappings()] for t in tables
    }
    pg.commit()
    migrate(pg)
    for t in tables:
        now = [dict(r) for r in pg.execute(sa.text(f"SELECT * FROM {t}")).mappings()]
        assert len(now) == len(before[t])
        for old, new in zip(before[t], now, strict=True):
            assert all(new[k] == v for k, v in old.items())
    assert (
        pg.scalar(
            sa.text("SELECT public_id FROM card_variants WHERE id=:id"), {"id": ids["variant"]}
        )
        == "legacy-visible-id"
    )
    pg.commit()
    migrate(pg, PREVIOUS, downgrade=True)
    assert pg.scalar(sa.text("SELECT count(*) FROM card_keywords")) == 1


def test_postgres_signed_range_and_downgrade_refusal(pg):
    migrate(pg)
    ids = base_rows(pg)
    for value in [-2147483648, -1, 2147483647]:
        pg.execute(
            sa.text("UPDATE cards SET power=:value WHERE id=:id"),
            {"value": value, "id": ids["card"]},
        )
        pg.commit()
    for value in [-2147483649, 2147483648]:
        with pytest.raises(sa.exc.DBAPIError):
            pg.execute(sa.text("UPDATE cards SET power=:value"), {"value": value})
        pg.rollback()
    pg.execute(sa.text("UPDATE cards SET power=-1"))
    pg.commit()
    with pytest.raises(sa.exc.DBAPIError, match="Unsafe Phase 13C downgrade"):
        migrate(pg, PREVIOUS, downgrade=True)
    pg.rollback()
    assert pg.scalar(sa.text("SELECT power FROM cards")) == -1
    assert pg.scalar(sa.text("SELECT version_num FROM alembic_version")) == HEAD


def test_printing_null_uniqueness_and_semantic_discriminators(pg):
    migrate(pg)
    ids = base_rows(pg)

    def add(public_id, **values):
        with Session(pg) as s:
            s.add(
                Printing(
                    public_id=public_id, card_id=ids["card"], variant_type="compatibility", **values
                )
            )
            s.commit()
        pg.commit()

    # All-null identity cannot evade uniqueness, even with a different public ID or language.
    with pytest.raises(sa.exc.IntegrityError):
        add("duplicate", language="FR")
    pg.rollback()
    for field, value in [
        ("edition", "Edition Two"),
        ("rarity_override", "Bright"),
        ("source_variant", "Foil"),
        ("card_version", "V2"),
        ("stamp", "Event"),
    ]:
        add("fictional-" + field, **{field: value})
    add("accent", stamp="Caf\u00e9")
    with pytest.raises(sa.exc.IntegrityError):
        add("same-accent", stamp="Cafe\u0301")
    pg.rollback()
    assert pg.scalar(sa.text("SELECT count(*) FROM card_variants")) == 7


def test_localization_provenance_mission_attachment_and_deletion(pg):
    migrate(pg)
    ids = base_rows(pg)
    assert Printing is CardVariant
    with Session(pg) as s:
        printing = s.get(Printing, ids["variant"])
        for lang in ("EN", "FR"):
            s.add(
                PrintingTranslation(
                    printing=printing,
                    language=lang,
                    title="Fictional " + lang,
                    rules_text="Invented local text",
                    image_url=f"https://example.invalid/{lang}.png",
                )
            )
        for uid in ("fictional-old", "fictional-new"):
            s.add(
                SourceRecord(
                    entity_type="card_variants",
                    entity_id=printing.id,
                    printing_id=printing.id,
                    source_uid=uid,
                    source_sku="fictional-sku",
                    source_name="Fictional publisher",
                    observation={"Power": -1},
                )
            )
        s.add(
            Card(
                public_id="fictional-mission",
                set_id=ids["set"],
                card_number="M01",
                name="Ember Quest",
                card_type="Mission",
                points=3,
            )
        )
        s.add(
            Card(
                public_id="fictional-attachment",
                set_id=ids["set"],
                card_number="A01",
                name="Ember Weight",
                card_type="Attachment",
                power=-1,
            )
        )
        s.commit()
    pg.commit()
    assert pg.scalar(sa.text("SELECT count(*) FROM printing_translations")) == 2
    assert (
        pg.scalar(sa.text("SELECT count(*) FROM source_records WHERE printing_id IS NOT NULL")) == 2
    )
    assert pg.scalar(sa.text("SELECT chakra FROM cards WHERE card_type='Mission'")) is None
    with pytest.raises(sa.exc.IntegrityError):
        pg.execute(sa.text("DELETE FROM card_variants WHERE id=:id"), {"id": ids["variant"]})
    pg.rollback()  # Typed provenance prevents silent destruction.
    with pytest.raises(sa.exc.DBAPIError, match="Unsafe Phase 13C downgrade"):
        migrate(pg, PREVIOUS, downgrade=True)
    pg.rollback()
    # Explicit fictional observation removal tests the remaining original owner actions.
    pg.execute(sa.text("DELETE FROM source_records WHERE printing_id IS NOT NULL"))
    pg.execute(sa.text("DELETE FROM card_variants WHERE id=:id"), {"id": ids["variant"]})
    pg.commit()
    assert pg.scalar(sa.text("SELECT count(*) FROM printing_translations")) == 0
    assert pg.scalar(sa.text("SELECT variant_id FROM card_images")) is None
    assert pg.scalar(sa.text("SELECT card_id FROM card_images")) == ids["card"]


def test_ambiguous_legacy_upgrade_rolls_back(pg):
    migrate(pg, PREVIOUS)
    ids = base_rows(pg)
    pg.execute(
        sa.text(
            "INSERT INTO card_variants(id,public_id,card_id,variant_type) VALUES (:id,'second-old-id',:parent,'different-legacy-type')"
        ),
        {"id": uuid.uuid4(), "parent": ids["card"]},
    )
    pg.commit()
    with pytest.raises(sa.exc.DBAPIError, match="Legacy Printing identity is ambiguous"):
        migrate(pg)
    pg.rollback()
    assert pg.scalar(sa.text("SELECT count(*) FROM card_variants")) == 2
    assert pg.scalar(sa.text("SELECT version_num FROM alembic_version")) == PREVIOUS
    assert "points" not in {c["name"] for c in sa.inspect(pg).get_columns("cards")}
