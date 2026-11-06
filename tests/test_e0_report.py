"""E0 summaries use actual samples and keep missing data distinct from zero."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("e0_report", ROOT / "experiments/E0/report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class E0ReportTests(unittest.TestCase):
    def test_reset_and_sparse_counter(self):
        series = [{"values": [[0, "5"], [5, "10"], [10, "2"], [15, "6"]]}]
        self.assertEqual(report.rates(series, 0, 15), round(11 / 15, 3))
        self.assertIsNone(report.rates(series, 1, 6))

    def test_window_is_explicit_and_missing_sources_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            for name in ("metrics", "logs"):
                (path / name).mkdir()
            (path / "metadata.json").write_text(json.dumps({"scenario": "E0", "run_id": "run"}), encoding="utf-8")
            (path / "collection.json").write_text(json.dumps({"status": "finished", "started_at_utc": "1970-01-01T00:00:00Z", "ended_at_utc": "1970-01-01T00:02:00Z"}), encoding="utf-8")
            (path / "logs/collect-worker.log").write_text('prefix {"status":"success","jobId":"a","completedAt":20000,"e2eMs":100}\n', encoding="utf-8")
            result = report.summarize(path, 10, 30)
            self.assertEqual(result["p95_success_e2e_seconds_from_logs"], .1)
            self.assertIsNone(result["success_tasks_per_second_approx"])
            self.assertIn("success_rate_missing", result["warnings"])
            with self.assertRaises(ValueError): report.summarize(path, -1, 30)
            with self.assertRaises(ValueError): report.timestamp("2026-01-01T12:00:00")


if __name__ == "__main__":
    unittest.main()
