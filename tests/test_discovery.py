"""Phase 7 discovery contracts; all fixtures are fictional."""

from datetime import date

import pytest
from sqlalchemy import event

from app.models import Card, CardImage, CardSet, CardVariant, Keyword
from app.utils.slugs import rarity_slug
from tests.test_cards_routes import DETAIL, SUMMARY, assert_private_fields_absent


def seed_discovery(db):

    st = CardSet(
        public_id="test-set-alpha",
        name="Test Set Alpha",
        code="SETCODE7",
        edition="Test Edition",
        release_date=date(2026, 1, 1),
    )

    other = CardSet(public_id="test-set-beta", name="Test Set Beta", code="BETA7")

    cards = [
        Card(
            public_id="TEST-001",
            set=st,
            card_number="C701",
            name="Test Character Alpha",
            subtitle="SubtitleNeedle",
            rarity="Rare",
        ),
        Card(
            public_id="TEST-002",
            set=st,
            card_number="10",
            name="Test Character Beta",
            rarity="Rare",
        ),
        Card(
            public_id="TEST-A03",
            set=other,
            card_number="2",
            name="Test Character Gamma",
            rarity=None,
        ),
    ]

    key = Keyword(slug="test-keyword", name="Test Keyword Needle")

    zero = Keyword(slug="test-unused", name="Test Unused")

    cards[0].keywords.append(key)
    cards[1].keywords.append(key)

    db.add_all(cards + [zero])
    db.flush()

    variant = CardVariant(public_id="TEST-V7", card=cards[0], variant_type="test-holo")

    db.add(variant)
    db.flush()

    db.add_all(
        [
            CardImage(
                card=cards[0],
                url="https://example.invalid/direct.png",
                source_name="private",
                hosted_by_us=True,
            ),
            CardImage(card=cards[0], variant=variant, url="https://example.invalid/variant.png"),
        ]
    )

    db.commit()

    return cards


@pytest.fixture
def discovery(db_session):

    return seed_discovery(db_session)


@pytest.mark.parametrize("path", ["/v1/rarities", "/v1/keywords"])
def test_empty_metadata(client, path):

    r = client.get(path)
    assert r.status_code == 200 and r.json() == []


def test_random_empty_and_randomish(client):

    r = client.get("/v1/cards/random")

    assert r.status_code == 404 and r.json() == {
        "error": {"code": "CARD_NOT_FOUND", "message": "No cards available."}
    }

    r = client.get("/v1/cards/randomish")

    assert r.status_code == 404 and r.json() == {
        "error": {"code": "CARD_NOT_FOUND", "message": "Card not found."}
    }


def test_random_single_full_detail(client, db_session):

    cards = seed_discovery(db_session)

    db_session.delete(cards[1])
    db_session.delete(cards[2])
    db_session.commit()

    for _ in range(2):
        r = client.get("/v1/cards/random")
        assert r.status_code == 200

        data = r.json()
        assert data["id"] == "TEST-001" and set(data) == DETAIL

        assert data["set"]["id"] == "test-set-alpha"

        assert data["keywords"] == [{"slug": "test-keyword", "name": "Test Keyword Needle"}]

        assert data["variants"][0]["id"] == "TEST-V7"

        assert [x["url"] for x in data["images"]] == ["https://example.invalid/direct.png"]

        assert [x["url"] for x in data["variants"][0]["images"]] == [
            "https://example.invalid/variant.png"
        ]

        assert_private_fields_absent(data)

        assert str(cards[0].id) not in r.text


def test_random_multiple_and_static_precedence(client, discovery, db_session):

    # Even a literal public ID 'random' must not shadow the static handler.

    r = client.get("/v1/cards/random")

    assert r.status_code == 200 and r.json()["id"] in {c.public_id for c in discovery}

    assert set(r.json()) == DETAIL

    card = discovery[0]
    card.public_id = "randomish"
    db_session.commit()

    assert client.get("/v1/cards/randomish").json()["id"] == "randomish"


@pytest.mark.parametrize(
    "name,slug",
    [
        ("Rare", "rare"),
        ("Super Rare", "super-rare"),
        ("Test / Rare", "test-rare"),
        ("  Test  /__ Rare-- ", "test-rare"),
        ("?!", ""),
        ("RARE", "rare"),
        ("Élite Rare", "élite-rare"),
    ],
)
def test_slug(name, slug):

    assert rarity_slug(name) == slug and rarity_slug(name) == rarity_slug(name)


def test_rarity_counts_case_collision_order(client, discovery, db_session):

    for i, rarity in enumerate(["rare", "Test / Rare", "Test Rare"]):
        db_session.add(
            Card(
                public_id=f"TEST-R-{i}",
                set=discovery[0].set,
                card_number=f"R{i}",
                name="Test Rarity",
                rarity=rarity,
            )
        )

    db_session.commit()

    data = client.get("/v1/rarities").json()

    assert data == [
        {"name": "Rare", "slug": "rare", "card_count": 2},
        {"name": "Test / Rare", "slug": "test-rare", "card_count": 1},
        {"name": "Test Rare", "slug": "test-rare", "card_count": 1},
        {"name": "rare", "slug": "rare", "card_count": 1},
    ]

    assert_private_fields_absent(data)


def test_one_rarity(client, discovery):

    assert client.get("/v1/rarities").json() == [{"name": "Rare", "slug": "rare", "card_count": 2}]


def test_keyword_counts_zero_ties(client, discovery, db_session):

    db_session.add(Keyword(slug="test-unused-a", name="Test Unused"))
    db_session.commit()

    data = client.get("/v1/keywords").json()

    assert data == [
        {"slug": "test-keyword", "name": "Test Keyword Needle", "card_count": 2},
        {"slug": "test-unused", "name": "Test Unused", "card_count": 0},
        {"slug": "test-unused-a", "name": "Test Unused", "card_count": 0},
    ]

    assert_private_fields_absent(data)


def test_one_zero_keyword(client, db_session):

    db_session.add(Keyword(slug="test-only", name="Test Only"))
    db_session.commit()

    assert client.get("/v1/keywords").json() == [
        {"slug": "test-only", "name": "Test Only", "card_count": 0}
    ]


@pytest.mark.parametrize(
    "slug,ids",
    [
        ("test-keyword", ["TEST-002", "TEST-001"]),
        ("TEST-KEYWORD", ["TEST-002", "TEST-001"]),
        ("test-unused", []),
    ],
)
def test_keyword_cards(client, discovery, slug, ids):

    r = client.get(f"/v1/keywords/{slug}/cards")
    assert r.status_code == 200

    assert [c["id"] for c in r.json()["data"]] == ids

    assert r.json()["pagination"]["total"] == len(ids)

    for card in r.json()["data"]:
        assert set(card) == SUMMARY
        assert_private_fields_absent(card)


def test_keyword_missing(client):

    r = client.get("/v1/keywords/absent/cards")
    assert r.status_code == 404

    assert r.json() == {"error": {"code": "KEYWORD_NOT_FOUND", "message": "Keyword not found."}}


@pytest.mark.parametrize(
    "query,status,code",
    [
        ("page=0", 400, "INVALID_PAGINATION"),
        ("limit=101", 400, "INVALID_PAGINATION"),
        ("sort=bad", 400, "INVALID_SORT"),
        ("order=bad", 400, "INVALID_SORT"),
        ("page=abc", 422, None),
    ],
)
def test_keyword_invalid(client, discovery, query, status, code):

    r = client.get("/v1/keywords/test-keyword/cards?" + query)
    assert r.status_code == status

    if code:
        assert r.json()["error"]["code"] == code


@pytest.mark.parametrize("sort", ["number", "name", "rarity", "set", "release_date"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_keyword_reuses_sorting(client, discovery, sort, order):

    params = {"sort": sort, "order": order, "limit": 1, "page": 2}

    a = client.get("/v1/keywords/test-keyword/cards", params=params)

    b = client.get("/v1/cards", params=dict(params, keyword="test-keyword"))

    assert a.status_code == 200 and a.json() == b.json()

    assert a.json()["pagination"]["total"] == 2


@pytest.mark.parametrize("query", [None, "", " ", "a", " a "])
def test_search_invalid_query(client, query):

    r = client.get("/v1/search", params={} if query is None else {"q": query})

    assert r.status_code == (422 if query is None else 400)

    if query is not None:
        assert r.json() == {
            "error": {
                "code": "INVALID_FILTER",
                "message": "Search query must contain at least 2 characters.",
            }
        }


@pytest.mark.parametrize(
    "q,kind,identifier",
    [
        ("Test Character Alpha", "card", "TEST-001"),
        ("TEST-001", "card", "TEST-001"),
        ("C701", "card", "TEST-001"),
        ("subtitleneedle", "card", "TEST-001"),
        ("Test Set Alpha", "set", "test-set-alpha"),
        ("test-set-alpha", "set", "test-set-alpha"),
        ("SETCODE7", "set", "test-set-alpha"),
        ("Test Keyword Needle", "keyword", "test-keyword"),
        ("test-keyword", "keyword", "test-keyword"),
        ("  tEsT-001  ", "card", "TEST-001"),
    ],
)
def test_search_fields(client, discovery, q, kind, identifier):

    r = client.get("/v1/search", params={"q": q})
    assert r.status_code == 200

    data = r.json()["data"]

    assert any(
        v["type"] == kind and v[kind]["slug" if kind == "keyword" else "id"] == identifier
        for v in data
    )

    assert_private_fields_absent(data)


def test_search_summary_direct_images_and_unique(client, discovery):

    data = client.get("/v1/search?q=test").json()["data"]

    ids = [(x["type"], x[x["type"]].get("id", x[x["type"]].get("slug"))) for x in data]

    assert len(ids) == len(set(ids)) == 7

    card = next(x["card"] for x in data if x["type"] == "card" and x["card"]["id"] == "TEST-001")

    assert set(card) == SUMMARY

    assert [i["url"] for i in card["images"]] == ["https://example.invalid/direct.png"]


@pytest.mark.parametrize("q", ["' OR 1=1 --", "%_", "'; DROP TABLE cards; --"])
def test_search_literal_security(client, discovery, q):

    assert client.get("/v1/search", params={"q": q}).json() == {"data": []}


def test_search_literal_positive(client, discovery, db_session):

    discovery[0].subtitle = "Literal %_ marker"
    db_session.commit()

    data = client.get("/v1/search", params={"q": "%_"}).json()["data"]

    assert len(data) == 1 and data[0]["card"]["id"] == "TEST-001"


def test_search_ranking(client, db_session):

    # Identifier > exact name > prefix > substring, then type, then alphabetic/ID.

    st = CardSet(public_id="need", name="ZZ Test Set")

    db_session.add(st)
    db_session.flush()

    for pid, name in [
        ("need", "ZZ Test Card"),
        ("test-exact", "need"),
        ("test-prefix-b", "need B"),
        ("test-prefix-a", "need A"),
        ("test-sub", "A need"),
    ]:
        db_session.add(Card(public_id=pid, set=st, card_number=pid, name=name))

    db_session.add(Keyword(slug="need", name="ZZ Test Keyword"))
    db_session.commit()

    data = client.get("/v1/search?q=need").json()["data"]

    actual = [(v["type"], v[v["type"]].get("id", v[v["type"]].get("slug"))) for v in data]

    assert actual == [
        ("card", "need"),
        ("set", "need"),
        ("keyword", "need"),
        ("card", "test-exact"),
        ("card", "test-prefix-a"),
        ("card", "test-prefix-b"),
        ("card", "test-sub"),
    ]

    assert client.get("/v1/search?q=need&limit=2").json()["data"] == data[:2]


@pytest.mark.parametrize("limit,expected", [(None, 20), (3, 3), (50, 50)])
def test_search_combined_limit(client, db_session, limit, expected):

    for i in range(22):
        st = CardSet(public_id=f"test-set-{i:02}", name=f"Test Set {i:02}")

        db_session.add(
            Card(
                public_id=f"test-card-{i:02}", set=st, card_number=str(i), name=f"Test Card {i:02}"
            )
        )

        db_session.add(Keyword(slug=f"test-key-{i:02}", name=f"Test Key {i:02}"))

    db_session.commit()

    params = {"q": "te"}

    if limit is not None:
        params["limit"] = limit

    data = client.get("/v1/search", params=params).json()["data"]

    assert len(data) == expected

    assert (
        len({(x["type"], x[x["type"]].get("id", x[x["type"]].get("slug"))) for x in data})
        == expected
    )


@pytest.mark.parametrize("limit,status", [(0, 400), (-1, 400), (51, 400), ("abc", 422)])
def test_search_invalid_limit(client, limit, status):

    r = client.get("/v1/search", params={"q": "test", "limit": limit})
    assert r.status_code == status

    if status == 400:
        assert r.json()["error"]["code"] == "INVALID_PAGINATION"


@pytest.mark.parametrize(
    "path,bound",
    [
        ("/v1/cards/random", 7),
        ("/v1/keywords/test-keyword/cards", 5),
        ("/v1/search?q=test&limit=50", 5),
        ("/v1/rarities", 2),
        ("/v1/keywords", 2),
    ],
)
def test_query_growth(client, db_session, path, bound):

    seed_discovery(db_session)

    def measure():

        db_session.expunge_all()
        sql = []

        def record(conn, cursor, statement, parameters, context, executemany):
            sql.append(statement.lower())

        engine = db_session.get_bind()
        event.listen(engine, "before_cursor_execute", record)

        try:
            r = client.get(path)

        finally:
            event.remove(engine, "before_cursor_execute", record)

        assert r.status_code == 200

        if path in ("/v1/rarities", "/v1/keywords"):
            assert any("count(" in q and "group by" in q for q in sql)

        if path.startswith("/v1/search"):
            assert sum("limit" in q for q in sql) >= 3

            assert not any("card_variants" in q or "card_keywords" in q for q in sql)

        return len(sql)

    before = measure()

    # Grow multiple cards/sets with direct images; random candidates all have variants.

    from sqlalchemy import select

    key = db_session.scalar(select(Keyword).where(Keyword.slug == "test-keyword"))

    for i in range(12):
        st = CardSet(public_id=f"test-grow-{i}", name=f"Test Growth {i}")

        card = Card(
            public_id=f"TEST-G-{i}",
            set=st,
            card_number=str(i),
            name=f"Test Growth {i}",
            rarity=f"Test Rarity {i}",
        )

        card.keywords.append(key)
        db_session.add(card)
        db_session.flush()

        db_session.add(CardImage(card=card, url="https://example.invalid/direct.png"))

        for j in range(8):
            v = CardVariant(public_id=f"TEST-GV-{i}-{j}", card=card, variant_type="test")

            db_session.add(v)
            db_session.flush()

            db_session.add(
                CardImage(card=card, variant=v, url="https://example.invalid/variant.png")
            )

    db_session.commit()

    after = measure()
    assert after <= bound and after <= before + 1


def test_openapi_discovery(client):

    doc = client.get("/openapi.json").json()

    for path, tag in [
        ("/v1/cards/random", "Cards"),
        ("/v1/rarities", "Metadata"),
        ("/v1/keywords", "Metadata"),
        ("/v1/keywords/{slug}/cards", "Metadata"),
        ("/v1/search", "Search"),
    ]:
        assert set(doc["paths"][path]) == {"get"}

        assert doc["paths"][path]["get"]["tags"] == [tag]

        assert (
            "schema" in doc["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]
        )

    assert {
        "SearchResponse",
        "CardSearchResult",
        "SetSearchResult",
        "KeywordSearchResult",
        "RarityCatalogItem",
        "KeywordCatalogItem",
    } <= doc["components"]["schemas"].keys()

    for path, code, msg in [
        ("/v1/cards/random", "CARD_NOT_FOUND", "No cards available."),
        ("/v1/keywords/{slug}/cards", "KEYWORD_NOT_FOUND", "Keyword not found."),
    ]:
        assert doc["paths"][path]["get"]["responses"]["404"]["content"]["application/json"][
            "example"
        ] == {"error": {"code": code, "message": msg}}

    assert (
        doc["paths"]["/v1/search"]["get"]["responses"]["400"]["content"]["application/json"][
            "examples"
        ]["query"]["value"]["error"]["code"]
        == "INVALID_FILTER"
    )


def test_random_many_relationships_batched(client, db_session):
    cards = seed_discovery(db_session)
    db_session.delete(cards[1])
    db_session.delete(cards[2])
    for i in range(12):
        v = CardVariant(public_id=f"TEST-RANDOM-V-{i}", card=cards[0], variant_type="test")
        db_session.add(v)
        db_session.flush()
        db_session.add(
            CardImage(card=cards[0], variant=v, url="https://example.invalid/variant.png")
        )
        cards[0].keywords.append(Keyword(slug=f"test-random-key-{i}", name="Test Random Keyword"))
    db_session.commit()
    db_session.expunge_all()
    sql = []

    def record(conn, cursor, statement, parameters, context, executemany):
        sql.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        r = client.get("/v1/cards/random")
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert r.status_code == 200 and r.json()["id"] == "TEST-001"
    assert len(r.json()["variants"]) == 13 and len(r.json()["keywords"]) == 13
    assert all(v["images"] for v in r.json()["variants"])
    assert len(sql) <= 7


def test_search_name_ties_use_public_identifier(client, db_session):
    st = CardSet(public_id="test-tie-set", name="Other Set")
    for pid in ["test-tie-b", "test-tie-a"]:
        db_session.add(Card(public_id=pid, set=st, card_number=pid, name="Equal Name"))
    db_session.commit()
    data = client.get("/v1/search?q=Equal").json()["data"]
    assert [x["card"]["id"] for x in data] == ["test-tie-a", "test-tie-b"]


def test_keyword_case_variants_do_not_duplicate_cards(client, discovery, db_session):
    discovery[0].keywords.append(Keyword(slug="TEST-KEYWORD", name="Test Upper"))
    db_session.commit()
    a = client.get("/v1/keywords/TeSt-KeYwOrD/cards").json()
    assert a["pagination"]["total"] == 2 and len(a["data"]) == 2
