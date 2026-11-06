"""Verify that the separate k6 scripts preserve their scheduled workloads."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
K6 = shutil.which("k6")


@unittest.skipUnless(K6, "k6 is required to inspect workload scripts")
class WorkloadScriptsTests(unittest.TestCase):
    def inspect(self, profile, *env):
        args = [K6, "inspect"]
        for item in env:
            args.extend(["-e", item])
        args.append(str(ROOT / "experiments" / "E1" / f"{profile}.js"))
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")

    def test_profile_schedules(self):
        expected = {
            "stead": [(5, "2m0s")],
            "step": [(5, "1m0s"), (10, "1m0s"), (15, "1m0s"), (20, "1m0s"),
                     (15, "1m0s"), (10, "1m0s"), (5, "1m0s")],
            "burst": [(5, "1m0s"), (40, "30s"), (5, "1m0s")],
        }
        for profile, levels in expected.items():
            with self.subTest(profile=profile):
                result = self.inspect(profile)
                self.assertEqual(result.returncode, 0, result.stderr)
                scenario = json.loads(result.stdout)["scenarios"]["jobs"]
                self.assertEqual(scenario["executor"], "ramping-arrival-rate")
                self.assertEqual(scenario["startRate"], 5)
                stages = scenario["stages"]
                self.assertEqual([(s["target"], s["duration"]) for s in stages if s["duration"] != "0s"], levels)
                self.assertTrue(all(s["duration"] == "0s" for s in stages[1::2]))

    def test_invalid_step_and_obsolete_profile_are_rejected(self):
        self.assertNotEqual(self.inspect("step", "HIGH_RATE=27").returncode, 0)
        self.assertNotEqual(self.inspect("stead", "LOW_RATE=10").returncode, 0)
        self.assertNotEqual(self.inspect("burst", "HIGH_RATE=40").returncode, 0)
        self.assertNotEqual(self.inspect("burst", "LOW_RATE=5").returncode, 0)
        self.assertNotEqual(self.inspect("burst", "PROFILE=step").returncode, 0)


if __name__ == "__main__":
    unittest.main()
