"""Offline checks for E6 Spot isolation and the fixed cost window."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(f"e6_spot_{name}", ROOT / "experiments/E6" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


window = module("window")
cost = module("cost")
collector = module("collect")
report = module("report")


class E6SpotTests(unittest.TestCase):
    def fixture(self, root, scenario="E6", capacity="spot", last_sample=630):
        p = Path(root)
        (p / "events").mkdir()
        (p / "raw").mkdir()
        def save(name, value):
            (p / name).write_text(json.dumps(value), encoding="utf-8")
        def iso(t):
            return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()
        pool = "e6-spot-orders" if scenario == "E6" else "e1-orders"
        save("metadata.json", {"scenario": scenario, "variant": "elastic", "profile": "step", "config": 1,
                               "run_id": f"{scenario}-elastic-step-r01", "target": {"aws_region": "us-east-1"}})
        save("collection.json", {"status": "finished", "started_at_utc": iso(90), "ended_at_utc": iso(640),
                                 "requested_interval_seconds": 5})
        metrics = {name: {"value": value} for name, value in {
            "workload_model_version": 4, "workload_profile_code": 1, "workload_low_rate": 5,
            "workload_high_rate": 20, "workload_batch_size": 1, "workload_work_units": 100,
            "workload_db_mode_code": 1, "workload_started_at_unix_ms": 100000,
            "workload_finished_at_unix_ms": 520000}.items()}
        metrics["e1_accepted_jobs"] = {"count": 4800}
        save("raw/k6-summary.json", {"metrics": metrics})
        labels = {"karpenter.sh/nodepool": pool, "node.kubernetes.io/instance-type": "c7i-flex.large",
                  "topology.kubernetes.io/zone": "us-east-1a", "karpenter.sh/capacity-type": capacity}
        with (p / "events/collect-topology-samples.jsonl").open("w", encoding="utf-8") as stream:
            for t in range(95, last_sample + 1, 5):
                nodes = [{"labels": labels}] * (2 if 300 <= t < 500 else 1)
                stream.write(json.dumps({"observed_at_utc": iso(t), "data": {"nodes": nodes}}) + "\n")
        return p

    def test_window_and_cost_match_525_second_node_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = window.build(self.fixture(tmp), 0.0275, "2026-11-08", "Spot price assumption")
        self.assertEqual(data["instances"][0]["node_seconds"], 725)
        self.assertEqual(data["instances"][0]["capacity_type"], "spot")
        self.assertEqual(data["processed_success"], 4800)
        self.assertIn("Giả định", data["success_count_method"])
        result = cost.calculate(data)
        self.assertEqual(result["window_seconds"], 525)
        self.assertAlmostEqual(result["compute_cost"], 725 / 3600 * 0.0275)

    def test_refuses_wrong_capacity_and_missing_end_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "capacity"):
                window.build(self.fixture(tmp, capacity="on-demand"), 0.0275, "2026-11-08", "price")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "mẫu topology"):
                window.build(self.fixture(tmp, last_sample=620), 0.0275, "2026-11-08", "price")

    def test_report_uses_same_fixed_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.fixture(tmp)
            (p / "metrics").mkdir()
            (p / "metrics/collect-sqs-samples.jsonl").write_text("", encoding="utf-8")
            (p / "events/collect-before.json").write_text(json.dumps({"worker": {}, "autoscaler": {
                "min_replica_count": 1, "hpa_min_replicas": 1}}), encoding="utf-8")
            summary = report.summarize(p)
        self.assertEqual(summary["resource_window_seconds"], 525)
        self.assertEqual(summary["resource_window_before_workload_seconds"], 0)
        self.assertEqual(summary["resource_window_after_workload_seconds"], 105)
        self.assertAlmostEqual(summary["worker_node_minutes_approx"], round(725 / 60, 2))

    def test_preflight_refuses_on_demand_node(self):
        class Source:
            target = {"deployment": "orders-worker"}
            def worker(self):
                return {"desired": 1, "ready": 1, "node_selector": {"karpenter.sh/nodepool": "e6-spot-orders"},
                        "pods": [{"node": "node-1", "containers": [{"ready": True, "imageID": "sha256:a"}]}]}
            def nodes(self):
                return [{"name": "node-1", "labels": {"karpenter.sh/nodepool": "e6-spot-orders",
                        "node.kubernetes.io/instance-type": "c7i-flex.large", "karpenter.sh/capacity-type": "on-demand"},
                        "conditions": [{"type": "Ready", "status": "True"}]}]
        with self.assertRaisesRegex(ValueError, "Spot"):
            collector.preflight(Source(), "elastic")

    def test_preflight_accepts_matching_spot_and_keda(self):
        class Source:
            target = {"namespace": "retailstore", "deployment": "orders-worker", "queue_name": "orders-queue", "aws_region": "us-east-1"}
            def __init__(self): self.queue_urls = {}
            def worker(self):
                return {"desired": 1, "ready": 1, "node_selector": {"karpenter.sh/nodepool": "e6-spot-orders"},
                        "containers": [{"name": "orders-worker", "resources": {"requests": {"cpu": "500m", "memory": "256Mi"}},
                                        "env": {"WORKER_CONCURRENCY": "1"}}],
                        "pods": [{"node": "node-1", "containers": [{"ready": True, "imageID": "sha256:a"}]}]}
            def nodes(self):
                return [{"name": "node-1", "labels": {"karpenter.sh/nodepool": "e6-spot-orders",
                         "node.kubernetes.io/instance-type": "c7i-flex.large", "karpenter.sh/capacity-type": "spot"},
                         "conditions": [{"type": "Ready", "status": "True"}]}]
            def controllers(self): return ["hpa/e6-spot-orders-keda-hpa", "scaledobjects.keda.sh/e6-spot-orders-sqs"]
            def queue(self, name):
                self.queue_urls[name] = "https://example/orders-queue"
                return {"counts": dict.fromkeys(collector.COUNTS, 0), "redrive_policy": None}
            def kube(self, *args):
                if args[-2] == "deployment":
                    return {"spec": {"template": {"spec": {"containers": [{"name": "orders-worker", "env": [
                        {"name": "SQS_QUEUE_URL", "value": "https://example/orders-queue"}]}]}}}}
                if args[-2] == "scaledobject":
                    return {"metadata": {"uid": "uid", "labels": {"experiments.retailstore.dev/owner": "e6"}},
                            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                            "spec": {"minReplicaCount": 1, "maxReplicaCount": 10, "triggers": [{"type": "aws-sqs-queue",
                                "metadata": {"queueLength": "10", "queueURLFromEnv": "SQS_QUEUE_URL", "awsRegion": "us-east-1"}}]}}
                return {"metadata": {"ownerReferences": [{"uid": "uid", "kind": "ScaledObject"}]},
                        "spec": {"minReplicas": 1, "maxReplicas": 10}, "status": {"conditions": [
                            {"type": "AbleToScale", "status": "True"}, {"type": "ScalingActive", "status": "True"}]}}
            def prom(self, *args, **kwargs): return {"data": {"result": [{"value": [1, "1"]}]}}
        self.assertEqual(collector.preflight(Source(), "elastic")["autoscaler"]["min_replica_count"], 1)

    @unittest.skipUnless(shutil.which("helm"), "Helm not installed")
    def test_helm_nodepool_is_spot_only(self):
        rendered = subprocess.run(["helm", "template", "e6-spot-capacity",
            str(ROOT / "kubernetes/charts/platform-config"),
            "-f", str(ROOT / "kubernetes/environments/dev/platform.yaml"),
            "-f", str(ROOT / "experiments/E6/karpenter-values.yaml")],
            capture_output=True, text=True, check=True).stdout
        self.assertIn('values: ["spot"]', rendered)
        self.assertIn("name: e6-spot-orders", rendered)
        self.assertIn("consolidateAfter: Never", rendered)
        self.assertNotIn('values: ["on-demand"]', rendered)


if __name__ == "__main__":
    unittest.main()
