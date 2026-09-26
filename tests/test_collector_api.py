"""Public collector API integration tests using local deterministic fixtures."""

from __future__ import annotations

from collections import Counter

import pytest
from sqlalchemy import select

from app.models import CardSet, Edition
from importer.reference_catalogue import build_reference_reconciliation
from importer.reference_persistence import persist_reference_reconciliation
from tests.test_reference_catalogue import _seed_upstream_catalogue


@pytest.fixture
def persisted_collector_catalogue(db_session):
    _seed_upstream_catalogue(db_session)
    result = build_reference_reconciliation()
    persist_reference_reconciliation(db_session, result)
    return result


def test_cards_remain_canonical_and_sets_expose_distinct_counts(
    client, persisted_collector_catalogue
):
    cards = client.get("/v1/cards?limit=100").json()
    assert cards["pagination"]["total"] == 318

    sets = client.get("/v1/sets?limit=100").json()
    set1 = next(item for item in sets["data"] if item["name"] == "Set 1: Konoha Shidō")
    assert set1["canonical_card_count"] == 158
    assert set1["collectible_printing_count"] == 606
    assert {edition["name"] for edition in set1["editions"]} == {"1st edition", "2nd edition"}
    first = next(edition for edition in set1["editions"] if edition["name"] == "1st edition")
    assert first["collector_reference_status"] == "VERIFIED"
    assert first["collector_reference_count"] == 396
    assert first["canonical_card_count"] == 158
    assert first["collectible_printing_count"] == 396

    set2 = next(item for item in sets["data"] if item["name"] == "Set 2: Shinobi Shiren")
    assert all(edition["collector_reference_status"] == "NONE" for edition in set2["editions"])
    assert all(
        edition["collector_reference_status"] == "NONE"
        for edition in set1["editions"]
        if edition["name"] != "1st edition"
    )
    second_edition = next(
        edition for edition in set1["editions"] if edition["name"] == "2nd edition"
    )
    unavailable = client.get(f"/v1/editions/{second_edition['id']}/printings")
    assert unavailable.status_code == 404
    assert unavailable.json()["error"]["code"] == "COLLECTOR_REFERENCE_NOT_FOUND"


def test_public_edition_and_collector_view_are_complete_and_unique(
    client, db_session, persisted_collector_catalogue
):
    set1 = db_session.scalar(select(CardSet).where(CardSet.name == "Set 1: Konoha Shidō"))
    edition = db_session.scalar(
        select(Edition).where(Edition.set_id == set1.id, Edition.normalized_name == "1st edition")
    )
    assert edition is not None

    listed = client.get(f"/v1/sets/{set1.public_id}/editions").json()
    assert listed["pagination"]["total"] == 2
    set_editions = client.get(f"/v1/sets/{set1.public_id}/editions?limit=100").json()
    assert set_editions["pagination"]["total"] == 2
    detail = client.get(f"/v1/editions/{edition.public_id}").json()
    assert detail["collector_reference_status"] == "VERIFIED"
    assert detail["canonical_card_count"] == 158
    assert detail["collectible_printing_count"] == 396
    assert client.get(f"/v1/editions/{edition.public_id}").status_code == 200

    page1 = client.get(f"/v1/editions/{edition.public_id}/printings?limit=100&page=1").json()
    page2 = client.get(f"/v1/editions/{edition.public_id}/printings?limit=100&page=2").json()
    page3 = client.get(f"/v1/editions/{edition.public_id}/printings?limit=100&page=3").json()
    page4 = client.get(f"/v1/editions/{edition.public_id}/printings?limit=100&page=4").json()
    assert page1["pagination"]["total"] == 396
    assert page1["pagination"]["pages"] == 4
    data = page1["data"] + page2["data"] + page3["data"] + page4["data"]
    assert len(data) == 396
    assert len({item["id"] for item in data}) == 396
    assert all(item["edition_id"] == edition.public_id for item in data)
    assert all(item["origin"] in {"UPSTREAM_AND_CURATED", "CURATED_REFERENCE"} for item in data)
    assert Counter(item["origin"] for item in data) == {
        "UPSTREAM_AND_CURATED": 184,
        "CURATED_REFERENCE": 212,
    }
    source_only_ids = {
        item["printing_public_id"] for item in persisted_collector_catalogue["source_only"]
    }
    assert source_only_ids.isdisjoint({item["id"] for item in data})
    ordered_numbers = [item["collector_number"] for item in data]
    assert ordered_numbers.index("104") < ordered_numbers.index("104A")
    assert ordered_numbers.index("131") < ordered_numbers.index("n/2000")

    first_rows = page1["data"]
    assert all("image" not in item for item in first_rows)
    assert all(item["images"] == [] for item in first_rows if item["origin"] == "CURATED_REFERENCE")


def test_general_printing_api_keeps_source_only_rows_and_filters_origins(
    client, db_session, persisted_collector_catalogue
):
    all_rows = client.get("/v1/printings?limit=100").json()
    assert all_rows["pagination"]["total"] == 848

    curated = client.get("/v1/printings?origin=CURATED_REFERENCE&limit=100").json()
    overlap = client.get("/v1/printings?origin=UPSTREAM_AND_CURATED&limit=100").json()
    upstream_only_pages = [
        client.get(f"/v1/printings?origin=UPSTREAM&limit=100&page={page}").json()
        for page in range(1, 6)
    ]
    assert curated["pagination"]["total"] == 212
    assert overlap["pagination"]["total"] == 184
    assert upstream_only_pages[0]["pagination"]["total"] == 452

    source_only_ids = {
        item["printing_public_id"] for item in persisted_collector_catalogue["source_only"]
    }
    source_only_public = {
        item["id"] for response in upstream_only_pages for item in response["data"]
    }
    assert source_only_ids.intersection(source_only_public)

    set1 = db_session.scalar(select(CardSet).where(CardSet.name == "Set 1: Konoha Shidō"))
    first_edition = db_session.scalar(
        select(Edition).where(Edition.set_id == set1.id, Edition.normalized_name == "1st edition")
    )
    all_edition_rows = client.get(
        f"/v1/printings?edition={first_edition.public_id}&limit=100"
    ).json()
    assert all_edition_rows["pagination"]["total"] == 398
    rarity_filtered = client.get(
        f"/v1/printings?edition={first_edition.public_id}&rarity=Rare ART"
    ).json()
    assert rarity_filtered["pagination"]["total"] > 0
    treatment_filtered = client.get(
        f"/v1/printings?edition={first_edition.public_id}&treatment=Holographic"
    ).json()
    assert treatment_filtered["pagination"]["total"] > 0
    class_filtered = client.get(
        f"/v1/printings?edition={first_edition.public_id}&collector_class=Mission"
    ).json()
    assert class_filtered["pagination"]["total"] == 10
    set_filtered = client.get(f"/v1/printings?set={set1.public_id}&limit=100").json()
    assert set_filtered["pagination"]["total"] == 606
    card_id = persisted_collector_catalogue["curated_printings"][0]["card_public_id"]
    card_filtered = client.get(f"/v1/printings?card={card_id}").json()
    assert card_filtered["pagination"]["total"] >= 1


def test_card_filter_uses_printing_rarity_and_edition_without_duplicate_cards(
    client, db_session, persisted_collector_catalogue
):
    set1 = db_session.scalar(select(CardSet).where(CardSet.name == "Set 1: Konoha Shidō"))
    edition = db_session.scalar(
        select(Edition).where(Edition.normalized_name == "1st edition", Edition.set_id == set1.id)
    )
    result = client.get(f"/v1/cards?edition={edition.public_id}&rarity=Common&limit=100").json()
    ids = [item["id"] for item in result["data"]]
    assert result["pagination"]["total"] == len(ids)
    assert len(ids) == len(set(ids))
    assert result["pagination"]["total"] > 0


def test_card_detail_preserves_variants_and_adds_printings(client, persisted_collector_catalogue):
    detail = client.get("/v1/cards/crd_" + "0" * 56)
    assert detail.status_code == 404
    cards = client.get("/v1/cards?limit=1").json()["data"]
    item = client.get(f"/v1/cards/{cards[0]['id']}").json()
    assert "variants" in item
    assert "printings" in item
    assert len(item["printings"]) == len(item["variants"])
    assert all(printing["card_id"] == item["id"] for printing in item["printings"])
    assert client.get(f"/v1/printings/{item['printings'][0]['id']}").status_code == 200


def test_printing_rarity_metadata_and_openapi(client, persisted_collector_catalogue):
    legacy = client.get("/v1/rarities")
    printing_rarities = client.get("/v1/printing-rarities")
    assert legacy.status_code == 200
    assert printing_rarities.status_code == 200
    assert all("card_count" in item for item in legacy.json())
    assert all("printing_count" in item for item in printing_rarities.json())

    openapi = client.get("/openapi.json").json()
    paths = openapi["paths"]
    assert "/v1/printings" in paths
    assert "/v1/printings/{printing_id}" in paths
    assert "/v1/editions/{edition_id}" in paths
    assert "/v1/editions/{edition_id}/printings" in paths
    assert "/v1/sets/{set_id}/editions" in paths
