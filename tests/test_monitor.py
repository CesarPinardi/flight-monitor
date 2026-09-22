import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from flight_monitor.monitor import load_config, run_monitor
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
    def all_fixtures(self, directory: Path) -> None:
        for origin in CONFIG["origins"]:
            for destination in CONFIG["destinations"]:
                (directory / f"google_flights_{origin.lower()}_{destination.lower()}.json").write_text(json.dumps(FIXTURE))

    def test_dry_run_reads_six_fixtures_and_writes_versioned_public_json(self):
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
            self.assertEqual(len(public["history"]["entries"][0]["routes"]), 6)
            self.assertTrue(public["offers"][0]["id"].startswith("offer-"))
            self.assertFalse(public["offers"][0]["baggage"]["included"])
            self.assertEqual(public["offers"][0]["price"]["amount"], 6225)
            self.assertIn("passageiro pagante", public["disclaimer"])
            self.assertEqual(public["offers"][0]["price"]["interpretation"], "provider_value_scope_unknown")
            self.assertEqual(result["telegram"]["status"], "local")
            self.assertFalse(json.loads((Path(root) / "data/state.json").read_text())["alerts"]["first_alert_sent"])

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
            route = state["routes"]["VCP-MIA"]
            self.assertEqual(route["status"], "stale_data")
            self.assertTrue(route["last_valid_offers"])
            public = json.loads((data_dir / "public/data.json").read_text())
            stale = [item for item in public["offers"] if item["route"] == {"origin": "VCP", "destination": "MIA"}]
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
            first = run_monitor(CONFIG, data_dir=root, dry_run=True, fixture_dir=ROOT / "tests/fixtures", now=NOW)
            second = run_monitor(CONFIG, data_dir=root, dry_run=True, fixture_dir=ROOT / "tests/fixtures", now=NOW)
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
                transport=lambda params: FIXTURE,
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
