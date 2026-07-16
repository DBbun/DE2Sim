from __future__ import annotations

import unittest

from de2sim.simulation.asot_adapter import extract_simulation_facts
from de2sim.simulation.high_fidelity import run_high_fidelity
from de2sim.simulation.low_fidelity import run_low_fidelity
from de2sim.simulation.scenario import default_scenario
from tests.test_simulation_adapter import approved_asot


class SimulationHighFidelityTests(unittest.TestCase):
    def test_deterministic_high_fidelity_and_distinct_from_low(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        scenario = default_scenario()
        high = run_high_fidelity(facts, scenario)
        self.assertEqual(high, run_high_fidelity(facts, scenario))
        low = run_low_fidelity(facts, scenario)
        self.assertNotEqual(high["telemetry"], low["telemetry"])
        self.assertEqual(high["telemetry"][-1]["state"], "landed")
        self.assertLessEqual(high["telemetry"][-1]["distance_to_home_m"], scenario["arrival_radius_m"]["value"])

    def test_high_fidelity_max_speed_energy_and_events(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        output = run_high_fidelity(facts, default_scenario())
        self.assertTrue(all(max(row["ground_speed_mps"], row["commanded_speed_mps"]) <= facts.max_speed_mps for row in output["telemetry"]))
        energies = [row["battery_energy_wh"] for row in output["telemetry"]]
        self.assertEqual(energies, sorted(energies, reverse=True))
        events = [event["event_type"] for event in output["events"]]
        self.assertTrue(events.index("battery_threshold_reached") < events.index("return_to_base_invoked") < events.index("home_position_reached") < events.index("landed"))
        self.assertTrue(output["mission_completed"])
        self.assertEqual(output["terminal_reason"], "landed")
        self.assertGreater(output["battery_reserve_at_landing_percent"], 0.0)

    def test_high_fidelity_stationary_waypoint_hold_zero_commanded_and_ground_speed(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        output = run_high_fidelity(facts, default_scenario())
        telemetry = output["telemetry"]
        waypoint_indices = [i for i, row in enumerate(telemetry) if row["event"] == "mission_waypoint_reached"]
        self.assertEqual(len(waypoint_indices), 1)
        waypoint_index = waypoint_indices[0]
        rtb_index = next(i for i, row in enumerate(telemetry) if row["event"] == "return_to_base_invoked")
        hold_rows = telemetry[waypoint_index:rtb_index]
        self.assertGreater(len(hold_rows), 2)
        self.assertTrue(all(row["state"] == "mission_flight" for row in hold_rows))
        self.assertTrue(all(row["commanded_speed_mps"] == 0.0 for row in hold_rows))
        self.assertTrue(all(row["ground_speed_mps"] == 0.0 for row in hold_rows))
        self.assertTrue(all(row["distance_to_waypoint_m"] == 0.0 for row in hold_rows))
        self.assertEqual({row["x_m"] for row in hold_rows}, {hold_rows[0]["x_m"]})
        self.assertEqual({row["y_m"] for row in hold_rows}, {hold_rows[0]["y_m"]})
        self.assertLess(hold_rows[-1]["battery_energy_wh"], hold_rows[0]["battery_energy_wh"])
        moving_return = next(row for row in telemetry[rtb_index + 1 :] if row["state"] == "return_to_base" and row["ground_speed_mps"] > 0.0)
        self.assertGreater(moving_return["commanded_speed_mps"], 0.0)
        self.assertTrue(output["mission_completed"])
        self.assertGreater(output["battery_reserve_at_landing_percent"], 0.0)

    def test_high_fidelity_zero_battery_terminal_condition(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        scenario = default_scenario()
        scenario["high_fidelity_idle_power_w"]["value"] = 3000.0
        scenario["high_fidelity_speed_power_coefficient"]["value"] = 3.0
        output = run_high_fidelity(facts, scenario)
        self.assertFalse(output["mission_completed"])
        self.assertEqual(output["terminal_reason"], "battery_depleted_before_landing")
        self.assertEqual(output["telemetry"][-1]["event"], "battery_depleted")
        self.assertEqual(output["telemetry"][-1]["commanded_speed_mps"], 0.0)
        self.assertEqual(output["telemetry"][-1]["ground_speed_mps"], 0.0)
        self.assertNotIn("landed", [event["event_type"] for event in output["events"]])


if __name__ == "__main__":
    unittest.main()
