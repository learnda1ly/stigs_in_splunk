import os
import sys
import unittest
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN = os.path.join(ROOT, "package", "bin")
if BIN not in sys.path:
    sys.path.insert(0, BIN)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from importers.events import event_has_export_body  # noqa: E402
from tools.hec_simulator import simulator  # noqa: E402


class TestHecSimulator(unittest.TestCase):
    def test_build_events_minimal_benchmark(self):
        manifest = os.path.join(
            ROOT, "tests", "fixtures", "baselines", "manifest.yaml"
        )
        meta, rules, source_uri = simulator.load_baseline(Path(manifest), "minimal")
        self.assertEqual(len(rules), 1)
        events = simulator.build_host_events(
            hostname="sim-host",
            ip="10.0.0.99",
            meta=meta,
            rules=rules,
            source_uri=source_uri,
            collection_id="test-collection-id",
            package_id="100001",
        )
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["source_product"], "stigman-watcher")
        self.assertEqual(event["collectionId"], "test-collection-id")
        self.assertEqual(event["package_id"], "100001")
        self.assertEqual(event["assetName"], "sim-host")
        self.assertIn(event["result"], ("pass", "fail", "notapplicable", "notchecked"))
        self.assertTrue(event_has_export_body(event))
        self.assertEqual(event["rule"]["group_id"], "V-000001")
        self.assertEqual(event["stig"]["stig_id"], "Example_STIG")

    def test_deterministic_results(self):
        rule = {"rule_id": "SV-1", "group_id": "V-1"}
        a = simulator.deterministic_result("host-a", rule)
        b = simulator.deterministic_result("host-a", rule)
        c = simulator.deterministic_result("host-b", rule)
        self.assertEqual(a, b)
        self.assertIn(a, simulator.RESULT_CYCLE)


if __name__ == "__main__":
    unittest.main()
