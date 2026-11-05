"""E1 preflight and report behavior without AWS or Kubernetes."""

import importlib.util
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collect = load("e1_collect", "experiments/E1/collect.py")
report = load("e1_report", "experiments/E1/report.py")
comparison = load("e1_compare", "experiments/E1/compare.py")


class FakeSource:
    def __init__(self, variant):
        self.variant = variant
        self.target = {"namespace": "retailstore", "deployment": "orders-worker", "queue_name": "orders-queue", "aws_region": "us-east-1"}
        self.queue_urls = {}
        self.url = "http://example"
        self.queue_url = "https://example/orders-queue"

    def worker(self):
        count = 2 if self.variant == "fixed" else 1
        return {"desired": count, "ready": count, "pods": [
            {"containers": [{"ready": True, "imageID": "sha256:image"}]} for _ in range(count)]}

    def controllers(self):
        return {"fixed": [], "hpa": ["hpa/e1-orders-cpu"],
                "keda": ["hpa/e1-orders-keda-hpa", "scaledobjects.keda.sh/e1-orders-sqs"]}[self.variant]

    def queue(self, name):
        self.queue_urls[name] = "https://example/orders-queue"
        return {"counts": dict.fromkeys(collect.COUNTS, 0), "redrive_policy": None}

    def kube(self, *args):
        kind = args[-2]
        if kind == "deployment":
            return {"spec": {"template": {"spec": {"containers": [{"name": "orders-worker", "env": [
                {"name": "SQS_QUEUE_URL", "value": self.queue_url}]}]}}}}
        if kind == "scaledobject":
            return {"metadata": {"uid": "scaled-uid", "labels": {"experiments.retailstore.dev/owner": "e1"}},
                    "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                    "spec": {"minReplicaCount": 1, "maxReplicaCount": 10, "triggers": [{"type": "aws-sqs-queue",
                        "metadata": {"queueLength": "10", "scaleOnInFlight": "true", "queueURLFromEnv": "SQS_QUEUE_URL", "awsRegion": "us-east-1"}}]}}
        if self.variant == "keda":
            return {"metadata": {"ownerReferences": [{"uid": "scaled-uid", "kind": "ScaledObject"}]},
                    "spec": {"minReplicas": 1, "maxReplicas": 10},
                    "status": {"conditions": [{"type": "AbleToScale", "status": "True"}, {"type": "ScalingActive", "status": "True"}]}}
        return {"metadata": {"labels": {"experiments.retailstore.dev/owner": "e1"}},
                "status": {"conditions": [{"type": "AbleToScale", "status": "True"}, {"type": "ScalingActive", "status": "True"}]},
                "spec": {"minReplicas": 1, "maxReplicas": 10, "metrics": [{"type": "Resource", "resource": {
                    "name": "cpu", "target": {"type": "Utilization", "averageUtilization": 60}}}]}}

    def prom(self, *_args, **_kwargs):
        n = 2 if self.variant == "fixed" else 1
        return {"data": {"result": [{"value": [1, "1"]} for _ in range(n)]}}

    def nodes(self):
        return [{"name": "node1", "uid": "one"}]


class E1PreflightTests(unittest.TestCase):
    def test_variants_require_expected_controllers_and_queue(self):
        for variant in ("fixed", "hpa", "keda"):
            with self.subTest(variant=variant):
                src = FakeSource(variant)
                self.assertEqual(collect.preflight(src, variant)["variant"], variant)
                src.queue_url = "https://example/other-queue"
                with self.assertRaisesRegex(ValueError, "SQS_QUEUE_URL"):
                    collect.preflight(src, variant)

    def test_wrong_controller_is_rejected(self):
        src = FakeSource("fixed")
        src.controllers = lambda: ["hpa/external"]
        with self.assertRaisesRegex(ValueError, "Autoscaler"):
            collect.preflight(src, "fixed")

    def test_collector_preserves_results_during_scaling(self):
        src = FakeSource("hpa")
        src.worker = lambda: {"uid": "deployment", "generation": 1, "desired": 1, "ready": 1,
                              "containers": [{"name": "orders-worker", "resources": {}}],
                              "pods": [{"name": "worker-1", "uid": "pod1", "node": "node1",
                                        "containers": [{"name": "orders-worker", "ready": True,
                                                        "imageID": "sha256:image", "restartCount": 0}]}]}
        original_prom = src.prom
        def prom(endpoint, **kwargs):
            if endpoint == "query_range":
                return {"status": "success", "data": {"result": [{"metric": {}, "values": [[1, "1"], [6, "2"]]}]}}
            return original_prom(endpoint, **kwargs)
        src.prom = prom
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for folder in ("raw", "metrics", "events", "logs"):
                (directory / folder).mkdir()
            (directory / "raw/k6-summary.json").write_text("{}", encoding="utf-8")
            metadata = {"run_id": "E1-hpa-step-r01", "variant": "hpa"}
            args = argparse.Namespace(interval=.01, step=5, duration=.001, tail_seconds=0)
            with mock.patch("builtins.print"):
                self.assertEqual(collect.Collector(directory, metadata, src, args).run(collect.preflight(src, "hpa")), 0)
            result = json.loads((directory / "collection.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "finished")
            self.assertTrue(result["k6_summary_present"])
            self.assertTrue((directory / "metrics/collect-sqs-samples.jsonl").exists())
            self.assertTrue((directory / "metrics/collect-prometheus-worker_tasks_processed_total.json").exists())


class E1ReportTests(unittest.TestCase):
    def test_compare_rejects_mismatched_workload(self):
        base = {"run_id": "a", "variant": "fixed", "profile": "step", "workload": {"low": 5},
                "resource_window_after_workload_seconds": 300}
        other = {**base, "run_id": "b", "variant": "hpa", "workload": {"low": 6}}
        with self.assertRaisesRegex(ValueError, "cùng profile"):
            comparison.compare([base, other])
        other["workload"] = {"low": 5}
        self.assertIn("| hpa | 1 |", comparison.compare([base, other]))

    def test_counter_reset_and_quantile(self):
        series = {"values": [[10, "5"], [15, "10"], [20, "2"], [25, "6"]]}
        self.assertEqual(report.counter_delta(series, 10, 25), 11)
        self.assertIsNone(report.counter_delta(series, 11, 16))
        self.assertEqual(report.histogram_quantile({"1": 5, "2": 10, "+Inf": 10}, .5), 1)
        self.assertIsNone(report.histogram_quantile({"1": 2, "+Inf": 10}, .95))

    def test_replica_minutes_reject_missing_samples(self):
        points = [{"values": [[0, "2"], [5, "2"], [10, "3"], [15, "3"]]}]
        self.assertEqual(report.replica_minutes(points, 0, 15, 5), 0.58)
        self.assertIsNone(report.replica_minutes(points, 0, 40, 5))

    def test_report_drain_and_fixed_window(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            (path / "raw").mkdir(); (path / "metrics").mkdir()
            def save(name, obj):
                (path / name).write_text(json.dumps(obj), encoding="utf-8")
            save("metadata.json", {"scenario": "E1", "variant": "fixed", "profile": "steady", "run_id": "r01"})
            save("collection.json", {"status": "finished", "started_at_utc": "1970-01-01T00:01:30Z", "ended_at_utc": "1970-01-01T00:02:20Z", "warnings": [],
                                      "prometheus_export_step_seconds": 5, "requested_interval_seconds": 5})
            save("raw/k6-summary.json", {"metrics": {"workload_started_at_unix_ms": {"value": 100000},
                 "workload_finished_at_unix_ms": {"value": 110000}, "e1_accepted_jobs": {"count": 10},
                 "workload_profile_code": {"value": 0}, "workload_low_rate": {"value": 5},
                 "workload_high_rate": {"value": 27}, "workload_batch_size": {"value": 1},
                 "workload_work_units": {"value": 100}, "workload_db_mode_code": {"value": 1}}})
            def matrix(name, metric, values):
                save(f"metrics/collect-prometheus-{name}.json", {"status": "success", "data": {"result": [
                    {"metric": metric, "values": values}]}})
            values = [[t, str(t - 100)] for t in range(100, 131, 5)]
            matrix("worker_tasks_processed_total", {"status": "success"}, values)
            matrix("worker_job_e2e_latency_seconds_bucket", {"le": "+Inf"}, values)
            matrix("ready_replicas", {}, [[t, "2"] for t in range(100, 131, 5)])
            matrix("worker_cpu_counter", {}, values)
            with (path / "metrics/collect-sqs-samples.jsonl").open("w", encoding="utf-8") as f:
                for t, visible in ((105, 4), (110, 2), (115, 0), (120, 0), (125, 0)):
                    counts = dict(zip(collect.COUNTS, (visible, 0, 0)))
                    f.write(json.dumps({"observed_at_utc": f"1970-01-01T00:{t//60:02d}:{t%60:02d}Z", "data": {"main": {"counts": counts}}}) + "\n")
            result = report.summarize(path, after=20)
            self.assertEqual(result["accepted_jobs"], 10)
            self.assertEqual(result["completed_by_status_approx"]["success"], 30)
            self.assertEqual(result["peak_visible_plus_inflight_approx"], 4)
            self.assertEqual(result["drain_confirmation_seconds_approx"], 15)
            self.assertEqual(result["ready_pod_minutes_approx"], 1)
            with self.assertRaisesRegex(ValueError, "đủ thời gian"):
                report.summarize(path, after=60)


if __name__ == "__main__":
    unittest.main()
