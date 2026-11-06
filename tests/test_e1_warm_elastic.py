"""Exercise the standalone E1 warm/elastic data path without AWS or EKS."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location("new_e1_" + name, ROOT / "experiments/E1" / (name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
run, collector, report, compare = [load(x) for x in ("run", "collect", "report", "compare")]

class E1WarmElasticTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("helm"), "Helm is required for template validation")
    def test_helm_worker_and_nodepool_match_e1(self):
        e1 = ROOT / "experiments/E1"
        platform = subprocess.run(["helm", "template", "e1-capacity", str(ROOT / "kubernetes/charts/platform-config"),
            "-f", str(ROOT / "kubernetes/environments/dev/platform.yaml"), "-f", str(e1 / "karpenter-values.yaml")],
            check=True, capture_output=True, text=True).stdout
        self.assertIn("name: e1-orders", platform)
        self.assertIn("consolidateAfter: Never", platform)
        self.assertNotIn("kind: ClusterTriggerAuthentication", platform)
        chart = ROOT.parent / "retailstore-backend-microservices/src/orders/chart"
        if not chart.is_dir(): self.skipTest("Backend chart is unavailable")
        rendered = subprocess.run(["helm", "template", "orders", str(chart),
            "-f", str(ROOT / "kubernetes/environments/dev/apps/orders.yaml"),
            "-f", str(e1 / "autoscaled-values.yaml")], check=True, capture_output=True, text=True).stdout
        worker = rendered.split("templates/deployment-worker.yaml", 1)[1].split("---", 1)[0]
        self.assertIn("karpenter.sh/nodepool: e1-orders", worker)
        self.assertIn("cpu: 500m", worker)
        self.assertNotIn("  replicas:", worker)

    def test_both_branches_require_the_same_keda_and_worker_pool(self):
        class Source:
            target = {"namespace": "retailstore", "deployment": "orders-worker", "queue_name": "orders-queue", "aws_region": "us-east-1"}
            queue_urls = {}
            def worker(self):
                return {"desired": 1, "ready": 1, "node_selector": {"karpenter.sh/nodepool": "e1-orders"},
                        "pods": [{"containers": [{"ready": True, "imageID": "sha256:a"}]}]}
            def controllers(self): return ["hpa/e1-orders-keda-hpa", "scaledobjects.keda.sh/e1-orders-sqs"]
            def queue(self, name):
                self.queue_urls[name] = "https://example/orders-queue"
                return {"counts": dict.fromkeys(collector.COUNTS, 0), "redrive_policy": None}
            def kube(self, *args):
                if args[-2] == "deployment":
                    return {"spec": {"template": {"spec": {"containers": [{"name": "orders-worker", "env": [{"name": "SQS_QUEUE_URL", "value": "https://example/orders-queue"}]}]}}}}
                if args[-2] == "scaledobject":
                    return {"metadata": {"uid": "uid", "labels": {"experiments.retailstore.dev/owner": "e1"}},
                            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                            "spec": {"minReplicaCount": 1, "maxReplicaCount": 10, "triggers": [{"type": "aws-sqs-queue", "metadata": {"queueLength": "10", "scaleOnInFlight": "true", "queueURLFromEnv": "SQS_QUEUE_URL", "awsRegion": "us-east-1"}}]}}
                return {"metadata": {"ownerReferences": [{"uid": "uid", "kind": "ScaledObject"}]},
                        "spec": {"minReplicas": 1, "maxReplicas": 10}, "status": {"conditions": [{"type": "AbleToScale", "status": "True"}, {"type": "ScalingActive", "status": "True"}]}}
            def prom(self, *args, **kwargs): return {"data": {"result": [{"value": [1, "1"]}]}}
            def nodes(self): return []
        for branch in ("warm", "elastic"):
            self.assertEqual(collector.preflight(Source(), branch)["variant"], branch)
        source = Source()
        source.worker = lambda: {"desired": 1, "ready": 1, "node_selector": {}, "pods": [{"containers": [{"ready": True, "imageID": "sha256:a"}]}]}
        with self.assertRaisesRegex(ValueError, "NodePool"):
            collector.preflight(source, "elastic")

    def test_init_is_local_and_rejects_old_variants(self):
        parser = run.parser()
        with tempfile.TemporaryDirectory() as tmp:
            args = parser.parse_args(["init", "--variant", "warm", "--profile", "step", "--attempt", "1", "--results-dir", tmp])
            with mock.patch.object(run, "git_snapshot", return_value={}): directory = run.init_run(args)
            data = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(data["scenario"], "E1")
            self.assertEqual(data["variant"], "warm")
            self.assertEqual(data["design_revision"], "warm-elastic-keda-karpenter-v1")
            with self.assertRaises(ValueError): run.init_run(args)
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            parser.parse_args(["init", "--variant", "hpa", "--profile", "step", "--attempt", "1"])

    def test_topology_sampling_preserves_pending_evidence(self):
        class Source:
            target = {"queue_name": "orders-queue", "namespace": "retailstore"}
            def queue(self, name): return {"counts": dict.fromkeys(collector.COUNTS, 0)}
            def worker(self):
                return {"uid": "deployment", "containers": [], "desired": 2, "ready": 1,
                        "pods": [{"name": "w", "uid": "p", "node": None, "phase": "Pending",
                                  "conditions": [{"type": "PodScheduled", "reason": "Unschedulable"}],
                                  "created_at": "1970-01-01T00:00:00Z", "containers": []}]}
            def nodes(self): return [{"name": "node", "labels": {"karpenter.sh/nodepool": "e1-orders"}}]
            def kube(self, *args):
                if "nodeclaims" in args: return {"items": [{"metadata": {"name": "claim"}, "status": {}}]}
                return {"items": [{"reason": "FailedScheduling", "message": "Insufficient cpu"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for folder in ("events", "metrics", "logs"): (path / folder).mkdir()
            obj = collector.Collector(path, {"run_id": "run"}, Source(), argparse.Namespace())
            obj.before = {"dlq": None, "worker": {"uid": "deployment", "containers": [], "pods": []}}
            with collector.ThreadPoolExecutor(max_workers=3) as pool, mock.patch("builtins.print"): obj.sample(pool)
            topology = json.loads((path / "events/collect-topology-samples.jsonl").read_text(encoding="utf-8"))
            worker = json.loads((path / "events/collect-worker-samples.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(topology["data"]["events"][0]["reason"], "FailedScheduling")
            self.assertEqual(worker["data"]["pods"][0]["conditions"][0]["reason"], "Unschedulable")
            self.assertFalse(obj.errors)

    def test_report_counts_node_idle_and_compares_matching_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for folder in ("raw", "metrics", "events"): (p / folder).mkdir()
            def save(name, data): (p / name).write_text(json.dumps(data), encoding="utf-8")
            save("metadata.json", {"scenario": "E1", "variant": "warm", "profile": "steady", "run_id": "a", "target": {"queue_name": "orders-queue", "aws_region": "us-east-1"}})
            save("collection.json", {"status": "finished", "started_at_utc": "1970-01-01T00:00:00Z", "ended_at_utc": "1970-01-01T00:03:00Z", "requested_interval_seconds": 5, "prometheus_export_step_seconds": 5})
            save("events/collect-before.json", {"worker": {"node_selector": {"karpenter.sh/nodepool": "e1-orders"}, "containers": [], "pods": []}})
            save("raw/k6-summary.json", {"metrics": {"workload_started_at_unix_ms": {"value": 100000}, "workload_finished_at_unix_ms": {"value": 110000}, "e1_accepted_jobs": {"count": 10}, "workload_profile_code": {"value": 0}, "workload_low_rate": {"value": 5}, "workload_high_rate": {"value": 5}, "workload_batch_size": {"value": 1}, "workload_work_units": {"value": 100}, "workload_db_mode_code": {"value": 1}}})
            node = {"labels": {"karpenter.sh/nodepool": "e1-orders"}}
            with (p / "events/collect-topology-samples.jsonl").open("w", encoding="utf-8") as f:
                for t in range(0, 181, 5): f.write(json.dumps({"observed_at_utc": f"1970-01-01T00:{t//60:02d}:{t%60:02d}Z", "data": {"nodes": [node,node]}}) + "\n")
            with (p / "metrics/collect-sqs-samples.jsonl").open("w", encoding="utf-8") as f:
                for t in (115,120,125): f.write(json.dumps({"observed_at_utc": f"1970-01-01T00:{t//60:02d}:{t%60:02d}Z", "data": {"main": {"counts": dict.fromkeys(collector.COUNTS, 0)}}}) + "\n")
            result = report.summarize(p)
            self.assertEqual(result["worker_node_minutes_approx"], 4.33)
            self.assertEqual(result["drain_confirmation_seconds_approx"], 15)
            other = {**result, "run_id": "b", "variant": "elastic"}
            self.assertIn("| elastic | 1 |", compare.compare([result, other]))
            with self.assertRaises(ValueError): compare.compare([result, {**other, "resource_window_before_workload_seconds": 5}])

if __name__ == "__main__": unittest.main()
