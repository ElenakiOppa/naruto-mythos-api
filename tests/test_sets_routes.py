"""
Route-level tests for GET /v1/sets, GET /v1/sets/{id}, and
GET /v1/sets/{id}/cards.

Uses the `client` fixture from conftest.py, which wires FastAPI's real
routing/dependency-injection stack to the same isolated in-memory SQLite
database as the `db_session` fixture (via a `get_db` dependency override) --
so these are genuine HTTP-level integration tests, not just service-layer
unit tests, while still being fast and requiring no real PostgreSQL.

All fixture data is obviously fictional (TEST-*, test-set-*, "Test
Character Alpha", etc.) -- no real Naruto Mythos data appears anywhere.
"""

from datetime import date

from sqlalchemy import event

from app.models import Card, CardImage, CardSet


def make_set(
    db_session,
    *,
    public_id="test-set-1",
    code="TST1",
    name="Test Set Alpha",
    edition="1st Edition",
    language="EN",
    release_date=None,
):
    card_set = CardSet(
        public_id=public_id,
        code=code,
        name=name,
        edition=edition,
        language=language,
        release_date=release_date,
    )
    db_session.add(card_set)
    db_session.commit()
    return card_set


def make_card(
    db_session,
    card_set,
    *,
    public_id="TEST-001",
    card_number="001",
    name="Test Character Alpha",
    card_type="Character",
    rarity=None,
):
    card = Card(
        public_id=public_id,
        set_id=card_set.id,
        card_number=card_number,
        name=name,
        card_type=card_type,
        rarity=rarity,
    )
    db_session.add(card)
    db_session.commit()
    return card


# ---------------------------------------------------------------------------
# GET /v1/sets
# ---------------------------------------------------------------------------


def test_list_sets_empty_database(client):
    response = client.get("/v1/sets")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["pagination"] == {
        "page": 1,
        "limit": 50,
        "total": 0,
        "pages": 0,
        "has_next": False,
        "has_previous": False,
    }


def test_list_sets_one_set(client, db_session):
    make_set(db_session, release_date=date(2026, 1, 1))

    response = client.get("/v1/sets")

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == "test-set-1"
    assert body["pagination"]["total"] == 1


def test_list_sets_multiple_sets(client, db_session):
    for i in range(3):
        make_set(db_session, public_id=f"test-set-{i}", name=f"Test Set {i}")

    response = client.get("/v1/sets")

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 3
    assert body["pagination"]["total"] == 3


def test_list_sets_pagination(client, db_session):
    for i in range(5):
        make_set(db_session, public_id=f"test-set-{i}", name=f"Test Set {i}")

    response = client.get("/v1/sets?page=2&limit=2")

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"] == {
        "page": 2,
        "limit": 2,
        "total": 5,
        "pages": 3,
        "has_next": True,
        "has_previous": True,
    }


def test_list_sets_page_beyond_available_results(client, db_session):
    make_set(db_session)

    response = client.get("/v1/sets?page=99&limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["page"] == 99
    assert body["pagination"]["total"] == 1
    assert body["pagination"]["has_next"] is False
    assert body["pagination"]["has_previous"] is True


def test_list_sets_limit_100_accepted(client, db_session):
    make_set(db_session)

    response = client.get("/v1/sets?limit=100")

    assert response.status_code == 200


def test_list_sets_limit_over_100_rejected(client):
    response = client.get("/v1/sets?limit=101")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PAGINATION"


def test_list_sets_page_zero_rejected(client):
    response = client.get("/v1/sets?page=0")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PAGINATION"


def test_list_sets_language_filter(client, db_session):
    make_set(db_session, public_id="en-set", language="EN")
    make_set(db_session, public_id="jp-set", language="JP")

    response = client.get("/v1/sets?language=en")  # case-insensitive

    body = response.json()
    assert [s["id"] for s in body["data"]] == ["en-set"]


def test_list_sets_edition_filter(client, db_session):
    make_set(db_session, public_id="first-ed", edition="1st Edition")
    make_set(db_session, public_id="second-ed", edition="2nd Edition")

    response = client.get("/v1/sets?edition=1st%20edition")  # case-insensitive

    body = response.json()
    assert [s["id"] for s in body["data"]] == ["first-ed"]


def test_list_sets_code_filter(client, db_session):
    make_set(db_session, public_id="a-set", code="AAA1")
    make_set(db_session, public_id="b-set", code="BBB1")

    response = client.get("/v1/sets?code=aaa1")  # case-insensitive

    body = response.json()
    assert [s["id"] for s in body["data"]] == ["a-set"]


def test_list_sets_sort_by_name_asc(client, db_session):
    make_set(db_session, public_id="s-b", name="Beta Set")
    make_set(db_session, public_id="s-a", name="Alpha Set")

    response = client.get("/v1/sets?sort=name&order=asc")

    body = response.json()
    assert [s["id"] for s in body["data"]] == ["s-a", "s-b"]


def test_list_sets_sort_by_name_desc(client, db_session):
    make_set(db_session, public_id="s-b", name="Beta Set")
    make_set(db_session, public_id="s-a", name="Alpha Set")

    response = client.get("/v1/sets?sort=name&order=desc")

    body = response.json()
    assert [s["id"] for s in body["data"]] == ["s-b", "s-a"]


def test_list_sets_sort_by_release_date_handles_nulls_deterministically(client, db_session):
    make_set(db_session, public_id="dated", name="Dated Set", release_date=date(2026, 1, 1))
    make_set(db_session, public_id="undated", name="Undated Set", release_date=None)

    response_desc = client.get("/v1/sets?sort=release_date&order=desc")
    response_asc = client.get("/v1/sets?sort=release_date&order=asc")

    # Regardless of direction, the null release_date always sorts last --
    # deterministic null handling, not direction-dependent.
    assert [s["id"] for s in response_desc.json()["data"]] == ["dated", "undated"]
    assert [s["id"] for s in response_asc.json()["data"]] == ["dated", "undated"]


def test_list_sets_sort_by_code(client, db_session):
    make_set(db_session, public_id="s-z", code="ZZZ1")
    make_set(db_session, public_id="s-a", code="AAA1")

    response = client.get("/v1/sets?sort=code&order=asc")

    body = response.json()
    assert [s["id"] for s in body["data"]] == ["s-a", "s-z"]


def test_list_sets_invalid_sort_rejected(client):
    response = client.get("/v1/sets?sort=not_a_real_field")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SORT"


def test_list_sets_invalid_order_rejected(client):
    response = client.get("/v1/sets?order=sideways")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SORT"


# ---------------------------------------------------------------------------
# GET /v1/sets/{id}
# ---------------------------------------------------------------------------


def test_get_set_existing(client, db_session):
    make_set(db_session, release_date=date(2026, 1, 1))

    response = client.get("/v1/sets/test-set-1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "test-set-1"
    assert body["name"] == "Test Set Alpha"


def test_get_set_missing_returns_404(client):
    response = client.get("/v1/sets/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "SET_NOT_FOUND", "message": "Set not found."}}


def test_get_set_uses_correct_public_id_lookup(client, db_session):
    make_set(db_session, public_id="set-a", name="Set A")
    make_set(db_session, public_id="set-b", name="Set B")

    response = client.get("/v1/sets/set-b")

    assert response.json()["id"] == "set-b"
    assert response.json()["name"] == "Set B"


def test_get_set_internal_uuid_does_not_work_as_lookup(client, db_session):
    card_set = make_set(db_session)

    response = client.get(f"/v1/sets/{card_set.id}")  # the real internal UUID

    assert response.status_code == 404


def test_get_set_response_contains_no_internal_uuid(client, db_session):
    card_set = make_set(db_session)

    response = client.get("/v1/sets/test-set-1")

    assert str(card_set.id) not in response.text


def test_get_set_nullable_fields_serialize_as_null(client, db_session):
    make_set(
        db_session,
        public_id="bare-set",
        code=None,
        edition=None,
        release_date=None,
    )

    response = client.get("/v1/sets/bare-set")
    body = response.json()

    assert body["code"] is None
    assert body["edition"] is None
    assert body["release_date"] is None
    assert body["printed_total"] is None
    assert body["total_with_variants"] is None
    assert body["logo_url"] is None
    assert body["symbol_url"] is None


# ---------------------------------------------------------------------------
# GET /v1/sets/{id}/cards
# ---------------------------------------------------------------------------


def test_list_set_cards_empty_set(client, db_session):
    make_set(db_session)

    response = client.get("/v1/sets/test-set-1/cards")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0


def test_list_set_cards_with_cards(client, db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set, public_id="TEST-001", card_number="001")
    make_card(db_session, card_set, public_id="TEST-A02", card_number="A02")

    response = client.get("/v1/sets/test-set-1/cards")

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["total"] == 2


def test_list_set_cards_missing_set_returns_404(client):
    response = client.get("/v1/sets/does-not-exist/cards")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SET_NOT_FOUND"


def test_list_set_cards_pagination(client, db_session):
    card_set = make_set(db_session)
    for i in range(5):
        make_card(db_session, card_set, public_id=f"TEST-{i:03d}", card_number=f"{i:03d}")

    response = client.get("/v1/sets/test-set-1/cards?page=2&limit=2")

    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"] == {
        "page": 2,
        "limit": 2,
        "total": 5,
        "pages": 3,
        "has_next": True,
        "has_previous": True,
    }


def test_list_set_cards_sort_by_number_is_lexical_not_numeric(client, db_session):
    card_set = make_set(db_session)
    # "10" sorts before "2" lexically -- this is the whole point of the
    # test: proving no numeric casting/"natural sort" is happening.
    make_card(db_session, card_set, public_id="TEST-1", card_number="1")
    make_card(db_session, card_set, public_id="TEST-2", card_number="2")
    make_card(db_session, card_set, public_id="TEST-10", card_number="10")

    response = client.get("/v1/sets/test-set-1/cards?sort=number&order=asc")

    numbers = [c["number"] for c in response.json()["data"]]
    assert numbers == ["1", "10", "2"]


def test_list_set_cards_sort_by_name(client, db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set, public_id="TEST-B", card_number="002", name="Beta Card")
    make_card(db_session, card_set, public_id="TEST-A", card_number="001", name="Alpha Card")

    response = client.get("/v1/sets/test-set-1/cards?sort=name&order=asc")

    names = [c["name"] for c in response.json()["data"]]
    assert names == ["Alpha Card", "Beta Card"]


def test_list_set_cards_sort_by_rarity_handles_nulls(client, db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set, public_id="TEST-R", card_number="001", rarity="Rare")
    make_card(db_session, card_set, public_id="TEST-N", card_number="002", rarity=None)

    response = client.get("/v1/sets/test-set-1/cards?sort=rarity&order=asc")

    ids = [c["id"] for c in response.json()["data"]]
    # The card with a null rarity sorts last regardless of direction.
    assert ids == ["TEST-R", "TEST-N"]


def test_list_set_cards_invalid_sort_rejected(client, db_session):
    make_set(db_session)

    response = client.get("/v1/sets/test-set-1/cards?sort=not_a_real_field")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SORT"


def test_list_set_cards_invalid_order_rejected(client, db_session):
    make_set(db_session)

    response = client.get("/v1/sets/test-set-1/cards?order=sideways")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_SORT"


def test_list_set_cards_card_summary_shape(client, db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set, rarity="Rare")
    db_session.add(
        CardImage(card_id=card.id, image_type="front", url="https://example.invalid/a.jpg")
    )
    db_session.commit()

    response = client.get("/v1/sets/test-set-1/cards")
    item = response.json()["data"][0]

    assert set(item.keys()) == {
        "id",
        "number",
        "name",
        "subtitle",
        "type",
        "rarity",
        "set",
        "images",
    }


def test_list_set_cards_excludes_ability_text(client, db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set)

    response = client.get("/v1/sets/test-set-1/cards")

    assert "ability_text" not in response.json()["data"][0]


def test_list_set_cards_excludes_flavor_text(client, db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set)

    response = client.get("/v1/sets/test-set-1/cards")

    assert "flavor_text" not in response.json()["data"][0]


def test_list_set_cards_excludes_variants(client, db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set)

    response = client.get("/v1/sets/test-set-1/cards")

    assert "variants" not in response.json()["data"][0]


def test_list_set_cards_excludes_keywords(client, db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set)

    response = client.get("/v1/sets/test-set-1/cards")

    assert "keywords" not in response.json()["data"][0]


def test_list_set_cards_excludes_internal_uuids(client, db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)

    response = client.get("/v1/sets/test-set-1/cards")

    assert str(card.id) not in response.text
    assert str(card_set.id) not in response.text


def test_list_set_cards_set_nested_correctly(client, db_session):
    card_set = make_set(db_session)
    make_card(db_session, card_set)

    response = client.get("/v1/sets/test-set-1/cards")
    item = response.json()["data"][0]

    assert item["set"]["id"] == "test-set-1"
    assert item["set"]["name"] == "Test Set Alpha"


def test_list_set_cards_images_serialized_correctly(client, db_session):
    card_set = make_set(db_session)
    card = make_card(db_session, card_set)
    db_session.add(
        CardImage(
            card_id=card.id,
            image_type="front",
            url="https://example.invalid/test-card.jpg",
            width=734,
            height=1024,
            source_name="test-fixture-source",
        )
    )
    db_session.commit()

    response = client.get("/v1/sets/test-set-1/cards")
    item = response.json()["data"][0]

    assert item["images"] == [
        {
            "type": "front",
            "url": "https://example.invalid/test-card.jpg",
            "width": 734,
            "height": 1024,
        }
    ]


# ---------------------------------------------------------------------------
# N+1 query regression test
# ---------------------------------------------------------------------------


def test_list_set_cards_does_not_n_plus_one(client, db_session):
    """Listing many cards must not issue one extra query per card for
    `set`/`images`.

    Mechanism: attach a SQLAlchemy `before_cursor_execute` listener to the
    test's SQLite engine, hit the route once for a set with several cards
    (each with an image), and assert the number of statements executed
    stays small and constant. An N+1 regression (e.g. lazy-loading `.set`
    or `.images` per card instead of eager-loading them) would instead
    make this scale linearly with the number of cards -- this test doesn't
    assert an exact brittle count, just that the growth clearly isn't 1:1
    with card count.
    """
    card_set = make_set(db_session)
    num_cards = 8
    for i in range(num_cards):
        card = make_card(db_session, card_set, public_id=f"TEST-{i:03d}", card_number=f"{i:03d}")
        db_session.add(
            CardImage(card_id=card.id, image_type="front", url=f"https://example.invalid/{i}.jpg")
        )
    db_session.commit()

    engine = db_session.get_bind()
    executed_statements = []

    def _record_statement(conn, cursor, statement, parameters, context, executemany):
        executed_statements.append(statement)

    event.listen(engine, "before_cursor_execute", _record_statement)
    try:
        response = client.get("/v1/sets/test-set-1/cards?limit=50")
    finally:
        event.remove(engine, "before_cursor_execute", _record_statement)

    assert response.status_code == 200
    assert len(response.json()["data"]) == num_cards

    # Expected constant-ish query shape: 1 set lookup (get_set_by_public_id),
    # 1 count query, 1 main card SELECT (with `set` joined in), 1 selectinload
    # query for images. A handful more is fine (e.g. driver/transaction
    # bookkeeping statements); what matters is this number does NOT scale
    # with num_cards. 8 cards with a real N+1 bug would push this well past
    # 8 (one extra query per card, per relationship) -- asserting a small
    # fixed ceiling well below num_cards catches that regression.
    assert len(executed_statements) < num_cards, (
        f"expected a small, roughly-constant number of queries regardless of "
        f"card count, but got {len(executed_statements)} queries for "
        f"{num_cards} cards -- this looks like an N+1 regression:\n"
        + "\n".join(executed_statements)
    )
