import unittest
from datetime import datetime, timezone

from flight_monitor.telegram import (
    TelegramClient,
    build_alert_plan,
    confirm_alert_plan,
)


NOW = datetime(2027, 1, 10, 15, 0, tzinfo=timezone.utc)
CONFIG = {
    "departure_date": "2027-03-05",
    "return_date": "2027-03-14",
    "alert_price_ceiling": 12000,
}


def offer(price=12450, *, link="https://example.test/flights?a=1&b=2"):
    return {
        "id": "offer-test",
        "status": "complete",
        "route": {"origin": "GRU", "destination": "MCO"},
        "route_verified": True,
        "passengers": {"adults": 2, "infants_on_lap": 1},
        "price": {
            "amount": price,
            "currency": "BRL",
            "scope": "unknown",
            "includes_taxes": None,
            "includes_infants_on_lap": None,
        },
        "itinerary": {
            "stops": 1,
            "total_duration_minutes": 600,
            "segments": [{
                "departure_airport": {"id": "GRU", "time": "2027-03-05 09:00"},
                "arrival_airport": {"id": "MCO", "time": "2027-03-05 19:00"},
                "flight_number": "T 1",
            }],
        },
        "baggage": {"status": "unknown"},
        "compatibility_key": "same-search",
        "observed_at_utc": "2027-01-10T15:00:00Z",
        "comparison_eligible": True,
        "links": {"google_flights": link},
    }


def results(value):
    return [{"status": "success", "offers": [value]}]


class TelegramTests(unittest.TestCase):
    def test_transport_confirms_message_without_exposing_token(self):
        calls = []

        def transport(params):
            calls.append(params)
            return {"ok": True, "result": {"message_id": 9}}

        result = TelegramClient("secret-token", "123", transport=transport).send_message("hello")

        self.assertEqual(result.message_id, 9)
        self.assertEqual(calls[0]["chat_id"], "123")
        self.assertNotIn("secret-token", str(calls[0]))

    def test_first_alert_escape_drop_ceiling_and_deduplication(self):
        first = build_alert_plan({}, results(offer()), CONFIG, NOW)
        self.assertIsNotNone(first.text)
        self.assertIn("&amp;", first.text)
        self.assertIn("Total confirmado", first.text)
        confirmed = confirm_alert_plan(first, sent_at_utc="2027-01-10T15:00:00Z", message_id=1)

        unchanged = build_alert_plan({"alerts": confirmed}, results(offer()), CONFIG, NOW)
        self.assertIsNone(unchanged.text)

        cheaper = build_alert_plan({"alerts": confirmed}, results(offer(11800)), CONFIG, NOW)
        self.assertIsNotNone(cheaper.text)
        self.assertIn("5%", cheaper.text)
        confirmed_again = confirm_alert_plan(cheaper, sent_at_utc="2027-01-11T15:00:00Z", message_id=2)
        self.assertIsNone(build_alert_plan({"alerts": confirmed_again}, results(offer(11800)), CONFIG, NOW).text)

    def test_failure_alert_requires_two_runs_and_recovery(self):
        failure = [{"status": "failure", "route": {"origin": "GRU", "destination": "MCO"}, "error": "timeout"}]
        first = build_alert_plan({}, failure, CONFIG, NOW)
        self.assertIsNone(first.text)
        second = build_alert_plan({"alerts": first.state}, failure, CONFIG, NOW)
        self.assertIn("Falha persistente", second.text)
        active = confirm_alert_plan(second, sent_at_utc="2027-01-10T15:00:00Z", message_id=3)
        recovery = build_alert_plan({"alerts": active}, [{"status": "success", "offers": []}], CONFIG, NOW)
        self.assertIn("Recuperação confirmada", recovery.text)


if __name__ == "__main__":
    unittest.main()
