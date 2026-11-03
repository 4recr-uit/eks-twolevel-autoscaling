"""Local tests for experiment records and read-only cluster inspection."""

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
SPEC = importlib.util.spec_from_file_location("experiment_run", ROOT / "experiments/_shared/run.py")
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)


class ExperimentRunTests(unittest.TestCase):
    def args(self, results_dir):
        return run.parser().parse_args([
            "init", "--scenario", "E1", "--variant", "fixed", "--profile", "step",
            "--attempt", "1", "--context", "test-context", "--namespace", "retailstore",
            "--deployment", "orders-worker", "--queue", "orders-queue", "--region", "us-east-1",
            "--results-dir", str(results_dir),
        ])

    def test_init_records_inputs_without_marking_a_run_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root / "results")
            with mock.patch.object(run, "git_snapshot", return_value={"commit": "abc", "branch": "dev", "dirty": False}):
                created = run.init_run(args, repo_root=root)
            self.assertEqual(created.name, "E1-fixed-step-r01")
            data = json.loads((created / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(data["target"]["kube_context"], "test-context")
            self.assertEqual(data["infrastructure_repo"]["commit"], "abc")
            self.assertIsNone(data["started_at_utc"])
            self.assertIsNone(data["ended_at_utc"])
            self.assertEqual(data["validity"], "not_assessed")
            for item in ("raw", "metrics", "events", "logs", "notes.md"):
                self.assertTrue((created / item).exists())

    def test_existing_run_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(Path(directory))
            created = run.init_run(args)
            marker = created / "raw" / "saved.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "không ghi đè"):
                run.init_run(args)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_cli_creates_a_run_in_an_explicit_local_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [
                sys.executable, str(ROOT / "experiments/_shared/run.py"), "init",
                "--scenario", "E5", "--variant", "warm-1", "--profile", "idle-step",
                "--attempt", "3", "--context", "test", "--namespace", "retailstore",
                "--deployment", "orders-worker", "--queue", "orders-queue",
                "--region", "us-east-1", "--results-dir", directory,
            ]
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            metadata = Path(directory) / "E5" / "E5-warm-1-idle-step-r03" / "metadata.json"
            self.assertEqual(json.loads(metadata.read_text(encoding="utf-8"))["validity"], "not_assessed")

    def test_invalid_identifiers_and_queue_url_are_rejected(self):
        for value in ("../escape", "fixed/step", "", "UPPER"):
            with self.subTest(value=value), self.assertRaises(Exception):
                run.token(value)
        with self.assertRaises(Exception):
            run.queue_name("https://sqs.example/account/queue")
        self.assertEqual(run.queue_name("orders-queue"), "orders-queue")
        self.assertEqual(run.queue_name("orders.fifo"), "orders.fifo")

    def test_inspect_reports_only_matching_deployment_controllers(self):
        args = run.parser().parse_args([
            "inspect", "--context", "test", "--namespace", "retailstore", "--deployment", "orders-worker"
        ])
        response = [
            {},
            {"spec": {"replicas": 2}, "status": {"readyReplicas": 1}},
            {"items": [
                {"metadata": {"name": "cpu"}, "spec": {"scaleTargetRef": {"kind": "Deployment", "name": "orders-worker"}}},
                {"metadata": {"name": "same-name-other-kind"}, "spec": {"scaleTargetRef": {"kind": "StatefulSet", "name": "orders-worker"}}},
                {"metadata": {"name": "other"}, "spec": {"scaleTargetRef": {"kind": "Deployment", "name": "cart-worker"}}},
            ]},
            {"items": [{"metadata": {"name": "orders-sqs"}, "spec": {"scaleTargetRef": {"name": "orders-worker"}}}]},
        ]
        with mock.patch.object(run, "kubectl_json", side_effect=response) as calls:
            result = run.inspect_cluster(args)
        self.assertEqual(result["desired_replicas"], 2)
        self.assertEqual(result["ready_replicas"], 1)
        self.assertEqual(result["controllers_targeting_deployment"], ["hpa/cpu", "scaledobjects.keda.sh/orders-sqs"])
        self.assertEqual(calls.call_count, 4)
        self.assertTrue(all(call.args[0] == "test" for call in calls.call_args_list))

    def test_kubectl_failure_does_not_look_like_an_empty_result(self):
        failed = subprocess.CompletedProcess([], 1, stdout="", stderr="forbidden")
        with mock.patch.object(run.subprocess, "run", return_value=failed) as invoked:
            with self.assertRaisesRegex(RuntimeError, "forbidden"):
                run.kubectl_json("ctx", "get", "hpa")
        self.assertEqual(invoked.call_args.args[0], ["kubectl", "--context", "ctx", "get", "hpa", "-o", "json"])

    @unittest.skipUnless(os.name == "nt", "Windows pipe encoding regression")
    def test_help_handles_legacy_windows_pipe_encoding(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1252"
        result = subprocess.run(
            [sys.executable, str(ROOT / "experiments/_shared/run.py"), "init", "--help"],
            capture_output=True, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertIn("--scenario", result.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
