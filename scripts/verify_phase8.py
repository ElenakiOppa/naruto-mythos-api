"""Explicit local PostgreSQL verification; cleans only exact UUIDs created here."""

import copy
import json
import uuid
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select, text

from app.database import engine
from app.main import app
from app.models.keyword import card_keywords
from importer import runner
from importer.planner import TABLES


def snapshot():
    with engine.connect() as conn:
        return {
            k: [dict(r) for r in conn.execute(select(t).order_by(t.c.id)).mappings()]
            for k, t in TABLES.items()
        }


def main(expected_head="5f360cfd2561", output_path="phase8_verification_results.json"):
    prefix = "p8-" + uuid.uuid4().hex[:12]
    payload = json.loads(Path("data/examples/fictional-catalogue.json").read_text())
    raw = json.dumps(payload).replace("test-import", prefix).replace("TEST-IMPORT", prefix.upper())
    payload = json.loads(raw)
    payload["source"]["name"] = prefix
    created = {k: set() for k in TABLES}
    original_apply = runner.apply_plan

    def tracked(conn, plan):
        for kind, rows in plan.inserts.items():
            created[kind].update(r["id"] for r in rows)
        original_apply(conn, plan)

    runner.apply_plan = tracked
    result = {"checks": {}, "performance": {}}
    baseline = snapshot()

    def run(data, **kwargs):
        report = runner.run_import(engine, data, **kwargs)
        assert report["status"] == "success", report["errors"]
        return report

    try:
        with engine.connect() as conn:
            assert conn.dialect.name == "postgresql"
            result["postgresql"] = conn.execute(text("SHOW server_version")).scalar()
            result["alembic"] = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            assert result["alembic"] == expected_head
        run(payload, dry_run=True)
        assert snapshot() == baseline
        result["checks"]["dry_run_unchanged"] = True
        first = run(payload)
        result["first_import_counts"] = first["counts"]
        after = snapshot()
        second = run(payload)
        assert all(
            g.get("created", 0) == g.get("updated", 0) == 0 for g in second["counts"].values()
        )
        assert snapshot() == after
        result["checks"]["idempotent"] = True
        card = payload["sets"][0]["cards"][0]
        card["name"] = "Fictional Updated"
        dry = run(payload, dry_run=True)
        assert dry["counts"]["cards"]["updated"] == 1
        assert (
            sum(
                g["updated"]
                for k, g in dry["counts"].items()
                if k not in ("provenance", "relationships")
            )
            == 1
        )
        assert snapshot() == after
        run(payload)
        assert {r["id"] for r in after["cards"]} == {r["id"] for r in snapshot()["cards"]}
        result["checks"]["one_update_stable_uuid"] = True
        payload["source"]["name"] += "-second"
        assert run(payload)["counts"]["provenance"]["created"] == 11
        result["checks"]["second_source"] = True
        with TestClient(app) as client:
            paths = [
                "/v1/sets",
                f"/v1/sets/{prefix}-set-0",
                f"/v1/sets/{prefix}-set-0/cards",
                "/v1/cards",
                f"/v1/cards/{prefix.upper()}-0",
                "/v1/cards/random",
                "/v1/rarities",
                "/v1/keywords",
                f"/v1/keywords/{prefix}-keyword/cards",
                "/v1/search?q=Fictional",
            ]
            result["api_statuses"] = {}
            for path in paths:
                response = client.get(path)
                assert response.status_code == 200, response.text
                assert "content_hash" not in response.text and "source_records" not in response.text
                result["api_statuses"][path] = response.status_code
        reduced = copy.deepcopy(payload)
        reduced["sets"] = reduced["sets"][:1]
        reduced["sets"][0]["cards"] = []
        before = snapshot()
        run(reduced)
        assert snapshot() == before
        result["checks"]["omitted_entities_preserved"] = True
        omitted_children = copy.deepcopy(payload)
        for item in omitted_children["sets"]:
            for imported_card in item["cards"]:
                imported_card["variants"] = []
                imported_card["images"] = []
        run(omitted_children)
        assert snapshot() == before
        result["checks"]["omitted_variants_images_preserved"] = True

        def fail(conn, plan):
            tracked(conn, plan)
            raise RuntimeError("injected failure")

        runner.apply_plan = fail
        broken = copy.deepcopy(payload)
        broken["sets"][0]["cards"][0]["name"] = "Fictional Rolled Back"
        assert runner.run_import(engine, broken)["transaction"] == "rolled_back"
        assert snapshot() == before
        runner.apply_plan = tracked
        result["checks"]["rollback"] = True
        large = {"source": dict(payload["source"], name=prefix + "-performance"), "sets": []}
        for s in range(5):
            st = {
                "id": f"{prefix}-perf-set-{s}",
                "name": f"Fictional Performance Set {s}",
                "cards": [],
            }
            for i in range(100):
                ident = f"{prefix}-perf-{s}-{i}"
                st["cards"].append(
                    {
                        "id": ident,
                        "number": f"{i:03}",
                        "name": f"Fictional Card {i}",
                        "keywords": [
                            {
                                "slug": f"{prefix}-perf-kw-{i % 10}",
                                "name": f"Fictional Keyword {i % 10}",
                            }
                        ],
                        "variants": [
                            {
                                "id": ident + "-v",
                                "type": "experimental",
                                "images": [{"url": f"https://example.invalid/{ident}-v.png"}],
                            }
                        ],
                        "images": [{"url": f"https://example.invalid/{ident}.png"}],
                    }
                )
            large["sets"].append(st)
        for label, dry_run in [("dry_run", True), ("actual", False), ("repeat", False)]:
            statements = []

            def capture(conn, cursor, statement, parameters, context, many, statements=statements):
                statements.append(statement.split()[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            started = perf_counter()
            report = run(large, dry_run=dry_run)
            duration = perf_counter() - started
            event.remove(engine, "before_cursor_execute", capture)
            result["performance"][label] = {
                "cards": 500,
                "seconds": round(duration, 4),
                "sql_executions": len(statements),
                "selects": statements.count("SELECT"),
                "dml_executions": sum(statements.count(x) for x in ("INSERT", "UPDATE", "DELETE")),
                "counts": report["counts"],
            }
        result["checks"]["performance_complete"] = True
    finally:
        runner.apply_plan = original_apply
        with engine.begin() as conn:
            conn.execute(delete(card_keywords).where(card_keywords.c.card_id.in_(created["cards"])))
            for kind in ("provenance", "images", "variants", "cards", "keywords", "sets"):
                conn.execute(delete(TABLES[kind]).where(TABLES[kind].c.id.in_(created[kind])))
        assert snapshot() == baseline, "Cleanup did not restore exact baseline"
        result["cleanup"] = {
            "baseline_restored": True,
            "exact_ids_removed": {k: len(v) for k, v in created.items()},
        }
        Path(output_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
