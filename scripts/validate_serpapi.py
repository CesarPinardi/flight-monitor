#!/usr/bin/env python3
"""Run one sanitized SerpApi Google Flights validation."""

from __future__ import annotations

import json
import os
from pathlib import Path

from flight_monitor.monitor import load_config
from flight_monitor.serpapi import SearchRequest, SerpApiClient


ROOT = Path(__file__).parents[1]


def main() -> int:
    config = load_config(ROOT / "config/search.json")
    itineraries = config.get("itineraries", [])
    trip_leg = config.get("trip_leg", "outbound")
    selected_leg = itineraries[0][trip_leg] if itineraries else {"origin": "GRU", "destination": "MCO"}
    request_config = dict(config)
    if trip_leg == "return":
        request_config["outbound_date"] = config["return_date"]
        request_config.pop("return_date", None)
    request = SearchRequest.from_config(
        request_config,
        departure_id=selected_leg["origin"],
        arrival_id=selected_leg["destination"],
    )
    result = SerpApiClient(os.environ.get("SERPAPI_API_KEY")).search(request)
    offers = []
    for flight in result.get("flights", []):
        price = flight.get("price", {})
        offers.append(
            {
                "amount": price.get("amount"),
                "currency": price.get("currency"),
                "scope": price.get("scope"),
                "includes_taxes": price.get("includes_taxes"),
                "includes_infants_on_lap": price.get("includes_infants_on_lap"),
                "segments_available": flight.get("segments_available"),
                "stops": flight.get("stops"),
                "duration_minutes": flight.get("total_duration_minutes"),
            }
        )
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "route": f"{selected_leg['origin']}-{selected_leg['destination']} ({trip_leg})",
                "request": request.params(),
                "result_count": result.get("result_count"),
                "offers": offers,
                "price_contract": result.get("price_contract"),
                "availability_contract": result.get("availability_contract"),
                "warnings": result.get("warnings"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
