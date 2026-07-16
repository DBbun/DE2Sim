from __future__ import annotations

import unittest

from de2sim.simulation.asot_adapter import extract_simulation_facts
from de2sim.simulation.low_fidelity import run_low_fidelity
from de2sim.simulation.scenario import default_scenario
from tests.test_simulation_adapter import approved_asot


class SimulationLowFidelityTests(unittest.TestCase):
    def test_deterministic_low_fidelity_telemetry_and_transition_order(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        scenario = default_scenario()
        first = run_low_fidelity(facts, scenario)
        second = run_low_fidelity(facts, scenario)
        self.assertEqual(first, second)
        events = [event["event_type"] for event in first["events"]]
        self.assertLess(events.index("mission_started"), events.index("return_to_base_invoked"))
        self.assertLess(events.index("return_to_base_invoked"), events.index("landed"))
        self.assertEqual(first["events"][events.index("return_to_base_invoked")]["action"], "ReturnToBase")

    def test_threshold_first_qualifying_step_speed_energy_and_landing(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        output = run_low_fidelity(facts, default_scenario())
        telemetry = output["telemetry"]
        trigger_index = next(i for i, row in enumerate(telemetry) if row["event"] == "return_to_base_invoked")
        self.assertLessEqual(telemetry[trigger_index]["battery_state_percent"], facts.battery_threshold_percent)
        self.assertTrue(all(row["battery_state_percent"] > facts.battery_threshold_percent for row in telemetry[:trigger_index] if row["state"] == "mission_flight"))
        self.assertTrue(all(max(row["ground_speed_mps"], row["commanded_speed_mps"]) <= facts.max_speed_mps for row in telemetry))
        energies = [row["battery_energy_wh"] for row in telemetry]
        self.assertEqual(energies, sorted(energies, reverse=True))
        self.assertEqual(telemetry[-1]["state"], "landed")
        self.assertEqual(telemetry[-1]["ground_speed_mps"], 0.0)
        self.assertEqual(telemetry[-1]["distance_to_home_m"], 0.0)
        self.assertTrue(output["mission_completed"])
        self.assertEqual(output["terminal_reason"], "landed")
        self.assertGreater(output["battery_reserve_at_landing_percent"], 0.0)
        self.assertFalse(output["battery_depleted_before_landing"])

    def test_stationary_waypoint_hold_zero_speed_battery_decreases_and_rtb_resumes(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        output = run_low_fidelity(facts, default_scenario())
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

    def test_zero_battery_terminates_without_powered_movement_or_landed_event(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        scenario = default_scenario()
        scenario["nominal_power_draw_w"]["value"] = 5000.0
        output = run_low_fidelity(facts, scenario)
        telemetry = output["telemetry"]
        self.assertFalse(output["mission_completed"])
        self.assertEqual(output["terminal_reason"], "battery_depleted_before_landing")
        self.assertTrue(output["battery_depleted_before_landing"])
        self.assertEqual(telemetry[-1]["event"], "battery_depleted")
        self.assertEqual(telemetry[-1]["battery_energy_wh"], 0.0)
        self.assertEqual(telemetry[-1]["commanded_speed_mps"], 0.0)
        self.assertEqual(telemetry[-1]["ground_speed_mps"], 0.0)
        self.assertIn("battery_depleted", [event["event_type"] for event in output["events"]])
        self.assertNotIn("landed", [event["event_type"] for event in output["events"]])


if __name__ == "__main__":
    unittest.main()
