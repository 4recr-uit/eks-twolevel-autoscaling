"""Offline checks for independent cost, target sensitivity and recovery tools."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

cost = module("e6_cost", "experiments/E6/cost.py")
e7run = module("e7_run", "experiments/E7/run.py")
e7collect = module("e7_collect", "experiments/E7/collect.py")
e7compare = module("e7_compare", "experiments/E7/compare.py")
e8run = module("e8_run", "experiments/E8/run.py")
recovery = module("e8_recovery", "experiments/E8/recovery.py")

class IndependentExperimentsTests(unittest.TestCase):
    def cost_input(self):
        return {"run_id": "a", "configuration": "hpa", "workload": "step-v4", "region": "us-east-1", "currency": "USD", "price_date": "2026-01-01", "price_source": "example pricing", "source_run": "a", "success_count_method": "job IDs", "window_start": "2026-01-01T00:00:00Z", "window_end": "2026-01-01T01:00:00Z", "processed_success": 1000, "instances": [{"instance_type": "example", "capacity_type": "on-demand", "node_seconds": 3600, "idle_node_seconds": 900, "hourly_price": 2.0}]}

    def test_cost_formula_and_input_rejection(self):
        data = self.cost_input(); value = cost.calculate(data)
        self.assertEqual(value["compute_cost"], 2)
        self.assertEqual(value["idle_cost"], .5)
        self.assertEqual(value["cost_per_1000"], 2)
        other = cost.calculate({**data, "run_id": "b", "instances": [{**data["instances"][0], "node_seconds": 1800, "idle_node_seconds": 0}]})
        self.assertEqual(cost.compare([value, other], "a")[1]["saving_percent_per_1000_vs_baseline"], 50)
        with self.assertRaises(ValueError): cost.calculate({**data, "processed_success": 0})
        with self.assertRaises(ValueError): cost.calculate({**data, "instances": [{**data["instances"][0], "hourly_price": float("nan")} ]})
        with self.assertRaises(ValueError): cost.compare([value, {**other, "workload": "burst"}])
        with self.assertRaises(ValueError): cost.calculate({**data, "window_start": "2026-01-01T00:00:00"})

    def test_scenario_init_requires_correct_variants(self):
        for module, scenario, variants in ((e7run, "E7", ("q-low", "q-medium", "q-high")), (e8run, "E8", ("baseline", "fault"))):
            for variant in variants:
                with self.subTest(scenario=scenario, variant=variant), tempfile.TemporaryDirectory() as tmp:
                    args = module.parser().parse_args(["init", "--variant", variant, "--profile", "burst", "--attempt", "1", "--results-dir", tmp])
                    with mock.patch.object(module, "git_snapshot", return_value={}): path = module.init_run(args)
                    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
                    self.assertEqual((metadata["scenario"], metadata["variant"]), (scenario, variant))
                    with self.assertRaises(ValueError): module.init_run(args)
            with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
                module.parser().parse_args(["init", "--variant", "warm", "--profile", "burst", "--attempt", "1"])

    def test_e7_three_manifests_and_report_comparison(self):
        for variant, target in (("low", "5"), ("medium", "10"), ("high", "20")):
            text = (ROOT / "experiments/E7" / f"keda-{variant}.yaml").read_text(encoding="utf-8")
            self.assertIn(f'queueLength: "{target}"', text)
            self.assertIn("name: e7-orders-sqs", text)
        row = {"run_id": "a", "variant": "q-low", "profile": "burst", "workload": {}, "configuration": {}, "resource_window_before_workload_seconds": 60, "resource_window_after_workload_seconds": 60}
        output = e7compare.compare([row, {**row, "run_id": "b", "variant": "q-high"}])
        self.assertIn("| q-low | 1 |", output); self.assertIn("| q-high | 1 |", output)
        with self.assertRaises(ValueError): e7compare.compare([row, {**row, "run_id": "b", "workload": {"high": 50}}])

    def test_e7_collector_requires_queue_target_for_each_variant(self):
        class Source:
            target = {"namespace": "retailstore", "deployment": "orders-worker", "queue_name": "orders-queue", "aws_region": "us-east-1"}
            queue_urls = {}
            def __init__(self, q): self.q = q
            def worker(self):
                return {"desired": 1, "ready": 1, "node_selector": {"karpenter.sh/nodepool": "e7-orders"},
                        "pods": [{"containers": [{"ready": True, "imageID": "sha256:a"}]}]}
            def controllers(self): return ["hpa/e7-orders-keda-hpa", "scaledobjects.keda.sh/e7-orders-sqs"]
            def queue(self, name):
                self.queue_urls[name] = "https://example/orders-queue"
                return {"counts": dict.fromkeys(e7collect.COUNTS, 0), "redrive_policy": None}
            def kube(self, *args):
                if args[-2] == "deployment":
                    return {"spec": {"template": {"spec": {"containers": [{"name": "orders-worker", "env": [{"name": "SQS_QUEUE_URL", "value": "https://example/orders-queue"}]}]}}}}
                if args[-2] == "scaledobject":
                    return {"metadata": {"uid": "uid", "labels": {"experiments.retailstore.dev/owner": "e7"}},
                            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                            "spec": {"minReplicaCount": 1, "maxReplicaCount": 10, "triggers": [{"type": "aws-sqs-queue", "metadata": {"queueLength": self.q, "queueURLFromEnv": "SQS_QUEUE_URL", "awsRegion": "us-east-1"}}]}}
                return {"metadata": {"ownerReferences": [{"uid": "uid", "kind": "ScaledObject"}]},
                        "spec": {"minReplicas": 1, "maxReplicas": 10}, "status": {"conditions": [{"type": "AbleToScale", "status": "True"}, {"type": "ScalingActive", "status": "True"}]}}
            def prom(self, *args, **kwargs): return {"data": {"result": [{"value": [1, "1"]}]}}
            def nodes(self): return []
        for variant, target in (("q-low", "5"), ("q-medium", "10"), ("q-high", "20")):
            self.assertEqual(e7collect.preflight(Source(target), variant)["variant"], variant)
        with self.assertRaisesRegex(ValueError, "queueLength"):
            e7collect.preflight(Source("10"), "q-low")

    def test_recovery_requires_observation_and_marks_candidate(self):
        marker = {"marked_at_utc": "1970-01-01T00:01:00+00:00", "pod_uid": "old", "pod": "old-pod"}
        samples = [{"observed_at_utc": "1970-01-01T00:00:59+00:00", "data": {"pods": [{"uid": "old"}]}},
                   {"observed_at_utc": "1970-01-01T00:01:05+00:00", "data": {"pods": []}},
                   {"observed_at_utc": "1970-01-01T00:01:10+00:00", "data": {"pods": [{"uid": "new", "name": "new-pod", "created_at": "1970-01-01T00:01:02Z", "phase": "Running", "containers": [{"ready": True}]}]}}]
        result = recovery.analyze(marker, samples)
        self.assertEqual(result["first_observed_target_absent_seconds"], 5)
        self.assertEqual(result["first_observed_new_ready_seconds"], 10)
        self.assertIsNone(recovery.analyze(marker, samples[1:])["first_observed_target_absent_seconds"])

    def test_cli_runs_from_each_folder_and_uses_utf8_on_windows(self):
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cost.json").write_text(json.dumps(self.cost_input()), encoding="utf-8")
            result = subprocess.run([sys.executable, "cost.py", str(root / "cost.json")],
                                    cwd=ROOT / "experiments/E6", env=env, capture_output=True, check=True)
            # The implementation explicitly emits UTF-8 on Windows; elsewhere
            # the caller's PYTHONIOENCODING is respected.
            output = result.stdout.decode("utf-8" if sys.platform == "win32" else "cp1252")
            self.assertEqual(json.loads(output)[0]["compute_cost"], 2)
            for scenario, variant in (("E7", "q-low"), ("E8", "fault")):
                path = ROOT / "experiments" / scenario
                subprocess.run([sys.executable, "run.py", "init", "--variant", variant, "--profile", "burst", "--attempt", "1", "--results-dir", tmp],
                               cwd=path, env=env, capture_output=True, check=True)
                subprocess.run([sys.executable, "report.py", "--help"], cwd=path, env=env, capture_output=True, check=True)

if __name__ == "__main__": unittest.main()
