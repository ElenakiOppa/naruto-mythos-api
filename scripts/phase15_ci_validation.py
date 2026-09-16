"""Ephemeral Phase 15 CI validation: acquire, import twice, validate the API.

This script is run only inside a disposable GitHub Actions runner. It never
writes raw source data to the repository or an artifact and prints aggregates,
not catalogue records or source text.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.main import app
from app.models import Card, CardSet, CardVariant, Keyword
from importer.catalogue_importer import build_dry_run
from importer.catalogue_persistence import PersistenceCounts, persist_catalogue_plan

EXPECTED_PLAN_HASH = "2a209a10ab4a59c25a2730f991ac4a3978fd0758e7e232a0d1d94815cb34a091"


def _api_check(session: Session) -> dict[str, object]:
    client = TestClient(app)
    sets = list(session.scalars(sa.select(CardSet).order_by(CardSet.public_id)))
    cards = list(session.scalars(sa.select(Card).order_by(Card.public_id)))
    mission = session.scalar(sa.select(Card).where(Card.card_type == "Mission"))
    attachment = session.scalar(sa.select(Card).where(Card.card_type == "Attachment"))
    negative = session.scalar(sa.select(Card).where(Card.power == -1))
    keyword = session.scalar(sa.select(Keyword).order_by(Keyword.slug))

    def get(path: str, **params):
        response = client.get(path, params=params)
        if response.status_code != 200:
            raise AssertionError(f"{path} returned {response.status_code}: {response.text[:200]}")
        return response.json()

    assert get("/health")["status"] == "ok"
    assert get("/ready")["status"] == "ready"
    sets_response = get("/v1/sets", page=1, limit=10)
    assert sets_response["pagination"]["total"] == 2
    assert {item["id"] for item in sets_response["data"]} == {item.public_id for item in sets}
    set_detail = get(f"/v1/sets/{sets[0].public_id}")
    assert set_detail["id"] == sets[0].public_id
    set_cards = get(f"/v1/sets/{sets[0].public_id}/cards", page=1, limit=1)
    assert set_cards["pagination"]["total"] > 0

    cards_response = get("/v1/cards", page=1, limit=10)
    assert cards_response["pagination"]["total"] == 318
    assert get("/v1/cards", page=2, limit=10)["pagination"]["page"] == 2
    assert get("/v1/cards", page=1, limit=10, type="Mission")["pagination"]["total"] == 20
    assert get("/v1/cards", page=1, limit=10, type="Attachment")["pagination"]["total"] == 32
    assert get("/v1/cards", page=1, limit=10, rarity="M")["pagination"]["total"] > 0
    assert get("/v1/cards/random")["id"] in {card.public_id for card in cards}
    assert get(f"/v1/cards/{cards[0].public_id}")["id"] == cards[0].public_id

    rarities = get("/v1/rarities")
    assert any(item["slug"] == "m" for item in rarities)
    keywords = get("/v1/keywords")
    assert keywords and keyword is not None
    keyword_cards = get(f"/v1/keywords/{keyword.slug}/cards", page=1, limit=10)
    assert keyword_cards["pagination"]["total"] > 0
    search = get("/v1/search", q="Naruto")
    assert search["data"]

    assert mission is not None and get(f"/v1/cards/{mission.public_id}")["type"] == "Mission"
    assert (
        attachment is not None and get(f"/v1/cards/{attachment.public_id}")["type"] == "Attachment"
    )
    assert negative is not None and get(f"/v1/cards/{negative.public_id}")["power"] == -1
    return {
        "routes": 12,
        "set_count": len(sets),
        "card_count": len(cards),
        "mission": True,
        "attachment": True,
        "negative_power": True,
        "pagination_filter_search": True,
    }


def main(root: Path) -> None:
    result = build_dry_run(root)
    report = result["report"]
    assert report["source_records"] == 636
    assert report["parsed"] == 636
    assert report["accepted"] == 636
    assert report["rejected"] == 0
    assert report["unexplained_quarantine"] == 0
    assert report["unique_cards"] == 318
    assert report["unique_printings"] == 636
    assert report["plan_sha256"] == EXPECTED_PLAN_HASH
    print(json.dumps({"phase": "pre_database", **report}, sort_keys=True))

    first: PersistenceCounts
    second: PersistenceCounts
    with SessionLocal() as session:
        first = persist_catalogue_plan(session, result)
        first_ids = set(session.scalars(sa.select(Card.public_id)).all())
        first_printing_ids = set(session.scalars(sa.select(CardVariant.public_id)).all())
    with SessionLocal() as session:
        second = persist_catalogue_plan(session, result)
        second_ids = set(session.scalars(sa.select(Card.public_id)).all())
        second_printing_ids = set(session.scalars(sa.select(CardVariant.public_id)).all())
        api_result = _api_check(session)

    assert first == second
    assert first.cards == 318 and first.printings == 636
    assert first_ids == second_ids
    assert first_printing_ids == second_printing_ids
    print(
        json.dumps(
            {"first_import": first.__dict__, "second_import": second.__dict__},
            sort_keys=True,
        )
    )
    print(json.dumps({"api": api_result}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    main(args.root)
