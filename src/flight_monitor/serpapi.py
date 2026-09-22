"""Small, dependency-free SerpApi Google Flights client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SERPAPI_URL = "https://serpapi.com/search.json"
_CABIN_CODES = {"economy": "1", "premium_economy": "2", "business": "3", "first": "4"}


class SerpApiError(RuntimeError):
    """Expected API or transport failure."""


class MissingApiKeyError(SerpApiError):
    """API key is not available."""


class BudgetExceededError(SerpApiError):
    """Local call budget prevents another request."""


@dataclass
class CallBudget:
    """Conservative local cap for every SerpApi request made by one client."""

    limit: int = 250
    used: int = 0

    def __post_init__(self) -> None:
        if self.limit < 0:
            raise ValueError("budget limit must be non-negative")
        if self.used < 0 or self.used > self.limit:
            raise ValueError("budget used must be between 0 and limit")

    def consume(self) -> None:
        if self.used >= self.limit:
            raise BudgetExceededError(f"SerpApi call budget exhausted ({self.limit})")
        self.used += 1


@dataclass(frozen=True)
class SearchRequest:
    departure_id: str
    arrival_id: str
    outbound_date: str
    return_date: str
    return_departure_id: str | None = None
    return_arrival_id: str | None = None
    adults: int = 1
    children: int = 0
    infants_in_seat: int = 0
    infants_on_lap: int = 0
    cabin: str = "economy"
    currency: str = "USD"
    trip_type: str = "round_trip"
    gl: str = "br"
    hl: str = "pt-BR"

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        *,
        departure_id: str,
        arrival_id: str,
        return_departure_id: str | None = None,
        return_arrival_id: str | None = None,
    ) -> "SearchRequest":
        values = dict(config)
        if "outbound_date" not in values and "departure_date" in values:
            values["outbound_date"] = values["departure_date"]
        values.update(departure_id=departure_id, arrival_id=arrival_id)
        if return_departure_id is not None:
            values["return_departure_id"] = return_departure_id
        if return_arrival_id is not None:
            values["return_arrival_id"] = return_arrival_id
        return cls(**{field: values[field] for field in cls.__dataclass_fields__ if field in values})

    def __post_init__(self) -> None:
        if not self.departure_id or not self.arrival_id:
            raise ValueError("departure_id and arrival_id are required")
        for field in ("outbound_date", "return_date"):
            try:
                date.fromisoformat(getattr(self, field))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} must use YYYY-MM-DD") from exc
        if self.return_date < self.outbound_date:
            raise ValueError("return_date must not precede outbound_date")
        if self.trip_type not in {"round_trip", "multi_city"}:
            raise ValueError("unsupported trip_type")
        if self.trip_type == "multi_city" and (not self.return_departure_id or not self.return_arrival_id):
            raise ValueError("multi_city requires return departure and arrival airports")
        if self.cabin not in _CABIN_CODES:
            raise ValueError(f"unsupported cabin: {self.cabin}")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        for field in ("adults", "children", "infants_in_seat", "infants_on_lap"):
            if getattr(self, field) < 0:
                raise ValueError(f"{field} must be non-negative")
        if self.adults == 0 and self.children == 0 and self.infants_in_seat == 0:
            raise ValueError("at least one adult, child, or infant in seat is required")

    def params(self) -> dict[str, str]:
        params = {
            "engine": "google_flights",
            "travel_class": _CABIN_CODES[self.cabin],
            "adults": str(self.adults),
            "children": str(self.children),
            "infants_in_seat": str(self.infants_in_seat),
            "infants_on_lap": str(self.infants_on_lap),
            "currency": self.currency.upper(),
            "gl": self.gl,
            "hl": self.hl,
        }
        if self.trip_type == "multi_city":
            params.update({
                "type": "3",
                "multi_city_json": json.dumps([
                    {
                        "departure_id": self.departure_id,
                        "arrival_id": self.arrival_id,
                        "date": self.outbound_date,
                    },
                    {
                        "departure_id": self.return_departure_id,
                        "arrival_id": self.return_arrival_id,
                        "date": self.return_date,
                    },
                ], separators=(",", ":")),
            })
        else:
            params.update({
                "departure_id": self.departure_id,
                "arrival_id": self.arrival_id,
                "outbound_date": self.outbound_date,
                "return_date": self.return_date,
                "type": "1",
            })
        return params


def _airport(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {key: value[key] for key in ("id", "name", "time") if key in value}


def _segment(segment: Mapping[str, Any]) -> dict[str, Any]:
    departure = _airport(segment.get("departure_airport"))
    arrival = _airport(segment.get("arrival_airport"))
    return {
        "departure_airport": departure,
        "arrival_airport": arrival,
        "duration_minutes": segment.get("duration"),
        "airline": segment.get("airline"),
        "flight_number": segment.get("flight_number"),
        "travel_class": segment.get("travel_class"),
        "available": bool(departure and arrival),
    }


def normalize_flight(flight: Mapping[str, Any], *, source: str, index: int, currency: str) -> dict[str, Any]:
    segments = [_segment(item) for item in flight.get("flights", []) if isinstance(item, Mapping)]
    normalized = {
        "source": source,
        "price": {
            "amount": flight.get("price"),
            "currency": currency.upper(),
            "scope": "unknown",
            "includes_taxes": None,
            "includes_infants_on_lap": None,
        },
        "type": flight.get("type"),
        "segments": segments,
        "segments_available": bool(segments) and all(item["available"] for item in segments),
        "booking_token_present": bool(flight.get("booking_token")),
        "departure_token_present": bool(flight.get("departure_token")),
        "total_duration_minutes": flight.get("total_duration"),
        "stops": len(segments) - 1 if segments else None,
    }
    identity = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return {"id": f"offer-{hashlib.sha256(identity.encode()).hexdigest()[:20]}", **normalized}


def normalize_response(response: Mapping[str, Any], request: SearchRequest) -> dict[str, Any]:
    metadata = response.get("search_metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    flights: list[dict[str, Any]] = []
    for source in ("best_flights", "other_flights"):
        values = response.get(source, [])
        if isinstance(values, list):
            flights.extend(
                normalize_flight(item, source=source, index=index, currency=request.currency)
                for index, item in enumerate(values)
                if isinstance(item, Mapping)
            )
    return {
        "status": "success",
        "search_id": metadata.get("id"),
        "request": request.params(),
        "result_count": len(flights),
        "flights": flights,
        "price_contract": {
            "currency": request.currency.upper(),
            "meaning": "SerpApi price field, exact scope not established by API response",
            "includes_taxes": None,
            "includes_infants_on_lap": None,
            "group_total_verified": False,
        },
        "availability_contract": {
            "segments_available": "true only when every returned segment has departure and arrival data",
            "inventory_verified": False,
            "booking_verified": False,
        },
        "links": {
            "google_flights": metadata.get("google_flights_url"),
            "serpapi_json": metadata.get("json_endpoint"),
        },
        "warnings": [
            "Price scope, taxes, infant-in-lap inclusion, and inventory are not inferred.",
            "A departure_token follow-up may be needed to select return flights.",
        ],
    }


Transport = Callable[[Mapping[str, str]], Mapping[str, Any]]


class SerpApiClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        budget: CallBudget | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = (
            os.getenv("SERPAPI_API_KEY", "").strip()
            if api_key is None
            else api_key.strip()
        )
        self.timeout = timeout
        self.budget = budget or CallBudget()
        self._transport = transport or self._request_json

    def search(self, request: SearchRequest) -> dict[str, Any]:
        response = self._call(request.params())
        return normalize_response(response, request)

    def returning_flights(self, request: SearchRequest, departure_token: str) -> dict[str, Any]:
        if not departure_token:
            raise ValueError("departure_token is required")
        response = self._call({**request.params(), "departure_token": departure_token})
        return normalize_response(response, request)

    def booking_options(self, request: SearchRequest, booking_token: str) -> Mapping[str, Any]:
        if not booking_token:
            raise ValueError("booking_token is required")
        return self._call({**request.params(), "booking_token": booking_token})

    def _call(self, params: Mapping[str, str]) -> Mapping[str, Any]:
        if not self.api_key:
            raise MissingApiKeyError("SERPAPI_API_KEY is not set")
        self.budget.consume()
        response = self._transport({**params, "api_key": self.api_key})
        if not isinstance(response, Mapping):
            raise SerpApiError("SerpApi response is not a JSON object")
        metadata = response.get("search_metadata")
        status = metadata.get("status") if isinstance(metadata, Mapping) else None
        if response.get("error") or status == "Error":
            raise SerpApiError(str(response.get("error") or "SerpApi returned status Error"))
        return response

    def _request_json(self, params: Mapping[str, str]) -> Mapping[str, Any]:
        query = urlencode(params)
        request = Request(f"{SERPAPI_URL}?{query}", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed HTTPS endpoint
                payload = response.read()
        except HTTPError as exc:
            raise SerpApiError(f"SerpApi HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise SerpApiError(f"SerpApi request failed: {exc}") from exc
        try:
            parsed = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SerpApiError("SerpApi returned invalid JSON") from exc
        if not isinstance(parsed, Mapping):
            raise SerpApiError("SerpApi response is not a JSON object")
        return parsed
