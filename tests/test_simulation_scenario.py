from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from de2sim.simulation.scenario import ScenarioError, default_scenario, load_scenario


class SimulationScenarioTests(unittest.TestCase):
    def test_default_scenario_classifies_demonstration_assumptions(self) -> None:
        scenario = default_scenario()
        self.assertTrue(all(item["source_classification"] == "demonstration_assumption" for item in scenario.values()))
        self.assertIn("explanation", scenario["home_x_m"])

    def test_scenario_file_override_handling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.json"
            path.write_text(json.dumps({"mission_waypoint_x_m": {"value": 1200, "unit": "m", "source_classification": "user_scenario", "explanation": "test override"}}), encoding="utf-8")
            scenario = load_scenario(path)
        self.assertEqual(scenario["mission_waypoint_x_m"]["value"], 1200.0)
        self.assertEqual(scenario["mission_waypoint_x_m"]["source_classification"], "user_scenario")

    def test_scenario_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps({"high_fidelity_time_step_s": 99}), encoding="utf-8")
            with self.assertRaisesRegex(ScenarioError, "time step"):
                load_scenario(path)


if __name__ == "__main__":
    unittest.main()
