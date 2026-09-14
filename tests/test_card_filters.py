"""Advanced filtering contracts and query growth; fictional data only."""

from datetime import date

import pytest
from sqlalchemy import event

from app.models import Card, CardSet, CardVariant, Keyword


def seed_filters(db):
    sets = [
        CardSet(
            public_id="test-set-alpha",
            name="Test Set Alpha",
            language="EN",
            edition="Test Edition",
            release_date=date(2026, 1, 1),
        ),
        CardSet(
            public_id="test-set-beta",
            name="Test Set Beta",
            language="JP",
            edition="Test Second",
            release_date=date(2026, 2, 1),
        ),
        CardSet(public_id="test-set-null", name="Test Set Null", language="EN"),
    ]
    db.add_all(sets)
    db.flush()
    cards = [
        Card(
            public_id=f"TEST6-{i}",
            set=sets[st],
            card_number=num,
            name=name,
            rarity=rarity,
            card_type=kind,
            chakra=chakra,
            power=power,
        )
        for i, st, num, name, rarity, kind, chakra, power in [
            (1, 0, "1", "Test Alpha", "Rare", "Character", 2, 3),
            (2, 0, "10", "Test Beta", "Rare", "Character", 5, 8),
            (3, 1, "2", "Test Gamma", "Common", "Event", 0, 0),
            (4, 2, "3", "Test Null", None, None, None, None),
            (5, 1, "1", "Test Alpha", "Rare", "Event", 3, 5),
        ]
    ]
    db.add_all(cards)
    db.flush()
    keywords = [
        Keyword(slug="test-keyword", name="Test Keyword"),
        Keyword(slug="TEST-KEYWORD", name="Test Upper Keyword"),
        Keyword(slug="test-other", name="Test Other"),
    ]
    cards[0].keywords.extend(keywords)
    cards[1].keywords.append(keywords[0])
    cards[2].keywords.append(keywords[2])
    cards[4].keywords.append(keywords[0])
    for i in range(3):
        db.add(
            CardVariant(
                public_id=f"TEST6-V-{i}",
                card=cards[0],
                variant_type="holographic",
                language="JP",
                edition="Variant Edition",
            )
        )
    db.add(CardVariant(public_id="TEST6-V-3", card=cards[2], variant_type="normal", language="EN"))
    db.add(
        CardVariant(public_id="TEST6-V-4", card=cards[4], variant_type="holographic", language="EN")
    )
    db.commit()
    return cards


@pytest.fixture
def advanced(db_session):
    return seed_filters(db_session)


# Expected indices in default lexical number / public-ID ordering.
CASES = [
    ({"rarity": "Rare"}, [1, 5, 2]),
    ({"rarity": "rArE"}, [1, 5, 2]),
    ({"rarity": "unknown"}, []),
    ({"type": "Character"}, [1, 2]),
    ({"type": "cHaRaCtEr"}, [1, 2]),
    ({"type": "unknown"}, []),
    ({"keyword": "test-keyword"}, [1, 5, 2]),
    ({"keyword": "TEST-KEYWORD"}, [1, 5, 2]),
    ({"keyword": "absent"}, []),
    ({"keyword": "test-other"}, [1, 3]),
    ({"variant": "holographic"}, [1, 5]),
    ({"variant": "HOLOGRAPHIC"}, [1, 5]),
    ({"variant": "unknown"}, []),
    ({"language": "EN"}, [1, 2, 4]),
    ({"language": "en"}, [1, 2, 4]),
    ({"language": "JP"}, [5, 3]),
    ({"edition": "Test Edition"}, [1, 2]),
    ({"edition": "test edition"}, [1, 2]),
    ({"edition": "Test Second"}, [5, 3]),
    ({"edition": "Variant Edition"}, []),
    ({"chakra_min": 2}, [1, 5, 2]),
    ({"chakra_max": 3}, [1, 5, 3]),
    ({"chakra_min": 2, "chakra_max": 3}, [1, 5]),
    ({"chakra_min": 2, "chakra_max": 2}, [1]),
    ({"chakra_max": 0}, [3]),
    ({"chakra_min": 0}, [1, 5, 2, 3]),
    ({"power_min": 3}, [1, 5, 2]),
    ({"power_max": 5}, [1, 5, 3]),
    ({"power_min": 3, "power_max": 5}, [1, 5]),
    ({"power_min": 3, "power_max": 3}, [1]),
    ({"power_max": 0}, [3]),
    ({"power_min": 0}, [1, 5, 2, 3]),
    ({"rarity": "Rare", "type": "Character"}, [1, 2]),
    ({"set": "test-set-alpha", "rarity": "Rare"}, [1, 2]),
    ({"set": "test-set-alpha", "number": "1"}, [1]),
    ({"set": "test-set-alpha", "variant": "holographic"}, [1]),
    ({"set": "test-set-alpha", "keyword": "test-keyword"}, [1, 2]),
    ({"rarity": "Rare", "keyword": "test-keyword"}, [1, 5, 2]),
    ({"variant": "holographic", "keyword": "test-keyword"}, [1, 5]),
    ({"language": "EN", "edition": "Test Edition"}, [1, 2]),
    ({"rarity": "Rare", "type": "Character", "variant": "holographic"}, [1]),
    (
        {
            "set": "test-set-alpha",
            "rarity": "Rare",
            "keyword": "test-keyword",
            "variant": "holographic",
        },
        [1],
    ),
    (
        {
            "name": "Alpha",
            "set": "test-set-alpha",
            "rarity": "Rare",
            "type": "Character",
            "chakra_min": 2,
            "power_min": 3,
        },
        [1],
    ),
    ({"language": "EN", "variant": "normal"}, []),
    ({"rarity": "' OR 1=1 --"}, []),
    ({"keyword": "%_test"}, []),
    ({"variant": "'; DROP TABLE cards; --"}, []),
    ({"rarity": "Ra%"}, []),
    ({"type": "Char_cter"}, []),
    ({"edition": "Test%"}, []),
    ({"language": "E%"}, []),
]


@pytest.mark.parametrize("params,expected", CASES)
def test_filter_cases(client, advanced, params, expected):
    r = client.get("/v1/cards", params=params)
    assert r.status_code == 200
    data = r.json()
    assert [c["id"] for c in data["data"]] == [f"TEST6-{i}" for i in expected]
    assert data["pagination"]["total"] == len(expected)
    for c in data["data"]:
        assert "keywords" not in c and "variants" not in c


INVALID = [
    ({key: -1}, f"{key} must be greater than or equal to 0.")
    for key in ("chakra_min", "chakra_max", "power_min", "power_max")
] + [
    ({"chakra_min": 5, "chakra_max": 2}, "chakra_min cannot be greater than chakra_max."),
    ({"power_min": 5, "power_max": 2}, "power_min cannot be greater than power_max."),
]


@pytest.mark.parametrize("params,message", INVALID)
def test_invalid_ranges(client, params, message):
    r = client.get("/v1/cards", params=params)
    assert r.status_code == 400
    assert r.json() == {"error": {"code": "INVALID_FILTER", "message": message}}


@pytest.mark.parametrize("key", ["chakra_min", "chakra_max", "power_min", "power_max"])
def test_malformed_ranges(client, key):
    assert client.get("/v1/cards", params={key: "abc"}).status_code == 422


@pytest.mark.parametrize("page,ids", [(1, [1]), (2, [5]), (3, [])])
def test_unique_filtered_pagination(client, advanced, page, ids):
    r = client.get(
        "/v1/cards",
        params={"keyword": "test-keyword", "variant": "holographic", "page": page, "limit": 1},
    ).json()
    assert [c["id"] for c in r["data"]] == [f"TEST6-{i}" for i in ids]
    assert r["pagination"] == {
        "page": page,
        "limit": 1,
        "total": 2,
        "pages": 2,
        "has_next": page < 2,
        "has_previous": page > 1,
    }


@pytest.mark.parametrize(
    "sort,asc,desc",
    [
        ("number", [1, 5, 2], [2, 1, 5]),
        ("name", [1, 5, 2], [2, 1, 5]),
        ("rarity", [1, 2, 5], [1, 2, 5]),
        ("set", [1, 2, 5], [5, 1, 2]),
        ("release_date", [1, 2, 5], [5, 1, 2]),
    ],
)
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_filtered_sorting(client, advanced, sort, asc, desc, order):
    r = client.get("/v1/cards", params={"rarity": "Rare", "sort": sort, "order": order}).json()
    assert [c["id"] for c in r["data"]] == [f"TEST6-{i}" for i in (asc if order == "asc" else desc)]


@pytest.mark.parametrize(
    "params",
    [
        {"keyword": "test-keyword"},
        {"variant": "holographic"},
        {"keyword": "test-keyword", "variant": "holographic"},
    ],
)
def test_constant_query_growth(client, db_session, advanced, params):
    def measure():
        db_session.expunge_all()
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())

        engine = db_session.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            r = client.get("/v1/cards", params=params)
        finally:
            event.remove(engine, "before_cursor_execute", record)
        assert r.status_code == 200
        assert any("exists" in s and "count(" in s for s in statements)
        # Relationship tables belong only to EXISTS predicates in parent/count SQL.
        assert not any("from keywords" in s and "from cards" not in s for s in statements)
        assert not any("from card_variants" in s and "from cards" not in s for s in statements)
        assert all("keywords" not in c and "variants" not in c for c in r.json()["data"])
        return len(statements), r.json()["pagination"]["total"]

    initial_count, initial_total = measure()
    for i in range(16):
        st = CardSet(public_id=f"test-grow-{i}", name=f"Test Growth {i}")
        card = Card(public_id=f"TEST6-G-{i}", set=st, card_number=str(i), name=f"Test Growth {i}")
        card.keywords.append(Keyword(slug=f"test-keyword-{i}", name="Test Other"))
        from sqlalchemy import select

        keyword = db_session.scalar(select(Keyword).where(Keyword.slug == "test-keyword"))
        card.keywords.append(keyword)
        db_session.add(card)
        db_session.flush()
        for j in range(3):
            db_session.add(
                CardVariant(public_id=f"TEST6-GV-{i}-{j}", card=card, variant_type="holographic")
            )
    db_session.commit()
    grown_count, grown_total = measure()
    assert grown_total == initial_total + 16
    assert grown_count <= 4 and grown_count <= initial_count + 1


def test_openapi_advanced(client):
    doc = client.get("/openapi.json").json()
    op = doc["paths"]["/v1/cards"]["get"]
    names = {p["name"] for p in op["parameters"]}
    assert names == {
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
    assert all(p.get("description") for p in op["parameters"])
    examples = op["responses"]["400"]["content"]["application/json"]["examples"]
    assert {"pagination", "sort", "chakra_range", "power_range", "negative_stat"} <= examples.keys()
    for key in ["chakra_range", "power_range", "negative_stat"]:
        assert examples[key]["value"]["error"]["code"] == "INVALID_FILTER"
    for path, code in [
        ("/v1/sets/{public_id}", "SET_NOT_FOUND"),
        ("/v1/cards/{public_id}", "CARD_NOT_FOUND"),
    ]:
        assert (
            doc["paths"][path]["get"]["responses"]["404"]["content"]["application/json"]["example"][
                "error"
            ]["code"]
            == code
        )
