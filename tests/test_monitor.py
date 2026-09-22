import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from flight_monitor.monitor import _request, load_config, normalize_offer, routes_from_config, run_monitor
from flight_monitor.serpapi import normalize_response
from flight_monitor.storage import ConcurrentRunError, JsonStore


ROOT = Path(__file__).parents[1]
CONFIG = load_config(ROOT / "config/search.json")
FIXTURE = json.loads((ROOT / "tests/fixtures/google_flights_gru_mco.json").read_text())
NOW = datetime(2027, 1, 10, 15, 0, tzinfo=timezone.utc)


def config(**changes):
    value = dict(CONFIG)
    value.update(changes)
    return value


class MonitorTests(unittest.TestCase):
    def one_way_fixture(self, params):
        payload = deepcopy(FIXTURE)
        flight = payload["best_flights"][0]
        segment = flight["flights"][0]
        segment["departure_airport"]["id"] = params["departure_id"]
        segment["arrival_airport"]["id"] = params["arrival_id"]
        flight["type"] = "One way"
        return payload

    def all_fixtures(self, directory: Path) -> None:
        for route in routes_from_config(CONFIG):
            payload = deepcopy(FIXTURE)
            flight = payload["best_flights"][0]
            segment = flight["flights"][0]
            segment["departure_airport"]["id"] = route.origin
            segment["arrival_airport"]["id"] = route.destination
            flight["type"] = "One way"
            if route.trip_type == "multi_city":
                returning = deepcopy(segment)
                returning["departure_airport"]["id"] = route.return_origin
                returning["arrival_airport"]["id"] = route.return_destination
                flight["flights"].append(returning)
                flight["type"] = "Multi-city"
            suffix = "_package" if route.trip_type == "multi_city" else ""
            (directory / f"google_flights_{route.origin.lower()}_{route.destination.lower()}{suffix}.json").write_text(json.dumps(payload))

    def test_dry_run_reads_both_legs_and_writes_versioned_public_json(self):
        with tempfile.TemporaryDirectory() as root:
            fixtures = Path(root) / "fixtures"
            fixtures.mkdir()
            self.all_fixtures(fixtures)
            result = run_monitor(CONFIG, data_dir=Path(root) / "data", dry_run=True, fixture_dir=fixtures, now=NOW)
            self.assertEqual(result["status"], "success")
            state = json.loads((Path(root) / "data/state.json").read_text())
            public = json.loads((Path(root) / "data/public/data.json").read_text())
            self.assertEqual(state["budget"]["basic_used"], 0)
            self.assertEqual(state["budget"]["basic_limit"], 186)
            self.assertEqual(public["schema_version"], 1)
            self.assertEqual(public["presentation"]["timezone"], "America/Sao_Paulo")
            self.assertEqual(public["history"]["kind"], "daily_route_minimum")
            self.assertEqual(len(public["history"]["entries"][0]["routes"]), len(routes_from_config(CONFIG)))
            self.assertEqual({offer["route"].get("leg") for offer in public["offers"]}, {None, "outbound", "return"})
            self.assertEqual(
                sum(offer["itinerary"]["type"] == "multi_city" for offer in public["offers"]),
                len(CONFIG["itineraries"]),
            )
            self.assertTrue(public["offers"][0]["id"].startswith("offer-"))
            self.assertFalse(public["offers"][0]["baggage"]["included"])
            self.assertEqual(
                public["offers"][0]["route"],
                {"origin": "GRU", "destination": "MCO", "leg": "outbound"},
            )
            self.assertEqual(public["offers"][0]["price"]["amount"], 6225)
            self.assertIn("passageiro pagante", public["disclaimer"])
            self.assertEqual(public["offers"][0]["price"]["interpretation"], "provider_value_scope_unknown")
            self.assertEqual(result["telegram"]["status"], "local")
            self.assertFalse(json.loads((Path(root) / "data/state.json").read_text())["alerts"]["first_alert_sent"])

    def test_return_leg_builds_one_way_request_for_return_route(self):
        return_config = config(trip_leg="return")
        route = routes_from_config(return_config)[0]
        request = _request(return_config, route)

        first_return = return_config["itineraries"][0]["return"]
        self.assertEqual(route.key, f"{first_return['origin']}-{first_return['destination']}:return")
        self.assertEqual(request.params()["departure_id"], first_return["origin"])
        self.assertEqual(request.params()["arrival_id"], first_return["destination"])
        self.assertEqual(request.params()["outbound_date"], "2027-03-14")
        self.assertEqual(request.params()["type"], "2")
        self.assertNotIn("return_date", request.params())

    def test_both_legs_builds_separate_one_way_routes(self):
        both_config = config(trip_leg="both", include_packages=False, daily_basic_searches=12)

        routes = routes_from_config(both_config)

        self.assertEqual(len(routes), 12)
        self.assertEqual({route.leg for route in routes}, {"outbound", "return"})
        self.assertEqual(routes[0].key, "GRU-MCO:outbound")
        first_return = both_config["itineraries"][0]["return"]
        self.assertEqual(routes[6].key, f"{first_return['origin']}-{first_return['destination']}:return")

    def test_package_builds_multi_city_request_and_route(self):
        package_config = config(trip_leg="both", include_packages=True, daily_basic_searches=48)
        route = routes_from_config(package_config)[-1]
        request = _request(package_config, route)

        last = package_config["itineraries"][-1]
        self.assertEqual(
            route.key,
            f"{last['outbound']['origin']}-{last['outbound']['destination']}:{last['return']['origin']}-{last['return']['destination']}",
        )
        self.assertEqual(request.params()["type"], "3")
        self.assertEqual(
            json.loads(request.params()["multi_city_json"]),
            [
                {"departure_id": "VCP", "arrival_id": "MIA", "date": "2027-03-05"},
                {
                    "departure_id": last["return"]["origin"],
                    "arrival_id": last["return"]["destination"],
                    "date": "2027-03-14",
                },
            ],
        )

    def test_multi_city_package_price_is_comparable_from_provider_result(self):
        route = next(route for route in routes_from_config(CONFIG) if route.trip_type == "multi_city")
        request = _request(CONFIG, route)
        payload = deepcopy(FIXTURE)
        flight = payload["best_flights"][0]
        flight["flights"][0]["departure_airport"]["id"] = route.origin
        flight["flights"][0]["arrival_airport"]["id"] = route.destination
        flight["type"] = "Multi-city"
        normalized = normalize_response(payload, request)["flights"][0]

        offer = normalize_offer(normalized, request, route, "2027-01-10T15:00:00Z")

        self.assertTrue(offer["route_verified"])
        self.assertTrue(offer["comparison_eligible"])

    def test_missing_fixture_is_partial_failure_and_last_valid_offer_stays_stale(self):
        with tempfile.TemporaryDirectory() as root:
            fixtures = Path(root) / "fixtures"
            fixtures.mkdir()
            self.all_fixtures(fixtures)
            data_dir = Path(root) / "data"
            first = run_monitor(CONFIG, data_dir=data_dir, dry_run=True, fixture_dir=fixtures, now=NOW)
            (fixtures / "google_flights_vcp_mia.json").unlink()
            second = run_monitor(CONFIG, data_dir=data_dir, dry_run=True, fixture_dir=fixtures, now=NOW.replace(day=11))
            self.assertEqual(first["status"], "success")
            self.assertEqual(second["status"], "failure")
            state = json.loads((data_dir / "state.json").read_text())
            route = state["routes"]["VCP-MIA:outbound"]
            self.assertEqual(route["status"], "stale_data")
            self.assertTrue(route["last_valid_offers"])
            public = json.loads((data_dir / "public/data.json").read_text())
            stale = [
                item for item in public["offers"]
                if item["route"].get("origin") == "VCP" and item["route"].get("destination") == "MIA"
                and item["route"].get("leg") == "outbound"
            ]
            self.assertTrue(stale and stale[0]["stale"])

    def test_monthly_budget_stops_after_limit_and_marks_quota(self):
        calls = []

        def transport(params):
            calls.append(params)
            return FIXTURE

        with tempfile.TemporaryDirectory() as root:
            result = run_monitor(config(monthly_basic_limit=2), data_dir=root, api_key="test", transport=transport, now=NOW)
            self.assertEqual(result["status"], "quota")
            self.assertEqual(len(calls), 2)
            state = json.loads((Path(root) / "state.json").read_text())
            self.assertEqual(state["budget"]["basic_used"], 2)

    def test_same_local_day_is_duplicate_without_force(self):
        with tempfile.TemporaryDirectory() as root:
            fixtures = Path(root) / "fixtures"
            fixtures.mkdir()
            self.all_fixtures(fixtures)
            first = run_monitor(CONFIG, data_dir=root, dry_run=True, fixture_dir=fixtures, now=NOW)
            second = run_monitor(CONFIG, data_dir=root, dry_run=True, fixture_dir=fixtures, now=NOW)
            self.assertNotEqual(first["status"], "duplicate")
            self.assertEqual(second["status"], "duplicate")
            self.assertEqual(second["calls"], 0)

    def test_configured_telegram_marks_alert_only_after_confirmation(self):
        sent = []

        def telegram_transport(payload):
            sent.append(payload)
            return {"ok": True, "result": {"message_id": 17}}

        with tempfile.TemporaryDirectory() as root:
            fixtures = Path(root) / "fixtures"
            fixtures.mkdir()
            self.all_fixtures(fixtures)
            data_dir = Path(root) / "data"
            result = run_monitor(
                CONFIG,
                data_dir=data_dir,
                dry_run=False,
                fixture_dir=fixtures,
                api_key="serp-test",
                transport=self.one_way_fixture,
                telegram_token="telegram-secret",
                telegram_chat_id="chat-123",
                telegram_transport=telegram_transport,
                now=NOW,
            )
            self.assertEqual(result["telegram"]["status"], "sent")
            self.assertEqual(sent[0]["chat_id"], "chat-123")
            self.assertNotIn("telegram-secret", json.dumps(sent))
            state = json.loads((data_dir / "state.json").read_text())
            self.assertTrue(state["alerts"]["first_alert_sent"])
            self.assertNotIn("telegram-secret", (data_dir / "public/data.json").read_text())

    def test_lock_blocks_second_writer(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonStore(root)
            with store.lock():
                with self.assertRaises(ConcurrentRunError):
                    with store.lock():
                        pass


if __name__ == "__main__":
    unittest.main()
