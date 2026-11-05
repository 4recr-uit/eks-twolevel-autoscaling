"""Check experiment runbook paths from their own working directories."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExperimentWorkdirTests(unittest.TestCase):
    def test_runbook_paths_and_backup_locations(self):
        for scenario in ("E0", "E1", "E2", "E3", "E4"):
            with self.subTest(scenario=scenario):
                directory = ROOT / "experiments" / scenario
                text = (directory / "run.sh").read_text(encoding="utf-8")
                self.assertNotIn("cd /d/WorkSpace/UITMagnolia/eks-twolevel-autoscaling\n", text)
                self.assertTrue((directory / "../../../retailstore-backend-microservices/src/orders/chart").is_dir())
                expected_backup = ROOT / ".generated" / ("e3" if scenario == "E4" else scenario.lower())
                for path in set(re.findall(r"(?:\.\./)+\.generated/e[0-9]", text)):
                    self.assertEqual((directory / path).resolve(), expected_backup.resolve())
                self.assertIn("../../.generated/" + ("e3" if scenario == "E4" else scenario.lower()), text)
                for path in re.findall(r"(?:-f|apply -f)\s+((?:\.{1,2}/)[^\s]+\.yaml)", text):
                    if ".generated/" not in path:
                        self.assertTrue((directory / path).is_file(), f"{scenario}: {path}")

    def test_reused_workloads_and_e3_charts_resolve(self):
        for scenario in ("E2", "E3", "E4"):
            directory = ROOT / "experiments" / scenario
            self.assertTrue((directory / "../E1/workload.js").is_file())
        for scenario in ("E3", "E4"):
            directory = ROOT / "experiments" / scenario
            self.assertTrue((directory / "../../kubernetes/charts/platform-config/Chart.yaml").is_file())
            self.assertTrue((directory / "../../kubernetes/environments/dev/platform.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
