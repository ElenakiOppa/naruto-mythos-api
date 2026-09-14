"""PostgreSQL ownership/migration verification; isolated schema is rolled back."""

import json
import uuid
import warnings
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, SAWarning
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Card, CardImage, CardSet, CardVariant
from app.schemas.card import CardDetail
from app.services.card_service import get_card_by_public_id

HEAD = "8b41e2a9c730"
OLD = "5f360cfd2561"


def main():
    result = {}
    schema = "p9a_" + uuid.uuid4().hex
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            cfg = Config("alembic.ini")
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, OLD)
            st, a, b, va, vb, direct, variant = [uuid.uuid4() for _ in range(7)]
            conn.execute(
                insert(CardSet), {"id": st, "public_id": "P9A-SET", "name": "Fictional Set"}
            )
            conn.execute(
                insert(Card),
                [
                    {
                        "id": a,
                        "set_id": st,
                        "public_id": "P9A-A",
                        "card_number": "001",
                        "name": "Fictional A",
                    },
                    {
                        "id": b,
                        "set_id": st,
                        "public_id": "P9A-B",
                        "card_number": "002",
                        "name": "Fictional B",
                    },
                ],
            )
            conn.execute(
                insert(CardVariant),
                [
                    {"id": va, "card_id": a, "public_id": "P9A-VA", "variant_type": "test"},
                    {"id": vb, "card_id": b, "public_id": "P9A-VB", "variant_type": "test"},
                ],
            )
            conn.execute(
                insert(CardImage),
                [
                    {
                        "id": direct,
                        "card_id": a,
                        "variant_id": None,
                        "url": "https://example.invalid/direct.png",
                    },
                    {
                        "id": variant,
                        "card_id": a,
                        "variant_id": va,
                        "url": "https://example.invalid/variant.png",
                    },
                ],
            )

            def constraints():
                return conn.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace=current_schema()::regnamespace ORDER BY conname"
                    )
                ).all()

            old_constraints = constraints()
            bad = uuid.uuid4()
            conn.execute(
                insert(CardImage),
                {
                    "id": bad,
                    "card_id": a,
                    "variant_id": vb,
                    "url": "https://example.invalid/bad.png",
                },
            )
            save = conn.begin_nested()
            try:
                command.upgrade(cfg, HEAD)
            except DBAPIError as exc:
                assert "ownership mismatch: 1 row(s)" in str(exc)
                save.rollback()
            else:
                raise AssertionError("Invalid legacy upgrade unexpectedly succeeded")
            assert constraints() == old_constraints
            assert conn.execute(
                select(CardImage.card_id, CardImage.variant_id).where(CardImage.id == bad)
            ).one() == (a, vb)
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == OLD
            result["invalid_legacy_preflight_atomic"] = True
            conn.execute(delete(CardImage).where(CardImage.id == bad))
            command.upgrade(cfg, HEAD)
            assert (
                conn.execute(select(CardImage.variant_id).where(CardImage.id == variant)).scalar()
                == va
            )
            upgraded = dict(constraints())
            assert "SET NULL (variant_id)" in upgraded["fk_card_images_variant_card_owner"]
            assert "uq_card_variants_id_card_id" in upgraded
            assert "fk_card_images_variant_id_card_variants" not in upgraded
            result["valid_upgrade_preserves_images"] = True
            command.downgrade(cfg, OLD)
            assert constraints() == old_constraints
            command.upgrade(cfg, HEAD)
            result["downgrade_exact_constraints_and_reupgrade"] = True
            with conn.begin_nested() as save:
                try:
                    conn.execute(
                        insert(CardImage),
                        {
                            "card_id": a,
                            "variant_id": vb,
                            "url": "https://example.invalid/reject.png",
                        },
                    )
                except IntegrityError as exc:
                    assert exc.orig.sqlstate == "23503"
                    assert exc.orig.diag.constraint_name == "fk_card_images_variant_card_owner"
                    save.rollback()
                else:
                    raise AssertionError("Cross-card INSERT accepted")
            result["sql_cross_card_insert_rejected"] = True
            with warnings.catch_warnings():
                warnings.simplefilter("error", SAWarning)
                with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
                    ca, cv = db.get(Card, a), db.get(CardVariant, va)
                    img = CardImage(card=ca, variant=cv, url="https://example.invalid/orm.png")
                    db.add(img)
                    db.commit()
                    image_id = img.id
                    assert img.card_id == a and img.variant_id == va
                    assert img in cv.images and img in ca.images
                    img.variant = db.get(CardVariant, vb)
                    try:
                        db.commit()
                    except IntegrityError:
                        db.rollback()
                    else:
                        raise AssertionError("Cross-card ORM assignment accepted")
                    db.expire_all()
                    assert db.get(CardImage, image_id).card_id == a
                    cv = db.get(CardVariant, va)
                    assert len(cv.images) == 2
                    db.delete(cv)
                    db.commit()
                    db.expire_all()
                    preserved = db.get(CardImage, image_id)
                    assert preserved.card_id == a and preserved.variant_id is None
                    public = CardDetail.model_validate(
                        get_card_by_public_id(db, "P9A-A")
                    ).model_dump(mode="json")
                    assert len(public["images"]) == 3 and public["variants"] == []
                    live = CardVariant(
                        card=db.get(Card, a), public_id="P9A-ORM-LIVE", variant_type="test"
                    )
                    live_image = CardImage(
                        card=db.get(Card, a),
                        variant=live,
                        url="https://example.invalid/orm-live.png",
                    )
                    db.add(live_image)
                    db.commit()
                    assert live.images and db.get(Card, a).variants
                    db.delete(db.get(Card, a))
                    db.commit()
                    assert db.scalar(select(CardImage.id).where(CardImage.card_id == a)) is None
            result["orm_assignment_loading_rejection_delete_serialization_no_warnings"] = True
            # Raw SQL deletion tests independently exercise database actions.
            raw_image = uuid.uuid4()
            conn.execute(
                insert(CardImage),
                {
                    "id": raw_image,
                    "card_id": b,
                    "variant_id": vb,
                    "url": "https://example.invalid/raw.png",
                },
            )
            conn.execute(delete(CardVariant).where(CardVariant.id == vb))
            assert conn.execute(
                select(CardImage.card_id, CardImage.variant_id).where(CardImage.id == raw_image)
            ).one() == (b, None)
            another_variant, another_image = uuid.uuid4(), uuid.uuid4()
            conn.execute(
                insert(CardVariant),
                {
                    "id": another_variant,
                    "card_id": b,
                    "public_id": "P9A-LIVE",
                    "variant_type": "test",
                },
            )
            conn.execute(
                insert(CardImage),
                {
                    "id": another_image,
                    "card_id": b,
                    "variant_id": another_variant,
                    "url": "https://example.invalid/live.png",
                },
            )
            conn.execute(delete(Card).where(Card.id == b))
            assert (
                conn.execute(select(CardImage.id).where(CardImage.id == another_image)).first()
                is None
            )
            assert (
                conn.execute(select(CardImage.id).where(CardImage.id == raw_image)).first() is None
            )
            result["sql_variant_preserved_then_card_cascade"] = True
        finally:
            outer.rollback()
        assert (
            conn.execute(
                text("SELECT count(*) FROM pg_namespace WHERE nspname=:name"), {"name": schema}
            ).scalar()
            == 0
        )
        result["isolated_schema_rolled_back"] = True
    Path("phase9a_verification_results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
