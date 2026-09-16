"""Phase 5 HTTP contract and query regressions using fictional records only."""

from datetime import date

import pytest
from sqlalchemy import event

from app.models import Card, CardImage, CardSet, CardVariant, Keyword

SUMMARY = {"id", "number", "name", "subtitle", "type", "rarity", "set", "images"}
DETAIL = SUMMARY | {
    "chakra",
    "power",
    "points",
    "faction",
    "ability_text",
    "flavor_text",
    "artist",
    "keywords",
    "variants",
}


def seed(db):
    alpha = CardSet(
        public_id="test-set-alpha",
        name="Test Set Alpha",
        code="TSTA",
        edition="Test Edition",
        release_date=date(2026, 1, 1),
    )
    beta = CardSet(public_id="test-set-beta", name="Test Set Beta", code="TSTB")
    db.add_all([alpha, beta])
    db.flush()
    cards = [
        Card(public_id=pid, set=st, card_number=num, name=name, rarity=rarity)
        for pid, st, num, name, rarity in [
            ("TEST-001", alpha, "1", "Test Character Alpha", "Rare"),
            ("TEST-002", alpha, "2", "Test Character Beta", None),
            ("TEST-A03", alpha, "10", "Test Character Gamma", "Common"),
            ("TEST-B01", beta, "1", "Test Character Alpha", "Rare"),
        ]
    ]
    db.add_all(cards)
    db.flush()
    variant = CardVariant(public_id="TEST-001-holo", card=cards[0], variant_type="holographic")
    db.add(variant)
    keyword = Keyword(slug="test-keyword", name="Test Keyword")
    cards[0].keywords.append(keyword)
    db.add(variant)
    db.flush()
    images = [
        CardImage(
            card=cards[0],
            url="https://example.invalid/card.png",
            width=100,
            height=140,
            source_name="private source",
            hosted_by_us=True,
        ),
        CardImage(card=cards[0], variant=variant, url="https://example.invalid/variant.png"),
    ]
    db.add_all(images)
    db.commit()
    return cards


@pytest.fixture
def catalogue(db_session):
    return seed(db_session)


def test_empty(client):
    r = client.get("/v1/cards")
    assert r.status_code == 200
    assert r.json() == {
        "data": [],
        "pagination": {
            "page": 1,
            "limit": 50,
            "total": 0,
            "pages": 0,
            "has_next": False,
            "has_previous": False,
        },
    }


def test_one_card(client, db_session):
    st = CardSet(public_id="test-only", name="Test Only")
    db_session.add(Card(public_id="TEST-ONLY", set=st, card_number="001", name="Test Only"))
    db_session.commit()
    r = client.get("/v1/cards").json()
    assert [x["id"] for x in r["data"]] == ["TEST-ONLY"]
    assert r["pagination"]["total"] == 1


@pytest.mark.parametrize(
    "query,ids",
    [
        ("", ["TEST-001", "TEST-B01", "TEST-A03", "TEST-002"]),
        ("name=Test Character Alpha", ["TEST-001", "TEST-B01"]),
        ("name=haracter", ["TEST-001", "TEST-B01", "TEST-A03", "TEST-002"]),
        ("name=aLpHa", ["TEST-001", "TEST-B01"]),
        ("set=TEST-SET-ALPHA", ["TEST-001", "TEST-A03", "TEST-002"]),
        ("number=1", ["TEST-001", "TEST-B01"]),
        ("name=alpha&set=test-set-alpha", ["TEST-001"]),
        ("set=test-set-beta&number=1", ["TEST-B01"]),
        ("name=absent", []),
        ("set=absent", []),
        ("number=01", []),
        ("name=%25", []),
        ("name=_", []),
        ("name=' OR 1=1 --", []),
    ],
)
def test_filters(client, catalogue, query, ids):
    r = client.get("/v1/cards?" + query)
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["data"]] == ids
    assert r.json()["pagination"]["total"] == len(ids)


@pytest.mark.parametrize(
    "field,asc_ids,desc_ids",
    [
        ("number", [0, 3, 2, 1], [1, 2, 0, 3]),
        ("name", [0, 3, 1, 2], [2, 1, 0, 3]),
        ("rarity", [2, 0, 3, 1], [0, 3, 2, 1]),
        ("set", [0, 1, 2, 3], [3, 0, 1, 2]),
        ("release_date", [0, 1, 2, 3], [0, 1, 2, 3]),
    ],
)
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sorting(client, catalogue, field, asc_ids, desc_ids, direction):
    expected = asc_ids if direction == "asc" else desc_ids
    r = client.get(f"/v1/cards?sort={field}&order={direction}")
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["data"]] == [catalogue[i].public_id for i in expected]


@pytest.mark.parametrize(
    "query,status,code",
    [
        ("limit=101", 400, "INVALID_PAGINATION"),
        ("limit=0", 400, "INVALID_PAGINATION"),
        ("page=0", 400, "INVALID_PAGINATION"),
        ("page=-1", 400, "INVALID_PAGINATION"),
        ("page=abc", 422, None),
        ("limit=abc", 422, None),
        ("sort=invalid", 400, "INVALID_SORT"),
        ("order=invalid", 400, "INVALID_SORT"),
    ],
)
def test_invalid(client, query, status, code):
    r = client.get("/v1/cards?" + query)
    assert r.status_code == status
    if code:
        assert set(r.json()) == {"error"}
        assert r.json()["error"]["code"] == code


@pytest.mark.parametrize(
    "page,limit,expected,pages", [(1, 50, 4, 1), (1, 100, 4, 1), (2, 1, 1, 4), (9, 2, 0, 2)]
)
def test_pagination(client, catalogue, page, limit, expected, pages):
    data = client.get(f"/v1/cards?page={page}&limit={limit}").json()
    assert len(data["data"]) == expected
    assert data["pagination"] == {
        "page": page,
        "limit": limit,
        "total": 4,
        "pages": pages,
        "has_next": page < pages,
        "has_previous": page > 1,
    }


def test_filtered_pagination(client, catalogue):
    data = client.get("/v1/cards?set=test-set-alpha&limit=1&page=2").json()
    assert data["pagination"]["total"] == 3
    assert data["data"][0]["id"] == "TEST-A03"


def assert_private_fields_absent(value):
    if isinstance(value, dict):
        assert not (
            {
                "public_id",
                "set_id",
                "card_id",
                "variant_id",
                "source_name",
                "source_url",
                "hosted_by_us",
                "created_at",
                "updated_at",
            }
            & value.keys()
        )
        for v in value.values():
            assert_private_fields_absent(v)
    elif isinstance(value, list):
        for v in value:
            assert_private_fields_absent(v)


@pytest.mark.parametrize("detail", [False, True])
def test_shapes_and_image_separation(client, catalogue, detail):
    r = client.get("/v1/cards/TEST-001" if detail else "/v1/cards?number=1&set=test-set-alpha")
    assert r.status_code == 200
    data = r.json() if detail else r.json()["data"][0]
    assert set(data) == (DETAIL if detail else SUMMARY)
    assert data["id"] == "TEST-001"
    assert data["set"] == {
        "id": "test-set-alpha",
        "code": "TSTA",
        "name": "Test Set Alpha",
        "edition": "Test Edition",
    }
    assert data["images"] == [
        {"type": "front", "url": "https://example.invalid/card.png", "width": 100, "height": 140}
    ]
    assert data["subtitle"] is None and data["type"] is None
    if detail:
        for key in ("chakra", "power", "faction", "ability_text", "flavor_text", "artist"):
            assert key in data and data[key] is None
        assert data["keywords"] == [{"slug": "test-keyword", "name": "Test Keyword"}]
        v = data["variants"][0]
        assert v == {
            "id": "TEST-001-holo",
            "type": "holographic",
            "finish": None,
            "rarity": None,
            "collector_number": None,
            "language": "EN",
            "edition": None,
            "source_variant": None,
            "card_version": None,
            "stamp": None,
            "serial_numbered": False,
            "serial_total": None,
            "images": [
                {
                    "type": "front",
                    "url": "https://example.invalid/variant.png",
                    "width": None,
                    "height": None,
                }
            ],
        }
    assert_private_fields_absent(data)
    assert str(catalogue[0].id) not in r.text
    assert str(catalogue[0].set_id) not in r.text


@pytest.mark.parametrize("lookup", ["does-not-exist", "uuid"])
def test_missing_and_internal_uuid(client, catalogue, lookup):
    if lookup == "uuid":
        lookup = str(catalogue[0].id)
    r = client.get("/v1/cards/" + lookup)
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "CARD_NOT_FOUND", "message": "Card not found."}}


def test_detail_empty_relationships(client, catalogue):
    data = client.get("/v1/cards/TEST-002").json()
    assert data["id"] == "TEST-002"
    assert data["images"] == data["variants"] == data["keywords"] == []


@pytest.mark.parametrize("detail", [False, True])
def test_query_growth_and_sql(client, db_session, detail):
    cards = seed(db_session)
    for i in range(12):
        if detail:
            v = CardVariant(public_id=f"TEST-V-{i}", card=cards[0], variant_type="test")
            db_session.add(v)
            db_session.flush()
            db_session.add(
                CardImage(card=cards[0], variant=v, url=f"https://example.invalid/v{i}.png")
            )
            cards[0].keywords.append(Keyword(slug=f"test-k-{i}", name=f"Test Keyword {i}"))
        else:
            st = CardSet(public_id=f"test-set-{i}", name=f"Test Set {i}")
            card = Card(public_id=f"TEST-M-{i}", set=st, card_number=str(i), name=f"Test Many {i}")
            db_session.add(CardImage(card=card, url=f"https://example.invalid/c{i}.png"))
    db_session.commit()
    db_session.expunge_all()
    sql = []

    def record(conn, cursor, statement, parameters, context, executemany):
        sql.append(statement.lower())

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        r = client.get("/v1/cards/TEST-001" if detail else "/v1/cards?name=Test&sort=set&limit=10")
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert r.status_code == 200
    assert len(sql) <= (7 if detail else 4), sql
    if detail:
        assert len(r.json()["variants"]) == 13
        assert all(v["images"] for v in r.json()["variants"])
        assert len(r.json()["keywords"]) == 13
    else:
        assert len(r.json()["data"]) == 10
        assert r.json()["pagination"]["total"] == 16
        assert any("count(" in q and "where" in q for q in sql)
        assert any("order by" in q and "limit" in q and "offset" in q for q in sql)
        assert not any("card_variants" in q or "keywords" in q for q in sql)


def test_openapi_cards_and_error_examples(client):
    doc = client.get("/openapi.json").json()
    for path in ("/v1/cards", "/v1/cards/{public_id}"):
        assert set(doc["paths"][path]) == {"get"}
        assert doc["paths"][path]["get"]["tags"] == ["Cards"]
    assert {p["name"] for p in doc["paths"]["/v1/cards"]["get"]["parameters"]} == {
        "page",
        "limit",
        "name",
        "set",
        "number",
        "sort",
        "order",
        "rarity",
        "type",
        "keyword",
        "variant",
        "language",
        "edition",
        "chakra_min",
        "chakra_max",
        "power_min",
        "power_max",
    }
    assert {
        "CardSummary",
        "CardDetail",
        "CardVariantResponse",
        "CardImageResponse",
        "KeywordResponse",
        "SetSummary",
        "PaginationMeta",
        "PaginatedCardsResponse",
        "ErrorResponse",
    } <= doc["components"]["schemas"].keys()
    for path, code in [
        ("/v1/sets/{public_id}", "SET_NOT_FOUND"),
        ("/v1/sets/{public_id}/cards", "SET_NOT_FOUND"),
        ("/v1/cards/{public_id}", "CARD_NOT_FOUND"),
    ]:
        assert (
            doc["paths"][path]["get"]["responses"]["404"]["content"]["application/json"]["example"][
                "error"
            ]["code"]
            == code
        )
    assert "example" not in doc["components"]["schemas"]["ErrorResponse"]
    assert "/v1/cards/random" in doc["paths"]


@pytest.mark.parametrize(
    "order,expected",
    [
        ("asc", ["TEST-001", "TEST-002", "TEST-A03", "TEST-NEW", "TEST-B01"]),
        ("desc", ["TEST-NEW", "TEST-001", "TEST-002", "TEST-A03", "TEST-B01"]),
    ],
)
def test_distinct_release_dates_with_null_last(client, catalogue, db_session, order, expected):
    st = CardSet(public_id="test-new", name="Test New", release_date=date(2026, 2, 1))
    db_session.add(Card(public_id="TEST-NEW", set=st, card_number="3", name="Test New"))
    db_session.commit()
    result = client.get(f"/v1/cards?sort=release_date&order={order}").json()
    assert [c["id"] for c in result["data"]] == expected


def test_populated_detail_fields(client, catalogue, db_session):
    card = catalogue[0]
    values = {
        "subtitle": "Test Subtitle",
        "card_type": "Character",
        "chakra": 4,
        "power": 5,
        "faction": "Test Village",
        "ability_text": "Fictional test ability",
        "flavor_text": "Fictional test flavor",
        "artist": "Test Artist",
    }
    for k, v in values.items():
        setattr(card, k, v)
    db_session.commit()
    data = client.get("/v1/cards/TEST-001").json()
    for k, v in values.items():
        assert data["type" if k == "card_type" else k] == v
