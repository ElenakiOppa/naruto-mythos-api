"""Portable relationship tests; actual ownership enforcement is PostgreSQL-only."""

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from app.models import CardImage, CardVariant
from app.schemas.card import CardDetail
from app.services.card_service import get_card_by_public_id
from tests.test_models import make_card, make_set


def test_postgresql_ddl_ownership():
    ddl = str(CreateTable(CardImage.__table__).compile(dialect=postgresql.dialect()))
    assert "FOREIGN KEY(variant_id, card_id)" in ddl
    assert "ON DELETE SET NULL (variant_id)" in ddl
    assert "fk_card_images_variant_id_card_variants" not in ddl
    assert "uq_card_variants_id_card_id" in str(
        CreateTable(CardVariant.__table__).compile(dialect=postgresql.dialect())
    )


def test_sqlite_keeps_foreign_key():
    ddl = str(CreateTable(CardImage.__table__).compile(dialect=sqlite.dialect()))
    assert "fk_card_images_variant_id_card_variants" in ddl
    assert "ON DELETE SET NULL" in ddl
    assert "fk_card_images_variant_card_owner" not in ddl


def test_variant_relationship_only_synchronizes_variant_id():
    for relationship in (CardImage.variant.property, CardVariant.images.property):
        assert [dest.name for source, dest in relationship.synchronize_pairs] == ["variant_id"]


def test_orm_delete_serializes_image_as_direct(db_session):
    card = make_card(db_session, make_set(db_session))
    variant = CardVariant(card=card, public_id="FICTIONAL-OWNERSHIP-V", variant_type="test")
    image = CardImage(card=card, variant=variant, url="https://example.invalid/ownership.png")
    db_session.add(image)
    db_session.commit()
    image_id, card_id = image.id, card.id
    detail = CardDetail.model_validate(get_card_by_public_id(db_session, card.public_id))
    assert detail.images == [] and len(detail.variants[0].images) == 1
    db_session.delete(variant)
    db_session.commit()
    db_session.expire_all()
    image = db_session.get(CardImage, image_id)
    assert image.card_id == card_id and image.variant_id is None
    detail = CardDetail.model_validate(get_card_by_public_id(db_session, card.public_id))
    assert len(detail.images) == 1 and detail.variants == []
