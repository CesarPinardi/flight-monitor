import json
from pathlib import Path
import unittest
from unittest.mock import patch

from flight_monitor.serpapi import (
    BudgetExceededError,
    CallBudget,
    MissingApiKeyError,
    SearchRequest,
    SerpApiClient,
    SerpApiError,
)


FIXTURE = Path(__file__).parent / "fixtures/google_flights_gru_mco.json"


class SerpApiClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = json.loads(FIXTURE.read_text())
        self.calls = []
        self.request = SearchRequest(
            departure_id="GRU",
            arrival_id="MCO",
            outbound_date="2027-03-05",
            return_date="2027-03-14",
            adults=2,
            infants_on_lap=1,
            currency="BRL",
        )

    def client(self, response=None, *, budget=None):
        def transport(params):
            self.calls.append(dict(params))
            return self.fixture if response is None else response

        return SerpApiClient("sanitized-key", budget=budget, transport=transport)

    def test_builds_google_flights_request_and_normalizes_without_price_inference(self):
        result = self.client().search(self.request)

        self.assertEqual(self.calls[0]["engine"], "google_flights")
        self.assertEqual(self.calls[0]["type"], "1")
        self.assertEqual(self.calls[0]["adults"], "2")
        self.assertEqual(self.calls[0]["infants_on_lap"], "1")
        self.assertEqual(self.calls[0]["currency"], "BRL")
        self.assertEqual(result["flights"][0]["price"]["amount"], 12450)
        self.assertIsNone(result["flights"][0]["price"]["includes_taxes"])
        self.assertFalse(result["price_contract"]["group_total_verified"])
        self.assertTrue(result["flights"][0]["segments_available"])

    def test_builds_multi_city_request_with_open_jaw_legs(self):
        request = SearchRequest(
            departure_id="GRU",
            arrival_id="MCO",
            return_departure_id="FLL",
            return_arrival_id="VCP",
            outbound_date="2027-03-05",
            return_date="2027-03-14",
            trip_type="multi_city",
        )

        params = request.params()

        self.assertEqual(params["type"], "3")
        self.assertEqual(
            json.loads(params["multi_city_json"]),
            [
                {"departure_id": "GRU", "arrival_id": "MCO", "date": "2027-03-05"},
                {"departure_id": "FLL", "arrival_id": "VCP", "date": "2027-03-14"},
            ],
        )
        self.assertNotIn("outbound_date", params)
        self.assertNotIn("return_date", params)

    def test_return_and_booking_calls_use_same_budget(self):
        client = self.client(budget=CallBudget(limit=2))

        client.returning_flights(self.request, "sanitized-departure-token")
        client.booking_options(self.request, "sanitized-booking-token")

        self.assertEqual(client.budget.used, 2)
        self.assertEqual(self.calls[0]["departure_token"], "sanitized-departure-token")
        self.assertEqual(self.calls[1]["booking_token"], "sanitized-booking-token")

    def test_budget_stops_calls_at_limit(self):
        client = self.client(budget=CallBudget(limit=1))
        client.search(self.request)

        with self.assertRaises(BudgetExceededError):
            client.search(self.request)
        self.assertEqual(len(self.calls), 1)

    def test_missing_key_stops_before_transport(self):
        client = SerpApiClient("", transport=lambda params: self.calls.append(params))

        with self.assertRaises(MissingApiKeyError):
            client.search(self.request)
        self.assertEqual(self.calls, [])

    def test_api_error_is_not_normalized_as_success(self):
        client = self.client({"error": "invalid api key"})

        with self.assertRaisesRegex(SerpApiError, "invalid api key"):
            client.search(self.request)

    def test_timeout_becomes_client_error(self):
        client = SerpApiClient("sanitized-key", timeout=7)

        with patch("flight_monitor.serpapi.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(SerpApiError, "timed out"):
                client.search(self.request)
        self.assertEqual(client.budget.used, 1)

    def test_from_config_maps_project_config_names(self):
        request = SearchRequest.from_config(
            {
                "departure_date": "2027-03-05",
                "return_date": "2027-03-14",
                "adults": 2,
                "infants_on_lap": 1,
                "cabin": "economy",
                "currency": "BRL",
                "trip_type": "round_trip",
            },
            departure_id="GRU",
            arrival_id="MCO",
        )

        self.assertEqual(request.params()["arrival_id"], "MCO")
        self.assertEqual(request.params()["travel_class"], "1")


if __name__ == "__main__":
    unittest.main()
