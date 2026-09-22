"""Telegram alerts, comparison rules, and safe message formatting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_TIMEOUT = 10.0
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
ALERT_SCHEMA_VERSION = 1


class TelegramError(RuntimeError):
    """Expected Telegram transport or API failure."""


class TelegramNotConfiguredError(TelegramError):
    """Telegram credentials are absent."""


Transport = Callable[[Mapping[str, str]], Mapping[str, Any]]


@dataclass(frozen=True)
class TelegramSendResult:
    message_id: int


class TelegramClient:
    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        *,
        timeout: float = TELEGRAM_TIMEOUT,
        transport: Transport | None = None,
    ) -> None:
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.timeout = timeout
        self._transport = transport or self._request_json

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str) -> TelegramSendResult:
        if not self.configured:
            raise TelegramNotConfiguredError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
        if not text or len(text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            raise TelegramError("Telegram message length is invalid")
        response = self._transport({
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        })
        if not isinstance(response, Mapping) or response.get("ok") is not True:
            raise TelegramError("Telegram API did not confirm message")
        result = response.get("result")
        message_id = result.get("message_id") if isinstance(result, Mapping) else None
        if isinstance(message_id, bool) or not isinstance(message_id, int):
            raise TelegramError("Telegram API response has no message_id")
        return TelegramSendResult(message_id=message_id)

    def _request_json(self, params: Mapping[str, str]) -> Mapping[str, Any]:
        body = json.dumps(params, ensure_ascii=False).encode("utf-8")
        request = Request(
            TELEGRAM_URL.format(token=self.token),
            data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed HTTPS endpoint
                payload = response.read()
        except HTTPError as exc:
            raise TelegramError(f"Telegram HTTP {exc.code}") from exc
        except (URLError, TimeoutError):
            raise TelegramError("Telegram request failed") from None
        try:
            parsed = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TelegramError("Telegram returned invalid JSON") from None
        if not isinstance(parsed, Mapping):
            raise TelegramError("Telegram response is not a JSON object")
        return parsed


def empty_alert_state() -> dict[str, Any]:
    return {
        "schema_version": ALERT_SCHEMA_VERSION,
        "first_alert_sent": False,
        "baselines": {},
        "sent": {},
        "issues": {
            "failure": {"consecutive": 0, "active": False, "alerted": False},
            "quota": {"active": False, "alerted": False},
        },
        "last_evaluated_at_utc": None,
    }


def _alert_state(value: Any) -> dict[str, Any]:
    result = empty_alert_state()
    if not isinstance(value, Mapping) or value.get("schema_version") != ALERT_SCHEMA_VERSION:
        return result
    result.update({key: value[key] for key in ("first_alert_sent", "baselines", "sent", "last_evaluated_at_utc") if key in value})
    if isinstance(value.get("issues"), Mapping):
        for name in ("failure", "quota"):
            issue = value["issues"].get(name)
            if isinstance(issue, Mapping):
                result["issues"][name].update(issue)
    if not isinstance(result["baselines"], Mapping):
        result["baselines"] = {}
    if not isinstance(result["sent"], Mapping):
        result["sent"] = {}
    return result


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _route_key(offer: Mapping[str, Any]) -> str:
    route = offer.get("route")
    if not isinstance(route, Mapping):
        return "unknown"
    key = f"{route.get('origin', '?')}-{route.get('destination', '?')}"
    return f"{key}:{route['leg']}" if route.get("leg") else key


def _fingerprint(offer: Mapping[str, Any]) -> str:
    itinerary = offer.get("itinerary") if isinstance(offer.get("itinerary"), Mapping) else {}
    segments = itinerary.get("segments") if isinstance(itinerary.get("segments"), list) else []
    identity = {
        "route": offer.get("route"),
        "compatibility_key": offer.get("compatibility_key"),
        "stops": itinerary.get("stops"),
        "duration": itinerary.get("total_duration_minutes"),
        "segments": segments,
    }
    return hashlib.sha256(_canonical(identity).encode()).hexdigest()[:20]


def _candidate_key(offer: Mapping[str, Any]) -> str:
    return f"{_route_key(offer)}:{offer.get('compatibility_key', 'unknown')}"


def _candidates(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, Mapping[str, Any]] = {}
    for result in results:
        if result.get("status") != "success":
            continue
        offers = result.get("offers")
        if not isinstance(offers, list):
            continue
        for offer in offers:
            if not isinstance(offer, Mapping) or not offer.get("comparison_eligible"):
                continue
            price = offer.get("price") if isinstance(offer.get("price"), Mapping) else {}
            amount = _number(price.get("amount"))
            if amount is None:
                continue
            key = _candidate_key(offer)
            previous = selected.get(key)
            if previous is None or amount < previous["price"]["amount"]:
                selected[key] = offer
    return [dict(offer) for offer in selected.values()]


def _ceiling(config: Mapping[str, Any]) -> float | None:
    value = config.get("alert_price_ceiling")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)


def _issue_details(results: Sequence[Mapping[str, Any]], status: str) -> list[str]:
    details = []
    for result in results:
        if result.get("status") != status:
            continue
        route = result.get("route") if isinstance(result.get("route"), Mapping) else {}
        key = f"{route.get('origin', '?')}-{route.get('destination', '?')}"
        error = str(result.get("error", "sem detalhe"))[:160]
        details.append(f"{key}: {error}")
    return details


def _money(amount: Any, currency: Any) -> str:
    value = _number(amount)
    if value is None:
        return "preço indisponível"
    return f"{html.escape(str(currency or 'BRL'))} {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _confirmed_price(offer: Mapping[str, Any]) -> bool:
    price = offer.get("price") if isinstance(offer.get("price"), Mapping) else {}
    return bool(
        price.get("scope") == "group_total"
        and price.get("includes_taxes") is True
        and price.get("includes_infants_on_lap") is True
    )


def _uncertainties(offer: Mapping[str, Any]) -> list[str]:
    price = offer.get("price") if isinstance(offer.get("price"), Mapping) else {}
    baggage = offer.get("baggage") if isinstance(offer.get("baggage"), Mapping) else {}
    values = []
    if not _confirmed_price(offer):
        values.append("total, taxas ou inclusão do bebê não confirmados pela fonte")
    if baggage.get("status") != "confirmed":
        values.append("bagagem não confirmada")
    if offer.get("route_verified") is not True:
        values.append("rota não confirmada")
    itinerary = offer.get("itinerary") if isinstance(offer.get("itinerary"), Mapping) else {}
    segments = itinerary.get("segments") if isinstance(itinerary.get("segments"), list) else []
    if not segments or any(
        not isinstance(item, Mapping)
        or not isinstance(item.get("arrival_airport"), Mapping)
        or not item["arrival_airport"].get("time")
        for item in segments
    ):
        values.append("horários completos podem estar ausentes")
    if price.get("scope") == "unknown":
        values.append("escopo do preço desconhecido")
    return list(dict.fromkeys(values))


def _opportunity_text(item: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    offer = item["offer"]
    route = offer.get("route") if isinstance(offer.get("route"), Mapping) else {}
    passengers = offer.get("passengers") if isinstance(offer.get("passengers"), Mapping) else {}
    price = offer.get("price") if isinstance(offer.get("price"), Mapping) else {}
    itinerary = offer.get("itinerary") if isinstance(offer.get("itinerary"), Mapping) else {}
    segments = itinerary.get("segments") if isinstance(itinerary.get("segments"), list) else []
    departure_airport = segments[0].get("departure_airport") if segments and isinstance(segments[0], Mapping) else None
    arrival_airport = segments[-1].get("arrival_airport") if segments and isinstance(segments[-1], Mapping) else None
    departure = departure_airport.get("time") if isinstance(departure_airport, Mapping) else None
    arrival = arrival_airport.get("time") if isinstance(arrival_airport, Mapping) else None
    leg = route.get("leg")
    leg_text = " · Ida" if leg == "outbound" else " · Volta" if leg == "return" else ""
    if leg == "return":
        dates = str(config.get("return_date", "?"))
    elif leg == "outbound":
        dates = str(config.get("departure_date", config.get("outbound_date", "?")))
    else:
        dates = f"{config.get('departure_date', config.get('outbound_date', '?'))} a {config.get('return_date', '?')}"
    reason = ", ".join(item["reasons"])
    baseline = item.get("baseline_price")
    difference = item.get("difference_percent")
    difference_text = "\nDiferença: primeira referência"
    if difference is not None:
        difference_text = f"\nDiferença: {difference:.1f}% vs. {_money(baseline, price.get('currency'))}"
    stops = itinerary.get("stops")
    stop_text = "direto" if stops == 0 else f"{stops} escala(s)" if isinstance(stops, int) else "escalas desconhecidas"
    schedule = " a ".join(value for value in (departure, arrival) if value) or "não informado"
    link_data = offer.get("links") if isinstance(offer.get("links"), Mapping) else {}
    link = link_data.get("google_flights")
    link_text = f'\nLink: <a href="{html.escape(str(link), quote=True)}">Google Flights</a>' if link else "\nLink: indisponível"
    uncertainties = "; ".join(_uncertainties(offer)) or "nenhuma registrada"
    confirmed = "sim" if _confirmed_price(offer) else "não"
    infants = passengers.get("infants_on_lap", 1)
    infant_label = "bebê" if infants == 1 else "bebês"
    return (
        f"<b>{html.escape(str(route.get('origin', '?')))} → {html.escape(str(route.get('destination', '?')))}</b>"
        f"{html.escape(leg_text)} | {html.escape(dates)}\n"
        f"Preço informado: {_money(price.get('amount'), price.get('currency'))}\n"
        f"Total confirmado para {passengers.get('adults', 2)} adultos + {infants} {infant_label} de colo: {confirmed}{difference_text}\n"
        f"Itinerário: {html.escape(stop_text)}, {itinerary.get('total_duration_minutes', 'duração desconhecida')} min\n"
        f"Horário: {html.escape(schedule)}\n"
        f"Motivo: {html.escape(reason)}\n"
        f"Incertezas: {html.escape(uncertainties)}{link_text}"
    )


def _issue_text(kind: str, action: str, details: Sequence[str]) -> str:
    if action == "recovery":
        title = "Recuperação confirmada"
        body = "Consultas voltaram a funcionar."
    elif kind == "quota":
        title = "Cota esgotada"
        body = "Monitor parou novas consultas até haver cota disponível."
    else:
        title = "Falha persistente"
        body = "Consultas falharam em execuções consecutivas. Últimas ofertas válidas permanecem preservadas."
    detail = "\n".join(f"• {html.escape(item)}" for item in details[:8])
    return f"<b>{title}</b>\n{body}" + (f"\n{detail}" if detail else "")


@dataclass(frozen=True)
class AlertPlan:
    text: str | None
    state: dict[str, Any]
    opportunity_keys: tuple[str, ...]
    issue_actions: tuple[tuple[str, str], ...]
    opportunity_count: int


def build_alert_plan(
    old_state: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    now: datetime,
) -> AlertPlan:
    alert_state = _alert_state(old_state.get("alerts"))
    candidates = _candidates(results)
    sent = dict(alert_state["sent"])
    baselines = dict(alert_state["baselines"])
    first_pending = not bool(alert_state.get("first_alert_sent"))
    opportunities: list[dict[str, Any]] = []
    opportunity_keys: list[str] = []
    ceiling = _ceiling(config)
    for offer in candidates:
        group = _candidate_key(offer)
        price = offer["price"]["amount"]
        fingerprint = _fingerprint(offer)
        previous = baselines.get(group) if isinstance(baselines.get(group), Mapping) else None
        previous_price = _number(previous.get("price")) if previous else None
        reasons: list[str] = []
        if first_pending:
            reasons.append("primeira execução válida")
        elif previous_price is not None and price <= previous_price * 0.95:
            reasons.append("queda de pelo menos 5%")
        if ceiling is not None and price <= ceiling and (previous_price is None or previous_price > ceiling):
            reasons.append(f"abaixo do teto {_money(ceiling, offer['price'].get('currency'))}")
        dedupe_key = f"opportunity:{group}:{fingerprint}:{price}:{offer['price'].get('currency')}"
        if reasons and dedupe_key not in sent:
            difference = None
            if previous_price:
                difference = (price - previous_price) / previous_price * 100
            opportunities.append({"offer": offer, "reasons": reasons, "baseline_price": previous_price, "difference_percent": difference})
            opportunity_keys.append(dedupe_key)
        baselines[group] = {
            "price": price,
            "currency": offer["price"].get("currency"),
            "fingerprint": fingerprint,
            "observed_at_utc": offer.get("observed_at_utc"),
        }

    issues = {name: dict(value) for name, value in alert_state["issues"].items()}
    failure = bool(_issue_details(results, "failure"))
    quota = bool(_issue_details(results, "quota"))
    failure_issue = issues["failure"]
    failure_issue["consecutive"] = int(failure_issue.get("consecutive", 0)) + 1 if failure else 0
    issue_actions: list[tuple[str, str]] = []
    issue_texts: list[str] = []
    if failure and failure_issue["consecutive"] >= 2 and not failure_issue.get("alerted"):
        issue_actions.append(("failure", "active"))
        issue_texts.append(_issue_text("failure", "active", _issue_details(results, "failure")))
    elif not failure and failure_issue.get("active"):
        issue_actions.append(("failure", "recovery"))
        issue_texts.append(_issue_text("failure", "recovery", ()))
    quota_issue = issues["quota"]
    if quota and not quota_issue.get("alerted"):
        issue_actions.append(("quota", "active"))
        issue_texts.append(_issue_text("quota", "active", _issue_details(results, "quota")))
    elif not quota and quota_issue.get("active"):
        issue_actions.append(("quota", "recovery"))
        issue_texts.append(_issue_text("quota", "recovery", ()))

    state = {
        **alert_state,
        "baselines": baselines,
        "issues": issues,
        "last_evaluated_at_utc": now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    blocks = issue_texts + [_opportunity_text(item, config) for item in opportunities]
    text = None
    if blocks:
        text = "<b>Flight Monitor</b>\n\n" + "\n\n".join(blocks)
        if len(text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            raise TelegramError("Telegram alert message exceeds 4096 characters")
    return AlertPlan(text, state, tuple(opportunity_keys), tuple(issue_actions), len(opportunities))


def confirm_alert_plan(plan: AlertPlan, *, sent_at_utc: str, message_id: int) -> dict[str, Any]:
    state = json.loads(json.dumps(plan.state))
    sent = dict(state.get("sent", {}))
    for key in plan.opportunity_keys:
        sent[key] = {"sent_at_utc": sent_at_utc, "message_id": message_id}
    state["sent"] = sent
    if plan.opportunity_keys and not state.get("first_alert_sent"):
        state["first_alert_sent"] = True
    for name, action in plan.issue_actions:
        issue = state["issues"][name]
        if action == "active":
            issue.update({"active": True, "alerted": True})
        else:
            issue.update({"active": False, "alerted": False})
    return state


def format_test_message() -> str:
    return "Flight Monitor: teste único de conexão Telegram confirmado. Nenhuma oferta foi enviada."
