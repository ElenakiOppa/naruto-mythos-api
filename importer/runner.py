"""Validate, plan, and apply an entire import in one transaction."""

import json
import logging
from datetime import UTC, datetime
from time import perf_counter

from pydantic import ValidationError
from sqlalchemy import bindparam, delete, insert, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.models.keyword import card_keywords
from importer.planner import TABLES, ImportConflict, build_plan, chunks
from importer.schemas import parse_catalogue

logger = logging.getLogger("catalogue_importer")


def apply_plan(connection, plan):
    for kind in ("sets", "keywords", "cards", "variants", "images", "provenance"):
        table = TABLES[kind]
        for batch in chunks(plan.inserts[kind]):
            connection.execute(insert(table), batch)
        rows = plan.updates[kind]
        if rows:
            stmt = (
                update(table)
                .where(table.c.id == bindparam("_pk"))
                .values({key: bindparam(key) for key in rows[0] if key != "_pk"})
            )
            for batch in chunks(rows):
                connection.execute(stmt, batch)
    if plan.links_removed:
        stmt = delete(card_keywords).where(
            card_keywords.c.card_id == bindparam("_card"),
            card_keywords.c.keyword_id == bindparam("_keyword"),
        )
        for batch in chunks(plan.links_removed):
            connection.execute(
                stmt, [{"_card": r["card_id"], "_keyword": r["keyword_id"]} for r in batch]
            )
    for batch in chunks(plan.links_created):
        connection.execute(insert(card_keywords), batch)


def run_import(engine, payload, *, dry_run=False, input_file=None):
    started = datetime.now(UTC)
    clock = perf_counter()
    report = {
        "source": None,
        "input_file": input_file,
        "dry_run": dry_run,
        "started_at": started.isoformat(),
        "finished_at": None,
        "validation": {"valid": False},
        "status": "failed",
        "transaction": "not_started",
        "plan": {},
        "counts": {},
        "normalizations": [],
        "warnings": [],
        "errors": [],
    }
    try:
        catalogue = parse_catalogue(payload)
        report["source"] = {"name": catalogue.source.name}
        report["validation"] = {
            "valid": True,
            "sets": len(catalogue.sets),
            "cards": sum(len(s.cards) for s in catalogue.sets),
        }
        with engine.connect() as connection:
            with connection.begin():
                if connection.dialect.name == "postgresql":
                    if dry_run:
                        connection.execute(
                            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                        )
                    else:
                        # Serialize cooperating importer runs: provenance/image tables lack
                        # natural-key uniqueness. External writers must coordinate separately.
                        connection.execute(text("SELECT pg_advisory_xact_lock(807008)"))
                plan = build_plan(connection, catalogue)
                report["plan"] = plan.changes
                report["counts"] = {
                    k: {action: len(ids) for action, ids in group.items()}
                    for k, group in plan.changes.items()
                }
                report["normalizations"] = plan.normalizations
                report["transaction"] = "planned"
                if not dry_run:
                    apply_plan(connection, plan)
            report["transaction"] = "read_only" if dry_run else "committed"
        report["status"] = "success"
    except ValidationError as exc:
        report["errors"] = [
            {"location": ".".join(map(str, e["loc"])), "message": e["msg"]}
            for e in exc.errors(include_input=False, include_context=False, include_url=False)
        ][:50]
    except (ValueError, UnicodeError) as exc:
        # JSON/parser errors can quote source text; only curated conflicts are printed.
        message = (
            str(exc) if isinstance(exc, ImportConflict) else "Invalid JSON or catalogue input."
        )
        report["errors"] = [{"message": message}]
        if isinstance(exc, ImportConflict):
            report["validation"]["valid"] = False
    except SQLAlchemyError:
        report["errors"] = [
            {"message": "Database transaction failed; no import changes were committed."}
        ]
    except Exception:  # noqa: BLE001 -- sanitize unexpected failures at the execution boundary
        report["errors"] = [{"message": "Import failed; no import changes were committed."}]
    if report["status"] != "success" and report["transaction"] == "planned":
        report["transaction"] = "rolled_back"
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["duration_seconds"] = round(perf_counter() - clock, 6)
    logger.info(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "source",
                    "input_file",
                    "dry_run",
                    "validation",
                    "counts",
                    "status",
                    "transaction",
                    "duration_seconds",
                )
            }
        )
    )
    return report
