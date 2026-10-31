"""Check explicit Bash commands and Helm contracts without accessing AWS/EKS."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/dev-contract.json").read_text())
DEPLOY = ("02-bootstrap.sh", "01-export-config.sh", "03-deploy-monitoring.sh", "04-deploy-platform.sh",
          "05-deploy-apps.sh", "06-deploy-autoscaling.sh", "07-verify.sh", "09-teardown.sh")


def render(chart, values, overrides=None, namespace="retailstore"):
    command = ["helm", "template", "test", str(ROOT / "kubernetes/charts" / chart),
               "-n", namespace, "-f", str(ROOT / values)]
    if overrides:
        command += ["-f", "-"]
    return subprocess.run(command, input=json.dumps(overrides) if overrides else None,
                          check=True, capture_output=True, text=True).stdout


class ManifestTests(unittest.TestCase):
    def test_platform_custom_resources_and_ami_pin(self):
        rendered = render("platform-config", "kubernetes/environments/dev/platform.yaml",
                          {"runtime": FIXTURE, "nodePool": {"amiAlias": "al2023@v20261001"}}, "karpenter")
        for kind in ("EC2NodeClass", "NodePool", "ClusterTriggerAuthentication", "ServiceMonitor"):
            self.assertIn("kind: " + kind, rendered)
        self.assertIn(FIXTURE["node_role"], rendered)
        invalid = subprocess.run(["helm", "template", "test", str(ROOT / "kubernetes/charts/platform-config"),
            "-f", str(ROOT / "kubernetes/environments/dev/platform.yaml"),
            "--set", "nodePool.amiAlias=al2023@latest"], capture_output=True, text=True)
        self.assertNotEqual(invalid.returncode, 0)

    def test_scaler_names_auth_and_queues_match_manual_app_values(self):
        rendered = render("worker-scaling", "kubernetes/environments/dev/autoscaling.yaml")
        self.assertEqual(rendered.count("kind: ScaledObject"), 3)
        for service, deployment in (("cart", "carts-worker"), ("orders", "orders-worker"), ("checkout", "checkout-worker")):
            self.assertIn("name: " + deployment + "-sqs", rendered)
            self.assertIn("REPLACE_" + service.upper() + "_QUEUE_URL", rendered)
        self.assertEqual(rendered.count("name: keda-sqs-pod-identity"), 3)

    def test_backend_values_override_defaults_without_secrets_or_duplicate_scalers(self):
        backend = ROOT.parent / "retailstore-backend-microservices"
        if not backend.exists(): self.skipTest("Backend checkout is unavailable")
        for service in ("cart", "orders", "checkout", "catalog", "recommendations"):
            values = ROOT / "kubernetes/environments/dev/apps" / (service + ".yaml")
            result = subprocess.run(["helm", "template", service, str(backend / "src" / service / "chart"),
                "-n", "retailstore", "-f", str(values)], check=True, capture_output=True, text=True).stdout
            with self.subTest(service=service):
                self.assertNotIn("managed-ng", result)
                self.assertNotIn("pgbouncer", result)
                self.assertNotIn("kind: Secret", result)
                self.assertNotIn("kind: ScaledObject", result)
                self.assertIn("imagePullPolicy: Always", result)
                self.assertIn(":latest", result)
                if service in ("catalog", "recommendations"):
                    self.assertIn("path: /ready", result)
                else:
                    worker = result.split("templates/deployment-worker.yaml", 1)[1].split("---", 1)[0]
                    self.assertNotIn("  replicas:", worker)
                    self.assertIn("REPLACE_POSTGRES_ENDPOINT", result)
                    self.assertIn("REPLACE_" + service.upper() + "_QUEUE_URL", result)


class ScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bash = os.environ.get("BASH_EXE") or shutil.which("bash")
        if not cls.bash: raise unittest.SkipTest("Set BASH_EXE to Bash")

    def test_bash_syntax(self):
        for script in (ROOT / "scripts").glob("*.sh"):
            subprocess.run([self.bash, "-n", script.as_posix()], check=True, capture_output=True)

    def mock_run(self, script, *arguments, fail="", claims=""):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            trace = temp / "commands.log"
            body = """#!/usr/bin/env bash
name=$(basename "$0")
printf '%s %s\n' "$name" "$*" >> "$COMMAND_TRACE"
if [[ -n "$FAIL_MATCH" && "$name $*" == *"$FAIL_MATCH"* ]]; then exit 42; fi
if [[ "$name $*" == *"get nodeclaims -o name"* ]]; then printf '%s' "$PENDING_CLAIMS"; fi
"""
            for name in ("aws", "terraform", "helm", "kubectl"):
                command = temp / name
                command.write_text(body, encoding="utf-8", newline="\n")
                command.chmod(0o755)
            env = os.environ.copy()
            env.update(PATH=directory + os.pathsep + env["PATH"], COMMAND_TRACE=trace.as_posix(),
                       FAIL_MATCH=fail, PENDING_CLAIMS=claims)
            result = subprocess.run([self.bash, (ROOT / "scripts" / script).as_posix(), *arguments],
                                    cwd=ROOT, env=env, text=True, capture_output=True)
            return result, trace.read_text() if trace.exists() else ""

    def test_deployment_order_and_explicit_chart_paths(self):
        result, calls = self.mock_run("04-deploy-platform.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(calls.index("--install karpenter-crd"), calls.index("--install karpenter oci"))
        self.assertLess(calls.index("--install keda"), calls.index("--install platform-config"))
        result, calls = self.mock_run("05-deploy-apps.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        for service in ("cart", "orders", "checkout", "catalog", "recommendations"):
            self.assertIn("../retailstore-backend-microservices/src/" + service + "/chart", calls)
        self.assertNotIn("python", calls)
        self.assertNotIn(".generated", calls)

    def test_native_error_stops_later_releases(self):
        result, calls = self.mock_run("05-deploy-apps.sh", fail="--install orders")
        self.assertEqual(result.returncode, 42)
        self.assertIn("--install cart", calls)
        self.assertNotIn("--install checkout", calls)

    def test_old_flags_are_rejected_before_any_command(self):
        for script in DEPLOY:
            result, calls = self.mock_run(script, "--apply")
            self.assertEqual(result.returncode, 2, script)
            self.assertEqual(calls, "", script)

    def test_remaining_nodeclaims_keep_controller_installed(self):
        result, calls = self.mock_run("09-teardown.sh", claims="nodeclaim/still-running")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("helm uninstall karpenter ", calls)
        result, calls = self.mock_run("09-teardown.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--cascade=foreground", calls)
        self.assertIn("helm uninstall karpenter ", calls)

    def test_verify_checks_monitoring_rollouts(self):
        result, calls = self.mock_run("07-verify.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rollout status deployment/monitoring-grafana", calls)
        self.assertIn("rollout status statefulset/prometheus-monitoring-kube-prometheus-prometheus", calls)


if __name__ == "__main__": unittest.main()
