"""Daily Google Flights processing, history, state, and public JSON."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .serpapi import BudgetExceededError, CallBudget, SearchRequest, SerpApiClient
from .storage import JsonStore
from .telegram import (
    AlertPlan,
    TelegramClient,
    TelegramError,
    build_alert_plan,
    confirm_alert_plan,
)


SCHEMA_VERSION = 1
PRESENTATION_TIMEZONE = "America/Sao_Paulo"
DEFAULT_MONTHLY_BASIC_LIMIT = 186
DEFAULT_MONTHLY_CALL_LIMIT = 250
DEFAULT_DAILY_BASIC_SEARCHES = 6
DEFAULT_EXTRA_CALLS_LIMIT = 0


@dataclass(frozen=True)
class Route:
    origin: str
    destination: str
    return_origin: str | None = None
    return_destination: str | None = None
    leg: str | None = None

    @property
    def key(self) -> str:
        suffix = f":{self.leg}" if self.leg else ""
        return f"{self.origin}-{self.destination}{suffix}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _local_date(value: datetime) -> str:
    return value.astimezone(ZoneInfo(PRESENTATION_TIMEZONE)).date().isoformat()


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:300]


def load_config(path: str | os.PathLike[str]) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config, Mapping):
        raise ValueError("search config must be a JSON object")
    result = dict(config)
    origins = result.get("origins")
    destinations = result.get("destinations")
    if not isinstance(origins, list) or not origins or not all(isinstance(item, str) and item for item in origins):
        raise ValueError("origins must be a non-empty list of airport codes")
    if not isinstance(destinations, list) or not destinations or not all(isinstance(item, str) and item for item in destinations):
        raise ValueError("destinations must be a non-empty list of airport codes")
    trip_type = result.get("trip_type", "round_trip")
    if trip_type not in {"one_way", "round_trip", "multi_city"}:
        raise ValueError("unsupported trip_type")
    trip_leg = result.get("trip_leg", "outbound")
    if trip_leg not in {"outbound", "return", "both"}:
        raise ValueError("trip_leg must be outbound, return, or both")
    if trip_type == "one_way" and trip_leg in {"return", "both"}:
        if "itineraries" not in result:
            raise ValueError(f"trip_leg {trip_leg} requires itineraries")
        if not isinstance(result.get("return_date"), str) or not result["return_date"]:
            raise ValueError(f"trip_leg {trip_leg} requires return_date")
    itineraries = result.get("itineraries")
    if itineraries is not None:
        if not isinstance(itineraries, list) or not itineraries:
            raise ValueError("itineraries must be a non-empty list")
        for index, itinerary in enumerate(itineraries):
            if not isinstance(itinerary, Mapping):
                raise ValueError(f"itineraries[{index}] must be an object")
            for leg_name in ("outbound", "return"):
                leg = itinerary.get(leg_name)
                if (
                    not isinstance(leg, Mapping)
                    or not isinstance(leg.get("origin"), str)
                    or not leg["origin"]
                    or not isinstance(leg.get("destination"), str)
                    or not leg["destination"]
                ):
                    raise ValueError(f"itineraries[{index}].{leg_name} must have origin and destination")
    result.setdefault("daily_basic_searches", DEFAULT_DAILY_BASIC_SEARCHES)
    result.setdefault("monthly_basic_limit", DEFAULT_MONTHLY_BASIC_LIMIT)
    result.setdefault("monthly_call_limit", DEFAULT_MONTHLY_CALL_LIMIT)
    result.setdefault("extra_calls_limit", DEFAULT_EXTRA_CALLS_LIMIT)
    for name in ("daily_basic_searches", "monthly_basic_limit", "monthly_call_limit", "extra_calls_limit"):
        if not isinstance(result[name], int) or result[name] < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    ceiling = result.get("alert_price_ceiling")
    if ceiling is not None and (isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0):
        raise ValueError("alert_price_ceiling must be a positive number or null")
    leg_count = 2 if trip_type == "one_way" and trip_leg == "both" else 1
    expected_searches = (len(itineraries) if itineraries is not None else len(origins) * len(destinations)) * leg_count
    if result["daily_basic_searches"] != expected_searches:
        raise ValueError("daily_basic_searches must match configured itineraries")
    if result["monthly_basic_limit"] > DEFAULT_MONTHLY_BASIC_LIMIT:
        raise ValueError("monthly_basic_limit cannot exceed 186")
    if result["monthly_call_limit"] > DEFAULT_MONTHLY_CALL_LIMIT:
        raise ValueError("monthly_call_limit cannot exceed 250")
    if result["monthly_basic_limit"] > result["monthly_call_limit"]:
        raise ValueError("monthly_basic_limit cannot exceed monthly_call_limit")
    return result


def routes_from_config(config: Mapping[str, Any]) -> list[Route]:
    itineraries = config.get("itineraries")
    if isinstance(itineraries, list):
        if config.get("trip_type") == "one_way":
            trip_leg = config.get("trip_leg", "outbound")
            trip_legs = ("outbound", "return") if trip_leg == "both" else (trip_leg,)
            return [
                Route(
                    str(item[leg]["origin"]).upper(),
                    str(item[leg]["destination"]).upper(),
                    leg=leg,
                )
                for leg in trip_legs
                for item in itineraries
            ]
        return [
            Route(
                str(item["outbound"]["origin"]).upper(),
                str(item["outbound"]["destination"]).upper(),
                str(item["return"]["origin"]).upper(),
                str(item["return"]["destination"]).upper(),
            )
            for item in itineraries
        ]
    routes: list[Route] = []
    seen: set[str] = set()
    trip_leg = config.get("trip_leg", "outbound")
    if trip_leg == "both":
        raise ValueError("trip_leg both requires itineraries")
    for origin in config["origins"]:
        for destination in config["destinations"]:
            route = Route(
                str(origin).upper(),
                str(destination).upper(),
                leg=trip_leg if config.get("trip_type") == "one_way" else None,
            )
            if route.key not in seen:
                routes.append(route)
                seen.add(route.key)
    return routes


def _request(config: Mapping[str, Any], route: Route) -> SearchRequest:
    values = dict(config)
    if route.leg == "return":
        values["outbound_date"] = config["return_date"]
        values.pop("return_date", None)
    return SearchRequest.from_config(
        values,
        departure_id=route.origin,
        arrival_id=route.destination,
        return_departure_id=route.return_origin,
        return_arrival_id=route.return_destination,
    )


def _route_payload(route: Route) -> dict[str, Any]:
    payload: dict[str, Any] = {"origin": route.origin, "destination": route.destination}
    if route.return_origin and route.return_destination:
        payload.update({"return_origin": route.return_origin, "return_destination": route.return_destination})
    if route.leg:
        payload["leg"] = route.leg
    return payload


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _offer_id(flight: Mapping[str, Any], request: SearchRequest, route: Route) -> str:
    identity = {
        "source": flight.get("source"),
        "route": route.key,
        "leg": route.leg,
        "request": request.params(),
        "price": flight.get("price"),
        "segments": flight.get("segments", []),
    }
    digest = hashlib.sha256(_canonical(identity).encode()).hexdigest()[:20]
    return f"offer-{digest}"


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _per_person_amount(amount: int | float | None, request: SearchRequest) -> int | float | None:
    if amount is None:
        return None
    paid_passengers = request.adults + request.children + request.infants_in_seat
    if paid_passengers <= 0:
        return amount
    return round(amount / paid_passengers, 2)


def normalize_offer(flight: Mapping[str, Any], request: SearchRequest, route: Route, observed_at_utc: str) -> dict[str, Any]:
    price = flight.get("price") if isinstance(flight.get("price"), Mapping) else {}
    amount = _per_person_amount(_number(price.get("amount")), request)
    segments = flight.get("segments") if isinstance(flight.get("segments"), list) else []
    first_airport = segments[0].get("departure_airport") if segments and isinstance(segments[0], Mapping) else None
    last_airport = segments[-1].get("arrival_airport") if segments and isinstance(segments[-1], Mapping) else None
    first_departure = first_airport.get("id") if isinstance(first_airport, Mapping) else None
    last_arrival = last_airport.get("id") if isinstance(last_airport, Mapping) else None
    route_verified = first_departure == route.origin and last_arrival == (route.return_destination or route.destination)
    if route.return_origin and route.return_destination:
        endpoint_ids = {
            airport_id
            for segment in segments
            for airport in (segment.get("departure_airport"), segment.get("arrival_airport"))
            if isinstance(airport, Mapping)
            for airport_id in (airport.get("id"),)
            if isinstance(airport_id, str)
        }
        route_verified = route_verified and route.destination in endpoint_ids and route.return_origin in endpoint_ids
    complete = bool(amount is not None and segments and flight.get("segments_available") and route_verified)
    compatibility = {
        "route": route.key,
        "outbound_date": request.outbound_date,
        "return_date": request.return_date,
        "return_origin": request.return_departure_id,
        "return_destination": request.return_arrival_id,
        "adults": request.adults,
        "children": request.children,
        "infants_in_seat": request.infants_in_seat,
        "infants_on_lap": request.infants_on_lap,
        "cabin": request.cabin,
        "currency": request.currency.upper(),
        "trip_type": request.trip_type,
        "trip_leg": route.leg,
    }
    return {
        "id": _offer_id(flight, request, route),
        "status": "complete" if complete else "pending",
        "route": _route_payload(route),
        "route_verified": route_verified,
        "passengers": {
            "adults": request.adults,
            "children": request.children,
            "infants_in_seat": request.infants_in_seat,
            "infants_on_lap": request.infants_on_lap,
        },
        "price": {
            "amount": amount,
            "currency": price.get("currency", request.currency).upper(),
            "scope": price.get("scope", "unknown"),
            "includes_taxes": price.get("includes_taxes"),
            "includes_infants_on_lap": price.get("includes_infants_on_lap"),
            "interpretation": "provider_value_scope_unknown",
        },
        "currency": request.currency.upper(),
        "itinerary": {
            "type": request.trip_type,
            "stops": flight.get("stops"),
            "total_duration_minutes": flight.get("total_duration_minutes"),
            "segments": segments,
        },
        "provider": "serpapi",
        "source": flight.get("source", "serpapi"),
        "observed_at_utc": observed_at_utc,
        "baggage": {"status": "unknown", "included": False, "counted_in_price": False},
        "compatibility_key": hashlib.sha256(_canonical(compatibility).encode()).hexdigest()[:20],
        "comparison_eligible": complete,
    }


def _empty_state(month: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "failure",
        "month": month,
        "last_run_id": None,
        "last_run_local_date": None,
        "last_run_at_utc": None,
        "search_signature": None,
        "budget": {},
        "routes": {},
    }


def _empty_history() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "entries": []}


def _fixture_response(fixture_dir: Path, route: Route) -> Mapping[str, Any]:
    path = fixture_dir / f"google_flights_{route.origin.lower()}_{route.destination.lower()}.json"
    with path.open(encoding="utf-8") as stream:
        response = json.load(stream)
    if not isinstance(response, Mapping):
        raise ValueError(f"fixture must be a JSON object: {path}")
    return response


def _public_search(config: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "departure_date", "return_date", "origins", "destinations", "adults", "children",
        "infants_in_seat", "infants_on_lap", "cabin", "currency", "trip_type", "trip_leg", "payment_type", "itineraries",
    )
    return {key: config[key] for key in allowed if key in config}


def _comparisons(offers: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for offer in offers:
        if offer.get("comparison_eligible") and _number(offer.get("price", {}).get("amount")) is not None:
            groups.setdefault(str(offer["compatibility_key"]), []).append(offer)
    comparisons: list[dict[str, Any]] = []
    for key, group in groups.items():
        ordered = sorted(group, key=lambda item: item["price"]["amount"])
        comparisons.append({
            "compatibility_key": key,
            "offer_ids": [item["id"] for item in ordered],
            "lowest_price_offer_id": ordered[0]["id"],
            "price_interpretation": "provider_value_scope_unknown",
        })
    return comparisons


def _public_history(history: Mapping[str, Any], search_signature: str | None = None) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for entry in history.get("entries", []):
        if not isinstance(entry, Mapping):
            continue
        if search_signature is not None and entry.get("search_signature") != search_signature:
            continue
        routes: list[dict[str, Any]] = []
        for result in entry.get("results", []):
            if not isinstance(result, Mapping) or not isinstance(result.get("route"), Mapping):
                continue
            route = result["route"]
            offers = result.get("offers", [])
            eligible = [
                offer for offer in offers
                if isinstance(offer, Mapping)
                and offer.get("comparison_eligible")
                and _number(offer.get("price", {}).get("amount")) is not None
            ]
            lowest = min(eligible, key=lambda offer: offer["price"]["amount"]) if eligible else None
            route_data: dict[str, Any] = {
                "route": {
                    key: route.get(key)
                    for key in ("origin", "destination", "return_origin", "return_destination", "leg")
                    if key in route
                },
                "status": result.get("status"),
                "minimum_price": None,
            }
            if lowest is not None:
                price = lowest["price"]
                route_data["minimum_price"] = {
                    "amount": price.get("amount"),
                    "currency": price.get("currency"),
                }
            routes.append(route_data)
        entries.append({
            "run_id": entry.get("run_id"),
            "recorded_at_utc": entry.get("recorded_at_utc"),
            "status": entry.get("status"),
            "routes": routes,
        })
    return {
        "kind": "daily_route_minimum",
        "description": "Menor preço confirmado por rota em cada consulta diária; não representa uma oferta específica.",
        "entries": entries,
    }


def _public_data(
    config: Mapping[str, Any],
    state: Mapping[str, Any],
    history: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    offers: list[dict[str, Any]] = []
    routes: dict[str, Any] = {}
    for key, route_state in state.get("routes", {}).items():
        if not isinstance(route_state, Mapping):
            continue
        route_offers = route_state.get("last_valid_offers", [])
        stale = route_state.get("last_result_status") != "success"
        if isinstance(route_offers, list):
            for offer in route_offers:
                if isinstance(offer, Mapping):
                    copy = dict(offer)
                    copy["stale"] = stale
                    offers.append(copy)
        routes[key] = {
            "status": route_state.get("status"),
            "last_success_at_utc": route_state.get("last_success_at_utc"),
            "stale": stale,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": iso_utc(now),
        "presentation": {"timezone": PRESENTATION_TIMEZONE, "generated_at": now.astimezone(ZoneInfo(PRESENTATION_TIMEZONE)).isoformat()},
        "status": state.get("status"),
        "last_run_id": state.get("last_run_id"),
        "search": _public_search(config),
        "routes": routes,
        "offers": offers,
        "comparisons": _comparisons(offers),
        "history": _public_history(history, _canonical(_public_search(config))),
        "disclaimer": "Preço por passageiro pagante. Escopo original da fonte, taxas, bebê de colo, bagagem e inventário não são inferidos.",
    }


def run_monitor(
    config: Mapping[str, Any],
    *,
    data_dir: str | os.PathLike[str] = "data",
    api_key: str | None = None,
    dry_run: bool = False,
    fixture_dir: str | os.PathLike[str] | None = None,
    now: datetime | None = None,
    force: bool = False,
    extra_requests: Sequence[SearchRequest] = (),
    transport: Callable[[Mapping[str, str]], Mapping[str, Any]] | None = None,
    local: bool = False,
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    telegram_transport: Callable[[Mapping[str, str]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one guarded monitor pass. Dry-run/local modes never send Telegram."""
    config = dict(config)
    config.setdefault("daily_basic_searches", DEFAULT_DAILY_BASIC_SEARCHES)
    config.setdefault("monthly_basic_limit", DEFAULT_MONTHLY_BASIC_LIMIT)
    config.setdefault("monthly_call_limit", DEFAULT_MONTHLY_CALL_LIMIT)
    config.setdefault("extra_calls_limit", DEFAULT_EXTRA_CALLS_LIMIT)
    current = (now or utc_now()).astimezone(timezone.utc)
    routes = routes_from_config(config)
    if len(routes) != config["daily_basic_searches"]:
        raise ValueError("configured route count does not match daily_basic_searches")
    if len(extra_requests) > config["extra_calls_limit"]:
        raise ValueError("extra request count exceeds extra_calls_limit")
    basic_route_keys = {(route.origin, route.destination) for route in routes}
    extra_route_keys = [(item.departure_id, item.arrival_id) for item in extra_requests]
    if len(extra_route_keys) != len(set(extra_route_keys)) or basic_route_keys.intersection(extra_route_keys):
        raise ValueError("duplicate route request is not allowed")
    store = JsonStore(data_dir)
    month = current.strftime("%Y-%m")
    with store.lock():
        old_state = store.read(store.state_path, _empty_state(month))
        if not isinstance(old_state, Mapping) or old_state.get("schema_version") != SCHEMA_VERSION:
            old_state = _empty_state(month)
        state = dict(old_state)
        if state.get("month") != month:
            previous_routes = state.get("routes", {}) if isinstance(state.get("routes"), Mapping) else {}
            previous_alerts = state.get("alerts") if isinstance(state.get("alerts"), Mapping) else None
            state = _empty_state(month)
            state["routes"] = dict(previous_routes)
            if previous_alerts is not None:
                state["alerts"] = dict(previous_alerts)
        search_signature = _canonical(_public_search(config))
        if state.get("search_signature") != search_signature:
            state["routes"] = {}
            state.pop("alerts", None)
        if not force and state.get("last_run_local_date") == _local_date(current):
            return {"status": "duplicate", "run_id": state.get("last_run_id"), "calls": 0}
        budget_info = state.get("budget") if isinstance(state.get("budget"), Mapping) else {}
        basic_used = int(budget_info.get("basic_used", 0))
        extra_used = int(budget_info.get("extra_used", 0))
        monthly_basic_limit = int(config["monthly_basic_limit"])
        monthly_call_limit = int(config["monthly_call_limit"])
        extra_limit = int(config["extra_calls_limit"])
        total_limit = min(monthly_call_limit, monthly_basic_limit + extra_limit)
        total_used = basic_used + extra_used
        remaining = max(0, total_limit - total_used)
        client = SerpApiClient(api_key, budget=CallBudget(limit=remaining), transport=transport) if not dry_run else None
        observed = iso_utc(current)
        run_id = "run-" + hashlib.sha256(f"{observed}:{_canonical(_public_search(config))}".encode()).hexdigest()[:20]
        route_states = dict(state.get("routes", {}))
        history = store.read(store.history_path, _empty_history())
        if not isinstance(history, Mapping) or history.get("schema_version") != SCHEMA_VERSION:
            history = _empty_history()
        history_entries = list(history.get("entries", [])) if isinstance(history.get("entries"), list) else []
        base_run_id = run_id
        suffix = 2
        used_run_ids = {item.get("run_id") for item in history_entries if isinstance(item, Mapping)}
        while run_id in used_run_ids:
            run_id = f"{base_run_id}-{suffix}"
            suffix += 1
        results: list[dict[str, Any]] = []
        quota_hit = False
        success_count = 0

        def process(route: Route, request: SearchRequest, *, is_extra: bool) -> None:
            nonlocal quota_hit, success_count
            key = route.key
            record: dict[str, Any] = {"route": _route_payload(route), "request": request.params(), "status": "failure", "offers": []}
            try:
                if dry_run:
                    response = _fixture_response(Path(fixture_dir or "tests/fixtures"), route)
                    from .serpapi import normalize_response
                    normalized = normalize_response(response, request)
                else:
                    assert client is not None
                    normalized = client.search(request)
                offers_by_id = {
                    offer["id"]: offer
                    for item in normalized.get("flights", [])
                    for offer in [normalize_offer(item, request, route, observed)]
                }
                offers = list(offers_by_id.values())
                links = normalized.get("links") if isinstance(normalized.get("links"), Mapping) else {}
                for offer in offers:
                    offer["links"] = {
                        "google_flights": links["google_flights"]
                    } if isinstance(links.get("google_flights"), str) and links["google_flights"] else {}
                record.update({"status": "success", "offers": offers, "search_id": normalized.get("search_id")})
                success_count += 1
                route_states[key] = {
                    "status": "success",
                    "last_result_status": "success",
                    "last_attempt_at_utc": observed,
                    "last_success_at_utc": observed,
                    "last_valid_run_id": run_id,
                    "last_valid_offers": offers,
                    "last_error": None,
                }
            except BudgetExceededError as exc:
                quota_hit = True
                record.update({"status": "quota", "error": _safe_error(exc), "error_code": "quota_exhausted"})
                previous = route_states.get(key, {})
                route_states[key] = {**previous, "status": "stale_data" if previous.get("last_valid_offers") else "quota", "last_result_status": "quota", "last_attempt_at_utc": observed, "last_error": _safe_error(exc)}
            except Exception as exc:  # keep other routes and preserve previous valid data
                record.update({"status": "failure", "error": _safe_error(exc), "error_code": exc.__class__.__name__})
                previous = route_states.get(key, {})
                route_states[key] = {**previous, "status": "stale_data" if previous.get("last_valid_offers") else "failure", "last_result_status": "failure", "last_attempt_at_utc": observed, "last_error": _safe_error(exc)}
            record["is_extra"] = is_extra
            results.append(record)

        for route in routes:
            process(route, _request(config, route), is_extra=False)
        for request in extra_requests:
            route = Route(request.departure_id, request.arrival_id)
            process(route, request, is_extra=True)

        calls_made = client.budget.used if client is not None else 0
        # Fixture reads do not spend SerpApi quota. Real client counts failed calls too.
        basic_used += min(calls_made, len(routes))
        extra_used += max(0, calls_made - min(calls_made, len(routes)))
        statuses = [item["status"] for item in results if not item["is_extra"]]
        if quota_hit:
            overall = "quota"
        elif statuses and all(status == "success" for status in statuses):
            overall = "success"
        elif any(status == "success" for status in statuses):
            overall = "failure"
        elif any(item.get("status") == "stale_data" for item in route_states.values()):
            overall = "stale_data"
        else:
            overall = "failure"
        state.update({
            "schema_version": SCHEMA_VERSION,
            "status": overall,
            "month": month,
            "last_run_id": run_id,
            "last_run_local_date": _local_date(current),
            "last_run_at_utc": observed,
            "search_signature": search_signature,
            "budget": {
                "month": month,
                "basic_used": basic_used,
                "extra_used": extra_used,
                "basic_limit": monthly_basic_limit,
                "monthly_call_limit": monthly_call_limit,
                "extra_limit": extra_limit,
                "total_limit": total_limit,
                "remaining": max(0, total_limit - basic_used - extra_used),
            },
            "routes": route_states,
        })
        alert_plan = build_alert_plan(state, results, config, current)
        state["alerts"] = alert_plan.state
        history_entries.append({
            "schema_version": SCHEMA_VERSION,
            "search_signature": search_signature,
            "run_id": run_id,
            "recorded_at_utc": observed,
            "status": overall,
            "results": results,
        })
        new_history = {"schema_version": SCHEMA_VERSION, "entries": history_entries}
        public = _public_data(config, state, new_history, current)
        store.write(store.history_path, new_history)
        store.write(store.state_path, state)
        store.write(store.public_path, public)
        telegram_result: dict[str, Any] = {
            "status": "idle" if alert_plan.text is None else "pending",
            "alerts": alert_plan.opportunity_count,
            "issues": len(alert_plan.issue_actions),
            "sent": False,
        }
        if alert_plan.text is not None:
            client = TelegramClient(
                telegram_token,
                telegram_chat_id,
                transport=telegram_transport,
            )
            if local or dry_run:
                telegram_result["status"] = "local"
            elif not client.configured:
                telegram_result["status"] = "not_configured"
            else:
                try:
                    sent = None
                    for message in alert_plan.messages:
                        sent = client.send_message(message)
                    assert sent is not None
                    sent_at = iso_utc(current)
                    state["alerts"] = confirm_alert_plan(alert_plan, sent_at_utc=sent_at, message_id=sent.message_id)
                    store.write(store.state_path, state)
                    telegram_result.update({"status": "sent", "sent": True, "message_id": sent.message_id})
                except TelegramError as exc:
                    telegram_result.update({"status": "failure", "error": str(exc)})
        return {
            "status": overall,
            "run_id": run_id,
            "calls": calls_made,
            "successful_routes": success_count,
            "telegram": telegram_result,
            "history": str(store.history_path),
            "state": str(store.state_path),
            "public": str(store.public_path),
        }
