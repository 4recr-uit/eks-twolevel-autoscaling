"""E0 tools stay independent of E1 and collect only capacity metrics."""

import importlib.util
from pathlib import Path
import unittest

from test_experiment_collect import FakeSource, target


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("e0_collect", ROOT / "experiments/E0/collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


class E0ToolsTests(unittest.TestCase):
    def test_e0_rejects_autoscaler(self):
        source = FakeSource()
        self.assertEqual(collect.preflight(source)["worker"]["ready"], 1)
        source.controls = ["hpa/orders"]
        with self.assertRaisesRegex(ValueError, "autoscaler"):
            collect.preflight(source)

    def test_capacity_metrics_only(self):
        queries = collect.queries(target())
        self.assertIn("worker_tasks_processed_total", queries)
        self.assertIn("published_jobs", queries)
        self.assertIn("worker_cpu_counter", queries)
        self.assertNotIn("worker_job_e2e_latency_seconds_bucket", queries)
        self.assertNotIn("worker_task_duration_seconds_bucket", queries)


if __name__ == "__main__":
    unittest.main()
