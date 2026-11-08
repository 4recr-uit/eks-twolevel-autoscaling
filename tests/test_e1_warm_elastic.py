"""Exercise the standalone E1 warm/elastic data path without AWS or EKS."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location("new_e1_" + name, ROOT / "experiments/E1" / (name + ".py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
run, collector, report, compare = [load(x) for x in ("run", "collect", "report", "compare")]
plot_spec = importlib.util.spec_from_file_location("e1_plot_data", ROOT / "experiments/E1/visualize-scripts/e1_plot_data.py")
plot_data = importlib.util.module_from_spec(plot_spec)
sys.modules[plot_spec.name] = plot_data
plot_spec.loader.exec_module(plot_data)

class E1WarmElasticTests(unittest.TestCase):
    def test_keda_configs_only_change_minimum(self):
        manifests = [(ROOT / f"experiments/E1/keda-config{i}.yaml").read_text(encoding="utf-8") for i in (1, 2, 3)]
        normalized = []
        for content, minimum in zip(manifests, (1, 3, 5)):
            self.assertRegex(content, rf"(?m)^  minReplicaCount: {minimum}$")
            normalized.append(re.sub(r"(?m)^  minReplicaCount: \d+$", "  minReplicaCount: X", content))
        self.assertEqual(normalized[0], normalized[1])
        self.assertEqual(normalized[0], normalized[2])

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
            def __init__(self, replicas=1, branch="warm"):
                self.replicas, self.branch, self.queue_urls = replicas, branch, {}
            def worker(self):
                return {"desired": self.replicas, "ready": self.replicas, "node_selector": {"karpenter.sh/nodepool": "e1-orders"},
                        "pods": [{"node": f"node-{i // 3}", "containers": [{"ready": True, "imageID": "sha256:a"}]}
                                 for i in range(self.replicas)]}
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
                            "spec": {"minReplicaCount": self.replicas, "maxReplicaCount": 10, "triggers": [{"type": "aws-sqs-queue", "metadata": {"queueLength": "10", "scaleOnInFlight": "true", "queueURLFromEnv": "SQS_QUEUE_URL", "awsRegion": "us-east-1"}}]}}
                return {"metadata": {"ownerReferences": [{"uid": "uid", "kind": "ScaledObject"}]},
                        "spec": {"minReplicas": self.replicas, "maxReplicas": 10}, "status": {"conditions": [{"type": "AbleToScale", "status": "True"}, {"type": "ScalingActive", "status": "True"}]}}
            def prom(self, *args, **kwargs): return {"data": {"result": [{"value": [1, "1"]} for _ in range(self.replicas)]}}
            def nodes(self):
                count = 4 if self.branch == "warm" else (self.replicas + 2) // 3
                return [{"name": f"node-{i}", "labels": {"karpenter.sh/nodepool": "e1-orders"},
                         "conditions": [{"type": "Ready", "status": "True"}]} for i in range(count)]
        for branch in ("warm", "elastic"):
            self.assertEqual(collector.preflight(Source(branch=branch), branch)["variant"], branch)
            for config, replicas in ((2, 3), (3, 5)):
                result = collector.preflight(Source(replicas, branch), branch, config)
                self.assertEqual(result["autoscaler"]["min_replica_count"], replicas)
                with self.assertRaisesRegex(ValueError, "worker"):
                    collector.preflight(Source(1), branch, config)
        source = Source()
        source.worker = lambda: {"desired": 1, "ready": 1, "node_selector": {}, "pods": [{"containers": [{"ready": True, "imageID": "sha256:a"}]}]}
        with self.assertRaisesRegex(ValueError, "NodePool"):
            collector.preflight(source, "elastic")
        with self.assertRaisesRegex(ValueError, "không chạy worker"):
            collector.preflight(Source(3, "warm"), "elastic", 2)

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

    def test_new_config_run_ids_and_metadata_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            for config, minimum in ((2, 3), (3, 5)):
                args = run.parser().parse_args(["init", "--variant", "elastic", "--profile", "burst", "--attempt", "1", "--config", str(config), "--results-dir", tmp])
                with mock.patch.object(run, "git_snapshot", return_value={}): directory = run.init_run(args)
                self.assertEqual(directory.name, f"E1-config{config}-elastic-burst-r01")
                data = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
                self.assertEqual((data["config"], data["min_workers"]), (config, minimum))

    def test_plot_loads_new_configs_and_rejects_idle_elastic_node(self):
        def write(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for config, minimum in ((2, 3), (3, 5)):
                for variant in ("warm", "elastic"):
                    run_id = f"E1-config{config}-{variant}-burst-r01"
                    directory = root / run_id
                    write(directory / "metadata.json", {"scenario": "E1", "run_id": run_id, "variant": variant,
                          "profile": "burst", "attempt": 1, "config": config, "min_workers": minimum})
                    write(directory / "report.json", {"run_id": run_id, "variant": variant, "profile": "burst",
                          "config": config, "min_workers": minimum,
                          "workload": {"model_version": 3, "low_request_per_second": 5, "high_request_per_second": 40},
                          "configuration": {"queue_name": "orders-queue"}, "peak_visible_plus_inflight_approx": 50,
                          "worker_node_minutes_approx": 4, "latency_seconds_approx_all_statuses": {"p95": 2},
                          "resource_window_before_workload_seconds": 60, "resource_window_after_workload_seconds": 60,
                          "workload_started_utc": "1970-01-01T00:01:40Z", "workload_finished_utc": "1970-01-01T00:04:10Z"})
                    write(directory / "collection.json", {"status": "finished", "errors": [], "requested_interval_seconds": 5})
                    node_count = 4 if variant == "warm" else (minimum + 2) // 3
                    nodes = [{"name": f"node-{i}", "labels": {"karpenter.sh/nodepool": "e1-orders"},
                              "conditions": [{"type": "Ready", "status": "True"}]} for i in range(node_count)]
                    pods = [{"node": f"node-{i // 3}"} for i in range(minimum)]
                    sample = {"observed_at_utc": "1970-01-01T00:01:35Z"}
                    write(directory / "events/collect-worker-samples.jsonl", {**sample, "data": {"ready": minimum, "desired": minimum, "pods": pods}})
                    write(directory / "events/collect-topology-samples.jsonl", {**sample, "data": {"nodes": nodes}})
                    write(directory / "metrics/collect-sqs-samples.jsonl", {**sample, "data": {"main": {"counts": dict.fromkeys(collector.COUNTS, 0)},
                          "dlq": {"counts": dict.fromkeys(collector.COUNTS, 0)}}})
                self.assertEqual(len(plot_data.load_profile(root, "burst", [1], config)), 2)
            path = root / "E1-config3-elastic-burst-r01/events/collect-topology-samples.jsonl"
            extra = json.loads(path.read_text(encoding="utf-8"))
            extra["data"]["nodes"].append({"name": "idle", "labels": {"karpenter.sh/nodepool": "e1-orders"},
                                           "conditions": [{"type": "Ready", "status": "True"}]})
            write(path, extra)
            with self.assertRaisesRegex(ValueError, "không chạy worker"):
                plot_data.load_profile(root, "burst", [1], 3)

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
            histogram = {"status": "success", "data": {"result": [
                {"metric": {"le": "1"}, "values": [[100, "0"], [110, "10"]]},
                {"metric": {"le": "+Inf"}, "values": [[100, "0"], [110, "10"]]}]}}
            for name in ("worker_job_queue_wait_seconds_bucket", "worker_task_duration_seconds_bucket"):
                save(f"metrics/collect-prometheus-{name}.json", histogram)
            result = report.summarize(p)
            self.assertEqual(result["worker_node_minutes_approx"], 4.33)
            self.assertEqual(result["drain_confirmation_seconds_approx"], 15)
            self.assertEqual(result["queue_wait_seconds_approx_all_statuses"]["p95"], .95)
            self.assertEqual(result["task_duration_seconds_approx_all_statuses"]["p95"], .95)
            other = {**result, "run_id": "b", "variant": "elastic"}
            self.assertIn("| elastic | 1 |", compare.compare([result, other]))
            with self.assertRaises(ValueError): compare.compare([result, {**other, "resource_window_before_workload_seconds": 5}])
            with self.assertRaisesRegex(ValueError, "config"):
                compare.compare([result, {**other, "config": 2, "min_workers": 3}])
            meta = json.loads((p / "metadata.json").read_text(encoding="utf-8"))
            save("metadata.json", {**meta, "config": 2, "min_workers": 3})
            with self.assertRaisesRegex(ValueError, "autoscaler"):
                report.summarize(p)
            save("events/collect-before.json", {"worker": {"node_selector": {}, "containers": [], "pods": []},
                "autoscaler": {"min_replica_count": 3, "max_replica_count": 10, "hpa_min_replicas": 3}})
            self.assertEqual(report.summarize(p)["min_workers"], 3)

if __name__ == "__main__": unittest.main()
