from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from de2sim.simulation.runner import run_simulation_build
from tests.test_simulation_adapter import approved_asot


class SimulationRunnerTests(unittest.TestCase):
    def test_runner_outputs_are_deterministic_and_do_not_mutate_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asot_path = root / "approved.json"
            original = json.dumps(approved_asot(), indent=2, sort_keys=True) + "\n"
            asot_path.write_text(original, encoding="utf-8")
            out1 = root / "out1"
            out2 = root / "out2"
            paths1 = run_simulation_build(asot_path, out1)
            paths2 = run_simulation_build(asot_path, out2)
            self.assertEqual(asot_path.read_text(encoding="utf-8"), original)
            self.assertEqual((out1 / "simulation_data.json").read_text(encoding="utf-8"), (out2 / "simulation_data.json").read_text(encoding="utf-8"))
            self.assertEqual((out1 / "telemetry_low.csv").read_text(encoding="utf-8"), (out2 / "telemetry_low.csv").read_text(encoding="utf-8"))
            data = json.loads((out1 / "simulation_data.json").read_text(encoding="utf-8"))
            self.assertEqual(data["simulation_status"]["low"]["scenario_feasibility_status"], "pass")
            self.assertEqual(data["simulation_status"]["high"]["scenario_feasibility_status"], "pass")
            self.assertGreater(data["simulation_status"]["low"]["battery_reserve_at_landing_percent"], 0.0)
            self.assertGreater(data["simulation_status"]["high"]["battery_reserve_at_landing_percent"], 0.0)
            self.assertLessEqual(data["simulation_status"]["low"]["battery_reserve_at_landing_percent"], 15.0)
            self.assertLessEqual(data["simulation_status"]["high"]["battery_reserve_at_landing_percent"], 15.0)
            self.assertEqual(set(paths1), {"simulation_inputs", "simulation_model", "telemetry_low", "telemetry_high", "simulation_events", "requirements_evaluation", "fidelity_comparison", "simulation_summary", "simulation_data", "simulation_viewer"})


if __name__ == "__main__":
    unittest.main()
