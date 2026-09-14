"""Real localhost HTTP + configured PostgreSQL full-system audit, fictional data only."""

import copy
import json
import socket
import threading
import time
import uuid
from pathlib import Path

import httpx
import uvicorn
from pydantic import TypeAdapter
from sqlalchemy import delete, event, select, text

from app.database import Base, engine
from app.main import app
from app.models.keyword import card_keywords
from app.schemas.card import CardDetail
from app.schemas.metadata import KeywordCatalogItem, RarityCatalogItem
from app.schemas.pagination import PaginatedCardsResponse, PaginatedSetsResponse
from app.schemas.search import SearchResponse
from app.schemas.set import SetDetail
from importer import runner
from importer.planner import TABLES


def snapshot():
    with engine.connect() as c:
        return {
            t.name: sorted(repr(dict(r)) for r in c.execute(select(t)).mappings())
            for t in Base.metadata.sorted_tables
        }


def main():
    prefix = "p9-" + uuid.uuid4().hex[:10]
    data = {"source": {"name": prefix, "retrieved_at": "2026-09-14T00:00:00Z"}, "sets": []}
    for s in range(10):
        st = {
            "id": f"{prefix}-set-{s}",
            "name": f"Fictional {prefix} Set {s}",
            "language": "EN" if s % 2 == 0 else "FR",
            "edition": f"Edition {s % 2}",
            "cards": [],
        }
        for n in range(200):
            ident = f"{prefix}-{s}-{n:03}"
            st["cards"].append(
                {
                    "id": ident,
                    "number": f"{n:03}",
                    "name": f"Fictional {prefix} Card {s} {n}",
                    "subtitle": None,
                    "type": "Character" if n % 2 == 0 else "Event",
                    "rarity": f"{prefix}-rare-{n % 3}",
                    "chakra": n % 8,
                    "power": n % 12,
                    "keywords": [
                        {
                            "slug": f"{prefix}-kw-{n % 5}",
                            "name": f"Fictional {prefix} Keyword {n % 5}",
                        }
                    ],
                    "variants": [
                        {
                            "id": ident + "-v",
                            "type": f"{prefix}-holo",
                            "language": st["language"],
                            "edition": st["edition"],
                            "images": [{"url": f"https://example.invalid/{ident}-v.png"}],
                        }
                    ],
                    "images": [
                        {"url": f"https://example.invalid/{ident}.png", "width": 300, "height": 420}
                    ],
                }
            )
        data["sets"].append(st)
    tracked = {k: set() for k in TABLES}
    original = runner.apply_plan

    def apply(c, plan):
        for k, rows in plan.inserts.items():
            tracked[k].update(r["id"] for r in rows)
        original(c, plan)

    runner.apply_plan = apply
    baseline = snapshot()
    result = {"checks": {}, "performance": {}, "plans": {}}

    def run(payload, **kwargs):
        r = runner.run_import(engine, json.dumps(payload), **kwargs)
        assert r["status"] == "success", r["errors"]
        return r

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            assert server.started
            with engine.connect() as c:
                assert (
                    c.execute(text("SELECT version_num FROM alembic_version")).scalar()
                    == "8b41e2a9c730"
                )
                constraints = {
                    r[0]: r[1]
                    for r in c.execute(
                        text(
                            "SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace='public'::regnamespace"
                        )
                    )
                }
                assert (
                    "fk_card_images_variant_card_owner" in constraints
                    and "uq_card_variants_id_card_id" in constraints
                )
                assert "fk_card_images_variant_id_card_variants" not in constraints
                assert "fk_card_images_card_id_cards" in constraints
                result["constraints"] = constraints
            run(data, dry_run=True)
            assert snapshot() == baseline
            result["initial_import"] = run(data)["counts"]
            a = data["sets"][0]["cards"][0]
            sid = data["sets"][0]["id"]
            cid = a["id"]
            kw = a["keywords"][0]["slug"]
            routes = {
                "/health": None,
                "/ready": None,
                "/v1/sets": PaginatedSetsResponse,
                f"/v1/sets/{sid}": SetDetail,
                f"/v1/sets/{sid}/cards": PaginatedCardsResponse,
                "/v1/cards": PaginatedCardsResponse,
                f"/v1/cards/{cid}": CardDetail,
                "/v1/cards/random": CardDetail,
                "/v1/rarities": list[RarityCatalogItem],
                "/v1/keywords": list[KeywordCatalogItem],
                f"/v1/keywords/{kw}/cards": PaginatedCardsResponse,
                f"/v1/search?q={prefix}": SearchResponse,
            }

            def get(path):
                response = client.get(path)
                assert response.status_code == 200, (path, response.text)
                return response.json()

            before_reads = snapshot()
            for path, model in routes.items():
                body = get(path)
                if model:
                    TypeAdapter(model).validate_python(body)
                assert not any(
                    f'"{key}"' in json.dumps(body)
                    for key in (
                        "hosted_by_us",
                        "card_id",
                        "variant_id",
                        "source_name",
                        "content_hash",
                        "entity_id",
                    )
                )
            detail = get(f"/v1/cards/{cid}")
            assert len(detail["images"]) == len(detail["variants"][0]["images"]) == 1
            assert len(get(f"/v1/sets/{sid}/cards")["data"][0]["images"]) == 1
            assert get(f"/v1/sets/{data['sets'][1]['id']}")["language"] == "FR"
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                for path in ("/v1/cards", f"/v1/cards/{cid}", "/v1/sets", "/v1/keywords"):
                    assert (
                        client.request(method, path, json={"name": "Fictional"}).status_code == 405
                    )
            assert snapshot() == before_reads
            result["checks"]["http_all_routes_methods_serialization_read_only"] = True
            for path in (
                "/v1/sets",
                f"/v1/sets/{sid}/cards",
                "/v1/cards",
                f"/v1/keywords/{kw}/cards",
            ):
                body = get(path + "?page=1&limit=1")
                assert body["pagination"]["has_next"] and len(body["data"]) == 1
                body = get(path + "?page=999999&limit=100")
                assert (
                    body["data"] == []
                    and body["pagination"]["has_previous"]
                    and not body["pagination"]["has_next"]
                )
            assert (
                get(f"/v1/cards?set={sid}&sort=number&order=asc&limit=2")["data"][0]["number"]
                == "000"
            )
            for params in (
                f"rarity={a['rarity']}",
                f"keyword={kw}",
                f"variant={prefix}-holo",
                "language=FR",
                "edition=Edition%201",
                "type=Event",
                "chakra_min=2&chakra_max=4&power_min=1&power_max=10",
            ):
                assert get("/v1/cards?" + params)["data"]
            errors = {
                "/v1/sets/fictional-not-present": (404, "SET_NOT_FOUND"),
                "/v1/cards/fictional-not-present": (404, "CARD_NOT_FOUND"),
                "/v1/cards/randomish": (404, "CARD_NOT_FOUND"),
                "/v1/keywords/fictional-not-present/cards": (404, "KEYWORD_NOT_FOUND"),
                "/v1/cards?page=0": (400, "INVALID_PAGINATION"),
                "/v1/cards?sort=hostile": (400, "INVALID_SORT"),
                "/v1/cards?chakra_min=-1": (400, "INVALID_FILTER"),
            }
            for path, (status, code) in errors.items():
                response = client.get(path)
                assert response.status_code == status and response.json()["error"]["code"] == code
            assert client.get("/v1/cards?page=abc").status_code == 422
            spec = get("/openapi.json")
            assert spec["openapi"].startswith("3.1") and len(spec["paths"]) == 12
            result["checks"]["pagination_filters_sort_errors_openapi"] = True
            with engine.connect() as c:
                old_id = c.execute(
                    select(TABLES["cards"].c.id).where(TABLES["cards"].c.public_id == cid)
                ).scalar()
            old_keywords = get("/v1/keywords")
            a.update(
                name=f"UniqueUpdated{prefix}",
                rarity=f"{prefix}-updated",
                chakra=19,
                power=20,
                keywords=[],
            )
            a["variants"][0]["finish"] = "updated-finish"
            a["images"][0]["width"] = 333
            run(data)
            d = get(f"/v1/cards/{cid}")
            assert (
                d["name"] == a["name"]
                and d["rarity"] == a["rarity"]
                and d["chakra"] == 19
                and d["power"] == 20
            )
            assert (
                d["keywords"] == []
                and d["images"][0]["width"] == 333
                and d["variants"][0]["finish"] == "updated-finish"
            )
            assert get(f"/v1/search?q={a['name']}")["data"][0]["card"]["id"] == cid
            assert (
                next(x for x in get("/v1/keywords") if x["slug"] == kw)["card_count"]
                == next(x for x in old_keywords if x["slug"] == kw)["card_count"] - 1
            )
            assert (
                next(x for x in get("/v1/rarities") if x["name"] == a["rarity"])["card_count"] == 1
            )
            with engine.connect() as c:
                assert (
                    c.execute(
                        select(TABLES["cards"].c.id).where(TABLES["cards"].c.public_id == cid)
                    ).scalar()
                    == old_id
                )
            stable = {path: get(path) for path in routes if path != "/v1/cards/random"}
            statements = []

            def capture(conn, cursor, statement, parameters, context, many):
                statements.append((statement, parameters))

            event.listen(engine, "before_cursor_execute", capture)
            run(data)
            event.remove(engine, "before_cursor_execute", capture)
            assert not any(
                s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s, p in statements
            )
            assert all(stable[path] == get(path) for path in stable)
            result["checks"]["updated_api_stable_uuid_counts_search_repeat_no_dml"] = True
            omitted = copy.deepcopy(data)
            omitted["sets"][0]["cards"][0].update(variants=[], images=[])
            run(omitted)
            assert get(f"/v1/cards/{cid}") == d
            before = snapshot()

            def fail(c, plan):
                apply(c, plan)
                raise RuntimeError("fictional rollback")

            runner.apply_plan = fail
            broken = copy.deepcopy(data)
            broken["sets"][0]["cards"][0]["name"] = "RolledBack"
            assert runner.run_import(engine, broken)["transaction"] == "rolled_back"
            runner.apply_plan = apply
            assert snapshot() == before
            result["checks"]["omissions_rollback"] = True
            from importer.planner import TYPES

            with engine.connect() as connection:
                for kind, entity_type in TYPES.items():
                    records = TABLES["provenance"]
                    missing = connection.execute(
                        select(records.c.id)
                        .outerjoin(TABLES[kind], records.c.entity_id == TABLES[kind].c.id)
                        .where(
                            records.c.entity_type == entity_type,
                            records.c.source_name == prefix,
                            TABLES[kind].c.id.is_(None),
                        )
                    ).first()
                    assert missing is None
                source_a_before = list(
                    connection.execute(
                        select(TABLES["provenance"]).where(
                            TABLES["provenance"].c.source_name == prefix
                        )
                    ).mappings()
                )
            second_source = copy.deepcopy(data)
            second_source["sets"] = second_source["sets"][:1]
            second_source["sets"][0]["cards"] = second_source["sets"][0]["cards"][:1]
            second_source["source"]["name"] = prefix + "-second"
            assert run(second_source)["counts"]["provenance"]["created"] > 0
            with engine.connect() as connection:
                source_a_after = list(
                    connection.execute(
                        select(TABLES["provenance"]).where(
                            TABLES["provenance"].c.source_name == prefix
                        )
                    ).mappings()
                )
                assert source_a_before == source_a_after
            result["checks"]["provenance_no_orphans_independent_sources"] = True

            # Uncommitted importer changes must be invisible to a separate HTTP session.
            before_name = get(f"/v1/cards/{cid}")["name"]

            def observe_before_commit(connection, plan):
                apply(connection, plan)
                assert get(f"/v1/cards/{cid}")["name"] == before_name

            runner.apply_plan = observe_before_commit
            during = copy.deepcopy(data)
            during["sets"][0]["cards"][0]["name"] = before_name + "Committed"
            run(during)
            runner.apply_plan = apply
            assert get(f"/v1/cards/{cid}")["name"] == before_name + "Committed"
            run(data)
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=4) as pool:
                assert all(pool.map(lambda _: get(f"/v1/cards/{cid}")["id"] == cid, range(8)))
            # Verify the actual importer's advisory key blocks a second connection
            # and is released by transaction rollback.
            with engine.connect() as first, engine.connect() as second:
                transaction = first.begin()
                first.execute(text("SELECT pg_advisory_xact_lock(807008)"))
                assert (
                    second.execute(text("SELECT pg_try_advisory_xact_lock(807008)")).scalar()
                    is False
                )
                second.rollback()
                transaction.rollback()
                assert (
                    second.execute(text("SELECT pg_try_advisory_xact_lock(807008)")).scalar()
                    is True
                )
                second.rollback()
            result["checks"]["concurrent_gets_mvcc_visibility_advisory_scope"] = True
            for path in (
                "/v1/cards?page=1&limit=50",
                f"/v1/cards?rarity={prefix}-rare-1",
                f"/v1/cards?keyword={kw}",
                f"/v1/cards?variant={prefix}-holo",
                f"/v1/search?q={prefix}",
                "/v1/rarities",
                "/v1/keywords",
                "/v1/cards/random",
                f"/v1/cards/{cid}",
                f"/v1/sets/{sid}",
            ):
                statements = []
                event.listen(engine, "before_cursor_execute", capture)
                start = time.perf_counter()
                body = get(path)
                elapsed = time.perf_counter() - start
                event.remove(engine, "before_cursor_execute", capture)
                count = (
                    len(body)
                    if isinstance(body, list)
                    else len(body["data"])
                    if "data" in body
                    else 1
                )
                result["performance"][path] = {
                    "latency_ms": round(elapsed * 1000, 2),
                    "sql_statements": len(statements),
                    "returned_items": count,
                }
                with engine.connect() as c:
                    plans = []
                    for sql, params in statements[:2]:
                        if sql.lstrip().upper().startswith("SELECT"):
                            plans.append(
                                c.exec_driver_sql(
                                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params
                                ).scalar()
                            )
                    result["plans"][path] = plans
            with engine.connect() as c:
                assert (
                    c.execute(
                        text(
                            "SELECT count(*) FROM card_images i JOIN card_variants v ON v.id=i.variant_id WHERE i.card_id<>v.card_id"
                        )
                    ).scalar()
                    == 0
                )
                assert (
                    c.execute(
                        text(
                            "SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND objid=807008"
                        )
                    ).scalar()
                    == 0
                )
            result["checks"]["ownership_zero_advisory_released"] = True
    finally:
        runner.apply_plan = original
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        with engine.begin() as c:
            c.execute(delete(card_keywords).where(card_keywords.c.card_id.in_(tracked["cards"])))
            for kind in ("provenance", "images", "variants", "cards", "keywords", "sets"):
                c.execute(delete(TABLES[kind]).where(TABLES[kind].c.id.in_(tracked[kind])))
        assert snapshot() == baseline
        result["cleanup"] = {
            "snapshot_restored": True,
            "server_stopped": not thread.is_alive(),
            "exact_created_id_counts": {k: len(v) for k, v in tracked.items()},
        }
        Path("phase9_verification_results.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps({k: v for k, v in result.items() if k not in ("plans", "constraints")}, indent=2)
    )


if __name__ == "__main__":
    main()
