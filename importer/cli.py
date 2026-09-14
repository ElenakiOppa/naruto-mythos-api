"""CLI for approved local JSON files. Does not fetch URLs or execute source content."""

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from importer.schemas import parse_catalogue


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import an approved local normalized catalogue (no scraping)."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--dry-run", action="store_true", help="Read-only validation and change planning."
    )
    parser.add_argument(
        "--report", type=Path, help="Also save the JSON execution report to a local file."
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.report and args.report.resolve() == args.input.resolve():
            raise ValueError("Report path must differ from input")
        if not args.input.is_file():
            raise ValueError("Input must be a regular local file")
        raw = args.input.read_text(encoding="utf-8-sig")
        # Invalid input does not even construct a configured database engine.
        parse_catalogue(raw)
        from app.database import engine
        from importer.runner import run_import

        report = run_import(engine, raw, dry_run=args.dry_run, input_file=args.input.name)
    except Exception as exc:  # noqa: BLE001 -- structured safe CLI error boundary
        now = datetime.now(UTC).isoformat()
        report = {
            "source": None,
            "input_file": args.input.name,
            "dry_run": args.dry_run,
            "started_at": now,
            "finished_at": now,
            "validation": {"valid": False},
            "status": "failed",
            "transaction": "not_started",
            "counts": {},
            "plan": {},
            "warnings": [],
            "errors": [
                {
                    "message": "Unable to read or validate input, report path, or database configuration."
                }
            ],
        }
        if isinstance(exc, ValidationError):
            report["errors"] = [
                {"location": ".".join(map(str, error["loc"])), "message": error["msg"]}
                for error in exc.errors(
                    include_input=False, include_context=False, include_url=False
                )
            ][:50]
    output = json.dumps(report, ensure_ascii=True, indent=2)
    print(output)
    if args.report:
        try:
            if args.report.resolve() == args.input.resolve():
                return 1
            args.report.write_text(output + "\n", encoding="utf-8")
        except OSError:
            return 1
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
