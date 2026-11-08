"""Each experiment can use its own files from its own working directory."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"


class ExperimentWorkdirTests(unittest.TestCase):
    def test_scenarios_have_local_tools_and_configuration(self):
        expected = {
            "E0": ("run.py", "run.sh", "collect.py", "report.py", "workload.js", "fixed-values.yaml"),
            "E1": ("run.py", "run.sh", "collect.py", "report.py", "compare.py", "keda-config1.yaml", "keda-config2.yaml", "keda-config3.yaml", "karpenter-values.yaml"),
            "E2": ("run.py", "run.sh", "collect.py", "report.py", "timeline.py", "keda.yaml", "karpenter-values.yaml"),
            "E3": ("run.py", "run.sh", "collect.py", "report.py", "compare.py", "hpa.yaml", "keda.yaml"),
            "E4": ("run.py", "run.sh", "collect.py", "report.py", "first_job.py", "keda.yaml"),
            "E5": ("run.py", "run.sh", "collect.py", "report.py", "first_job.py", "keda-cold.yaml", "keda-warm-1.yaml", "keda-warm-2.yaml"),
            "E6": ("cost.py", "input.example.txt"),
            "E7": ("run.py", "run.sh", "collect.py", "report.py", "compare.py", "keda-low.yaml", "keda-medium.yaml", "keda-high.yaml"),
            "E8": ("run.py", "run.sh", "collect.py", "report.py", "mark.py", "recovery.py", "keda.yaml"),
        }
        for scenario, names in expected.items():
            self.assertTrue((EXPERIMENTS / scenario / "README.md").is_file())
            for name in names:
                with self.subTest(scenario=scenario, name=name):
                    self.assertTrue((EXPERIMENTS / scenario / name).is_file())

    def test_profile_copies_match_e0_model(self):
        for name in ("stead.js", "step.js", "burst.js", "workload-common.js"):
            reference = (EXPERIMENTS / "E0" / name).read_text(encoding="utf-8")
            # E2 has its own burst workload for cold-start measurement.
            for scenario in ("E1", "E3", "E4", "E5", "E7", "E8"):
                with self.subTest(scenario=scenario, name=name):
                    content = (EXPERIMENTS / scenario / name).read_text(encoding="utf-8")
                    if name == "workload-common.js":
                        content = content.replace(scenario.lower() + "_accepted_jobs", "e1_accepted_jobs")
                        content = content.replace(scenario.lower() + "_failed_requests", "e1_failed_requests")
                        content = content.replace("test-" + scenario.lower(), "test-e1")
                    self.assertEqual(reference, content)

    def test_e2_only_keeps_burst_workload(self):
        e2 = EXPERIMENTS / "E2"
        self.assertTrue((e2 / "burst.js").is_file())
        for name in ("stead.js", "step.js", "snapshot.py"):
            self.assertFalse((e2 / name).exists())

    def test_scenario_code_does_not_import_removed_common_directories(self):
        for scenario in ("E0", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
            for path in (EXPERIMENTS / scenario).glob("*"):
                if path.is_file() and path.suffix in (".py", ".sh", ".js", ".md"):
                    text = path.read_text(encoding="utf-8")
                    with self.subTest(scenario=scenario, path=path.name):
                        self.assertNotIn("../_shared/", text)
                        self.assertNotIn("../workloads/", text)
        self.assertFalse((EXPERIMENTS / "_shared").exists())
        self.assertFalse((EXPERIMENTS / "workloads").exists())


if __name__ == "__main__":
    unittest.main()
