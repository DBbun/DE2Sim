from __future__ import annotations

import unittest

from de2sim.simulation.asot_adapter import extract_simulation_facts
from de2sim.simulation.high_fidelity import run_high_fidelity
from de2sim.simulation.low_fidelity import run_low_fidelity
from de2sim.simulation.scenario import default_scenario
from de2sim.simulation.validation import SimulationValidationError, compare_fidelities, evaluate_requirements, validate_simulation_output
from tests.test_simulation_adapter import approved_asot


class SimulationValidationTests(unittest.TestCase):
    def test_requirement_evaluation_pass_and_comparison_generation(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        scenario = default_scenario()
        low = run_low_fidelity(facts, scenario)
        high = run_high_fidelity(facts, scenario)
        validate_simulation_output(low, scenario["maximum_simulation_time_s"]["value"])
        validate_simulation_output(high, scenario["maximum_simulation_time_s"]["value"])
        requirements = evaluate_requirements(facts, [low, high])
        self.assertEqual(requirements["low"]["low_battery_return"]["status"], "pass")
        self.assertEqual(requirements["high"]["maximum_speed"]["status"], "pass")
        comparison = compare_fidelities(low, high, requirements)
        self.assertIn("landing_time_s", comparison["differences"])
        self.assertIn("neither fidelity", comparison["explanation"])
        self.assertEqual(comparison["scenario_feasibility"]["scenario_feasibility_status"], "pass")
        self.assertEqual(comparison["scenario_feasibility"]["per_fidelity"]["low"]["terminal_reason"], "landed")
        self.assertGreater(comparison["scenario_feasibility"]["per_fidelity"]["high"]["battery_reserve_at_landing_percent"], 0.0)
        self.assertIsInstance(requirements["low"]["maximum_speed"]["telemetry_indices"], dict)

    def test_validation_rejects_positive_speed_after_zero_battery(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        scenario = default_scenario()
        low = run_low_fidelity(facts, scenario)
        low["telemetry"][-1]["battery_energy_wh"] = 0.0
        low["telemetry"][-1]["commanded_speed_mps"] = 1.0
        low["terminal_reason"] = "battery_depleted_before_landing"
        low["events"] = [event for event in low["events"] if event["event_type"] != "landed"]
        low["events"].append({"event_type": "battery_depleted", "time_s": low["telemetry"][-1]["time_s"]})
        with self.assertRaisesRegex(SimulationValidationError, "positive speed"):
            validate_simulation_output(low, scenario["maximum_simulation_time_s"]["value"])


if __name__ == "__main__":
    unittest.main()
