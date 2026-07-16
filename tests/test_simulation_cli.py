from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_simulation_adapter import approved_asot


REPO_ROOT = Path(__file__).resolve().parents[1]


class SimulationCLITests(unittest.TestCase):
    def test_cli_output_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asot = root / "approved.json"
            asot.write_text(json.dumps(approved_asot(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            out = root / "out"
            result = subprocess.run(
                [sys.executable, "-m", "de2sim.cli.challenge_pipeline", "--approved-asot", str(asot), "--output", str(out), "--build-simulation"],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = ["simulation_inputs.json", "simulation_model.json", "telemetry_low.csv", "telemetry_high.csv", "simulation_events.json", "requirements_evaluation.json", "fidelity_comparison.json", "simulation_summary.md", "simulation_data.json", "simulation_viewer.html"]
            for name in expected:
                self.assertTrue((out / name).exists(), name)
                self.assertIn(name, result.stdout)


if __name__ == "__main__":
    unittest.main()
