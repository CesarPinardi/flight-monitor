from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys

from .monitor import load_config, run_monitor
from .serpapi import SearchRequest


def _extra_request(value: str, config: dict[str, object]) -> SearchRequest:
    try:
        origin, destination = value.upper().split(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("extra route must use ORIGIN:DESTINATION") from exc
    extra_config = dict(config)
    extra_config["trip_type"] = "round_trip"
    extra_config.pop("itineraries", None)
    return SearchRequest.from_config(extra_config, departure_id=origin, arrival_id=destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process Google Flights history")
    parser.add_argument("--config", default="config/search.json")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--dry-run", action="store_true", help="read fixtures; never call SerpApi")
    parser.add_argument("--local", action="store_true", help="never send Telegram alerts")
    parser.add_argument("--fixtures", default="tests/fixtures")
    parser.add_argument("--extra-route", action="append", default=[], help="explicit extra route ORIGIN:DESTINATION")
    parser.add_argument("--force", action="store_true", help="allow a second run on same Sao Paulo date")
    parser.add_argument("--now", help="UTC ISO timestamp for repeatable runs")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        extras = [_extra_request(value, config) for value in args.extra_route]
        now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None
        result = run_monitor(config, data_dir=args.data_dir, dry_run=args.dry_run, fixture_dir=args.fixtures, force=args.force, extra_requests=extras, now=now, local=args.local)
    except Exception as exc:
        print(json.dumps({"status": "failure", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"success", "duplicate"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
