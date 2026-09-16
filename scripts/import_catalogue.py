"""One-shot approved catalogue import: python scripts/import_catalogue.py.

Requires an empty catalogue. Repeated invocation refuses existing data; the
Phase 15 persistence helper is reused unchanged. No startup hook or scheduler.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from importer.catalogue_importer import build_dry_run
from scripts.acquisition.run_acquisition import acquire_one
from scripts.acquisition.sources import APPROVED_API_SOURCES

PLAN_SHA256 = "2a209a10ab4a59c25a2730f991ac4a3978fd0758e7e232a0d1d94815cb34a091"
EXPECTED_REPORT = {
    "source_records": 636,
    "accepted": 636,
    "rejected": 0,
    "unexplained_quarantine": 0,
    "unique_cards": 318,
    "unique_printings": 636,
}
EXPECTED_SETS = {"Set 1: Konoha Shidō": 394, "Set 2: Shinobi Shiren": 242}
EXPECTED_COUNTS = {
    "sets": 2,
    "cards": 318,
    "printings": 636,
    "translations": 2544,
    "provenance": 2544,
    "image_references": 2544,
    "keywords": 46,
    "associations": 701,
}


class ImportRefused(RuntimeError):
    """Only fixed safe codes are emitted; never exception details or credentials."""


def validate_plan(result):
    try:
        plan, report = result["plan"], result["report"]
        encoded = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if hashlib.sha256(encoded.encode()).hexdigest() != PLAN_SHA256:
            raise ValueError
        if report.get("plan_sha256") != PLAN_SHA256:
            raise ValueError
        if any(report.get(k) != v for k, v in EXPECTED_REPORT.items()):
            raise ValueError
        if report.get("quarantined_records") or report.get("identity_collision_count") != 0:
            raise ValueError
        if len(plan["cards"]) != 318 or len(plan["printings"]) != 636:
            raise ValueError
        if Counter(p["identity"]["expansion"] for p in plan["printings"]) != EXPECTED_SETS:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ImportRefused("SOURCE_DRIFT") from None


def acquire_plan():
    # Fresh isolated snapshot: a failed fetch cannot reuse an older manifest entry.
    with TemporaryDirectory(prefix="catalogue-import-") as temporary:
        root = Path(temporary)
        try:
            for source in APPROVED_API_SOURCES:
                entry = acquire_one(
                    source, root / "raw", root / "manifest.json", root / "observations"
                )
                if entry.get("http_status") != 200 or not entry.get("sha256") or entry.get("error"):
                    raise ValueError
            result = build_dry_run(root)
            validate_plan(result)
            return result
        except Exception:  # noqa: BLE001 -- CLI boundary must not disclose credentials/source text
            raise ImportRefused("SOURCE_DRIFT") from None


def configured_engine():
    # Explicitly disable dotenv before the existing cached settings and model engine load.
    from app.config import Settings, get_settings

    Settings.model_config["env_file"] = None
    get_settings()
    from app.database import engine

    return engine


def lock_catalogue(connection):
    from sqlalchemy import text

    connection.execute(text("SET LOCAL lock_timeout = '15s'"))
    connection.execute(
        text(
            "LOCK TABLE sets, cards, card_variants, printing_translations, source_records, "
            "card_images, keywords, card_keywords IN SHARE ROW EXCLUSIVE MODE"
        )
    )


def verify_catalogue(session, result):
    from sqlalchemy import select

    from app.models import Card
    from importer.catalogue_persistence import count_catalogue

    if asdict(count_catalogue(session)) != EXPECTED_COUNTS:
        raise ImportRefused("CATALOGUE_VERIFICATION_FAILED")
    missions, negatives = {}, {}
    for printing in result["plan"]["printings"]:
        raw = next(
            o["observation"] for o in printing["source_observations"] if o["language"] == "en"
        )
        if raw.get("CardType") == "Mission":
            missions[printing["card_id"]] = int(raw["Points"])
        if raw.get("Power") == -1:
            negatives[printing["card_id"]] = -1
    actual_missions = dict(
        session.execute(
            select(Card.public_id, Card.points).where(Card.card_type == "Mission")
        ).all()
    )
    actual_negatives = dict(
        session.execute(select(Card.public_id, Card.power).where(Card.power < 0)).all()
    )
    if (
        not missions
        or actual_missions != missions
        or len(negatives) != 2
        or actual_negatives != negatives
    ):
        raise ImportRefused("GAMEPLAY_VERIFICATION_FAILED")


def execute_import(engine, result):
    from sqlalchemy.orm import Session

    from importer.catalogue_persistence import count_catalogue, persist_catalogue_plan

    # Connection owns the real commit. Helper commits/rollbacks affect savepoints only.
    with engine.begin() as connection:
        lock_catalogue(connection)
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            before = asdict(count_catalogue(session))
            print(json.dumps({"before": before}, sort_keys=True))
            if any(before.values()):
                raise ImportRefused("CATALOGUE_NOT_EMPTY")
            persist_catalogue_plan(session, result)
            verify_catalogue(session, result)
            session.commit()
    # Repeat verification after durable commit. A read failure here cannot undo an
    # already committed transaction; report that distinctly, never claim rollback.
    try:
        with Session(engine) as session:
            verify_catalogue(session, result)
    except Exception:  # noqa: BLE001 -- CLI boundary must not disclose credentials/source text
        raise ImportRefused("POST_COMMIT_VERIFICATION_FAILED") from None


def main():
    engine = None
    try:
        result = acquire_plan()  # All source/hash gates precede configuration/connection.
        engine = configured_engine()
        execute_import(engine, result)
        print(
            json.dumps(
                {"status": "COMMITTED_AND_VERIFIED", "counts": EXPECTED_COUNTS}, sort_keys=True
            )
        )
        return 0
    except ImportRefused as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 -- CLI boundary must not disclose credentials/source text
        print("IMPORT_FAILED", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:  # noqa: BLE001 -- cleanup must not expose connection details
                print("ENGINE_CLEANUP_FAILED", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
