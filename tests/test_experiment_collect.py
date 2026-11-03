"""Collector lifecycle, failure reporting and result preservation without AWS/EKS."""

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("experiment_collect", ROOT / "experiments/_shared/collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


def target():
    return {"kube_context": "test", "namespace": "retailstore", "deployment": "orders-worker",
            "queue_name": "orders-queue", "aws_region": "us-east-1"}


class FakeSource:
    def __init__(self):
        self.target, self.url = target(), "http://127.0.0.1:9090"
        self.controls = []
        self.fail_export = False
        self.backlog = 0
        self.fail_poll = False

    def worker(self):
        return {"name": "orders-worker", "uid": "dep1", "generation": 1, "desired": 1, "ready": 1,
                "pods": [{"name": "orders-worker-abc", "uid": "pod1", "node": "node1",
                          "containers": [{"name": "orders-worker", "ready": True, "restartCount": 0, "imageID": "sha256:abc"}]}]}

    def nodes(self):
        return [{"name": "node1", "uid": "node-uid"}]

    def controllers(self):
        return self.controls

    def queue(self, name):
        if self.fail_poll:
            raise RuntimeError("SQS timed out")
        return {"queue_name": name, "counts": dict(zip(collect.COUNTS, (self.backlog, 0, 0))), "redrive_policy": None}

    def prom(self, endpoint, **params):
        if endpoint == "query_range":
            if self.fail_export:
                raise RuntimeError("Prometheus disconnected")
            return {"status": "success", "data": {"resultType": "matrix", "result": [
                {"metric": {}, "values": [[100, "1"], [105, "2"]]}]}}
        return {"status": "success", "data": {"resultType": "vector", "result": [
            {"metric": {"__name__": "up"}, "value": [100, "1"]}]}}

    def command(self, *args, **kwargs):
        return "2026-11-03T00:00:00Z task log\nraw body: private-message\n"


class CollectorTests(unittest.TestCase):
    def make_run(self, root):
        directory = Path(root) / "E0-single-worker-steady-r01"
        directory.mkdir()
        for sub in ("raw", "metrics", "events", "logs"):
            (directory / sub).mkdir()
        data = {"schema_version": 1, "run_id": directory.name, "scenario": "E0", "target": target(),
                "started_at_utc": None, "ended_at_utc": None, "validity": "not_assessed"}
        (directory / "metadata.json").write_text(json.dumps(data), encoding="utf-8")
        (directory / "notes.md").write_text("keep my notes", encoding="utf-8")
        return directory, data

    def args(self):
        return argparse.Namespace(interval=.01, step=5, duration=.001, tail_seconds=0)

    def test_full_capture_preserves_user_metadata_and_records_files(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, data = self.make_run(temp)
            original = (directory / "metadata.json").read_bytes()
            source = FakeSource()
            collector = collect.Collector(directory, data, source, self.args())
            with mock.patch("builtins.print"):
                code = collector.run(collect.preflight(source))
            self.assertEqual(code, 0)
            report = json.loads((directory / "collection.json").read_text())
            self.assertEqual(report["status"], "finished")
            self.assertEqual(report["validity"], "not_assessed")
            self.assertIsNotNone(report["ended_at_utc"])
            self.assertGreaterEqual(report["sample_counts"]["sqs"], 2)
            self.assertEqual((directory / "metadata.json").read_bytes(), original)
            self.assertEqual((directory / "notes.md").read_text(), "keep my notes")
            self.assertTrue((directory / "events/collect-after.json").is_file())
            self.assertTrue((directory / "collection-summary.md").is_file())
            self.assertNotIn("private-message", (directory / "logs/collect-orders-worker-abc-orders-worker.log").read_text())
            with self.assertRaisesRegex(ValueError, "attempt"):
                collect.load_run(directory)

    def test_failed_exports_are_partial_and_other_data_survives(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, data = self.make_run(temp)
            source = FakeSource()
            before = collect.preflight(source)
            source.fail_export = True
            collector = collect.Collector(directory, data, source, self.args())
            with mock.patch("builtins.print"):
                self.assertEqual(collector.run(before), 2)
            report = json.loads((directory / "collection.json").read_text())
            self.assertEqual(report["status"], "partial")
            self.assertGreater(len(report["errors"]), 0)
            self.assertTrue((directory / "metrics/collect-sqs-samples.jsonl").is_file())

    def test_ctrl_c_requests_stop_and_still_finalizes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, data = self.make_run(temp)
            source = FakeSource()
            args = self.args()
            args.duration = None
            collector = collect.Collector(directory, data, source, args)
            original = collector.sample
            def stop_during_sample(pool):
                original(pool)
                collect.signal.raise_signal(collect.signal.SIGINT)
            with mock.patch.object(collector, "sample", side_effect=stop_during_sample), mock.patch("builtins.print"):
                self.assertEqual(collector.run(collect.preflight(source)), 0)
            self.assertEqual(json.loads((directory / "collection.json").read_text())["status"], "finished")

    def test_preflight_rejects_backlog_controllers_and_missing_prometheus(self):
        source = FakeSource()
        source.backlog = 3
        with self.assertRaisesRegex(ValueError, "Queue"):
            collect.preflight(source)
        source.backlog = 0
        source.controls = ["hpa/orders-cpu"]
        with self.assertRaisesRegex(ValueError, "autoscaler"):
            collect.preflight(source)
        source.controls = []
        with mock.patch.object(source, "prom", return_value={"data": {"result": []}}):
            with self.assertRaisesRegex(ValueError, "UP"):
                collect.preflight(source)

    def test_bad_metadata_and_existing_capture_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, data = self.make_run(temp)
            data["target"]["deployment"] = "--all-namespaces"
            (directory / "metadata.json").write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                collect.load_run(directory)
            data["target"] = target()
            (directory / "metadata.json").write_text(json.dumps(data), encoding="utf-8")
            (directory / "metrics/collect-sqs-samples.jsonl").write_text("keep", encoding="utf-8")
            with self.assertRaises(ValueError):
                collect.load_run(directory)
            self.assertEqual((directory / "metrics/collect-sqs-samples.jsonl").read_text(), "keep")

    def test_queries_scope_worker_and_preserve_histogram_buckets(self):
        q = collect.queries(target())
        self.assertIn('namespace="retailstore"', q["worker_tasks_processed_total"])
        self.assertIn('pod=~"orders', q["worker_tasks_processed_total"])
        self.assertIn("worker_job_e2e_latency_seconds_bucket", q)
        self.assertNotIn("rate(", q["worker_tasks_processed_total"])
        for bad in ("http://user:pass@localhost", "file:///secret", "http://localhost/?token=x"):
            with self.assertRaises(argparse.ArgumentTypeError):
                collect.prometheus_url(bad)

    def test_drift_is_flagged_instead_of_calling_experiment_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, data = self.make_run(temp)
            collector = collect.Collector(directory, data, FakeSource(), self.args())
            collector.before = {"worker": FakeSource().worker()}
            changed = copy.deepcopy(collector.before["worker"])
            changed["pods"][0]["uid"] = "replacement"
            collector.observe_worker(changed)
            self.assertIn("worker_configuration_or_pod_changed", collector.warnings)


if __name__ == "__main__":
    unittest.main()
