"""Validation, requirement evaluation, and fidelity comparison."""

from __future__ import annotations

import math
from typing import Any

from de2sim.simulation.schema import EVENT_ORDER, SimulationASOTFacts


class SimulationValidationError(Exception):
    """Controlled simulation validation failure."""


def validate_engineering_limits(facts: SimulationASOTFacts) -> None:
    if not 0.0 <= facts.battery_threshold_percent <= 100.0:
        raise SimulationValidationError("battery threshold must be from 0 through 100")
    if facts.battery_capacity_wh <= 0.0:
        raise SimulationValidationError("battery capacity must be positive")
    if facts.max_speed_mps <= 0.0:
        raise SimulationValidationError("max speed must be positive")
    for value in (facts.battery_threshold_percent, facts.battery_capacity_wh, facts.max_speed_mps):
        if not math.isfinite(value):
            raise SimulationValidationError("engineering limits must be finite")


def evaluate_requirements(facts: SimulationASOTFacts, outputs: list[dict[str, Any]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for output in outputs:
        telemetry = output["telemetry"]
        events = output["events"]
        fidelity = output["fidelity"]
        threshold_events = [e for e in events if e["event_type"] == "battery_threshold_reached"]
        rtb_events = [e for e in events if e["event_type"] == "return_to_base_invoked"]
        low_pass = bool(threshold_events and rtb_events and rtb_events[0]["time_s"] == threshold_events[0]["time_s"] and rtb_events[0]["action"] == "ReturnToBase")
        max_observed = max(max(row["ground_speed_mps"], row["commanded_speed_mps"]) for row in telemetry)
        speed_pass = max_observed <= facts.max_speed_mps + 1e-6
        results[fidelity] = {
            "low_battery_return": {
                "status": "pass" if low_pass else "fail",
                "requirement_id": facts.low_battery_requirement_id,
                "evidence": "return_to_base entered when battery_state <= battery_threshold and ReturnToBase action was invoked",
                "telemetry_indices": _summarize_indices(_indices_for_events(telemetry, {"return_to_base_invoked"})),
            },
            "maximum_speed": {
                "status": "pass" if speed_pass else "fail",
                "requirement_id": facts.max_speed_requirement_id,
                "interpretation": "Both commanded speed and reported ground speed are checked against ASOT max_speed for this demonstrative point model.",
                "max_observed_speed_mps": round(max_observed, 6),
                "telemetry_indices": _summarize_indices(
                    [index for index, row in enumerate(telemetry) if max(row["ground_speed_mps"], row["commanded_speed_mps"]) == max_observed]
                ),
            },
        }
        for row in telemetry:
            row["requirement_low_battery_return_status"] = results[fidelity]["low_battery_return"]["status"]
            row["requirement_max_speed_status"] = results[fidelity]["maximum_speed"]["status"]
    return results


def validate_simulation_output(output: dict[str, Any], maximum_simulation_time_s: float) -> None:
    telemetry = output["telemetry"]
    events = output["events"]
    if not telemetry:
        raise SimulationValidationError("telemetry is empty")
    previous_time = -1.0
    previous_energy = float("inf")
    landed_seen = False
    landed_position = None
    depleted_seen = False
    for row in telemetry:
        if row["time_s"] < previous_time:
            raise SimulationValidationError("telemetry time is not monotonically nondecreasing")
        if row["battery_energy_wh"] > previous_energy + 1e-6:
            raise SimulationValidationError("battery energy increased unexpectedly")
        if landed_seen and (row["x_m"], row["y_m"]) != landed_position:
            raise SimulationValidationError("landed state did not remain stationary")
        if landed_seen and row is not telemetry[-1]:
            raise SimulationValidationError("telemetry continues after terminal landed row")
        if depleted_seen and row is not telemetry[-1]:
            raise SimulationValidationError("telemetry continues after terminal battery depletion row")
        if depleted_seen and (row["commanded_speed_mps"] > 0.0 or row["ground_speed_mps"] > 0.0):
            raise SimulationValidationError("positive speed after zero battery")
        if row["battery_energy_wh"] <= 0.0:
            depleted_seen = True
            if row["commanded_speed_mps"] > 0.0 or row["ground_speed_mps"] > 0.0:
                raise SimulationValidationError("positive speed after zero battery")
        if row["state"] == "landed":
            landed_seen = True
            landed_position = (row["x_m"], row["y_m"])
        previous_time = row["time_s"]
        previous_energy = row["battery_energy_wh"]
    terminal_reason = output.get("terminal_reason", "")
    if terminal_reason == "landed":
        if telemetry[-1]["state"] != "landed":
            raise SimulationValidationError("landed terminal reason without landed final row")
        if telemetry[-1]["battery_energy_wh"] <= 0.0:
            raise SimulationValidationError("successful simulation landed without positive battery energy")
    elif terminal_reason == "battery_depleted_before_landing":
        if telemetry[-1]["battery_energy_wh"] > 0.0:
            raise SimulationValidationError("battery-depleted terminal reason without zero battery")
        if any(event["event_type"] == "landed" for event in events):
            raise SimulationValidationError("landed event after battery-depletion termination")
    else:
        raise SimulationValidationError(f"unsupported terminal reason: {terminal_reason}")
    if telemetry[-1]["time_s"] > maximum_simulation_time_s:
        raise SimulationValidationError("simulation exceeded maximum_simulation_time_s")
    seen_events = [event["event_type"] for event in events]
    positions = [seen_events.index(item) for item in EVENT_ORDER if item in seen_events]
    if positions != sorted(positions):
        raise SimulationValidationError("required events are out of order")
    required_terminal = ("home_position_reached", "landed") if terminal_reason == "landed" else ("battery_depleted",)
    missing = [
        item
        for item in ("mission_started", "battery_threshold_reached", "return_to_base_invoked", *required_terminal)
        if item not in seen_events
    ]
    if missing:
        raise SimulationValidationError("required events are absent: " + ", ".join(missing))


def compare_fidelities(low: dict[str, Any], high: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    low_metrics = _metrics(low["telemetry"])
    high_metrics = _metrics(high["telemetry"])
    feasibility = _feasibility({"low": low, "high": high})
    return {
        "low": low_metrics,
        "high": high_metrics,
        "scenario_feasibility": feasibility,
        "requirement_results": requirements,
        "differences": {
            key: round(high_metrics[key] - low_metrics[key], 6)
            for key in low_metrics
            if isinstance(low_metrics[key], (int, float)) and isinstance(high_metrics[key], (int, float))
        },
        "explanation": (
            "The low-fidelity model changes heading instantaneously, ignores wind and acceleration, and uses constant power. "
            "The high-fidelity demonstrative point-mass model integrates velocity, acceleration limits, wind disturbance, idle power, and speed-dependent power. "
            "These differences can change trigger time, landing time, distance traveled, and energy use; neither fidelity is asserted physically correct without validation data."
        ),
    }


def _metrics(telemetry: list[dict[str, Any]]) -> dict[str, Any]:
    trigger = _event_time(telemetry, "return_to_base_invoked")
    landing = _event_time(telemetry, "landed")
    distance = 0.0
    for previous, current in zip(telemetry, telemetry[1:]):
        distance += math.hypot(current["x_m"] - previous["x_m"], current["y_m"] - previous["y_m"])
    return {
        "total_simulated_mission_time_s": telemetry[-1]["time_s"],
        "return_to_base_trigger_time_s": trigger,
        "landing_time_s": landing,
        "distance_traveled_m": round(distance, 6),
        "minimum_battery_percent": min(row["battery_state_percent"] for row in telemetry),
        "maximum_speed_mps": max(max(row["ground_speed_mps"], row["commanded_speed_mps"]) for row in telemetry),
        "energy_consumed_wh": round(telemetry[0]["battery_energy_wh"] - telemetry[-1]["battery_energy_wh"], 6),
        "final_distance_from_home_m": telemetry[-1]["distance_to_home_m"],
        "number_of_telemetry_samples": len(telemetry),
    }


def _event_time(telemetry: list[dict[str, Any]], event: str) -> float:
    for row in telemetry:
        if row["event"] == event:
            return row["time_s"]
    return -1.0


def _indices_for_events(telemetry: list[dict[str, Any]], events: set[str]) -> list[int]:
    return [index for index, row in enumerate(telemetry) if row["event"] in events]


def _summarize_indices(indices: list[int]) -> dict[str, int | None]:
    if not indices:
        return {"count": 0, "first_index": None, "last_index": None, "event_index": None}
    return {"count": len(indices), "first_index": indices[0], "last_index": indices[-1], "event_index": indices[0]}


def _feasibility(outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    per_fidelity = {}
    for fidelity, output in outputs.items():
        reserve = output.get("battery_reserve_at_landing_percent")
        passed = bool(output.get("mission_completed")) and reserve is not None and reserve > 0.0
        per_fidelity[fidelity] = {
            "mission_completed": bool(output.get("mission_completed")),
            "terminal_reason": output.get("terminal_reason"),
            "battery_reserve_at_landing_percent": reserve,
            "battery_depleted_before_landing": bool(output.get("battery_depleted_before_landing")),
            "scenario_feasibility_status": "pass" if passed else "fail",
            "scenario_feasibility_explanation": (
                "Mission landed with positive battery reserve under the explicit demonstration scenario."
                if passed
                else "Mission did not land with positive battery reserve under the explicit demonstration scenario."
            ),
        }
    overall_pass = all(item["scenario_feasibility_status"] == "pass" for item in per_fidelity.values())
    return {
        "scenario_feasibility_status": "pass" if overall_pass else "fail",
        "scenario_feasibility_explanation": (
            "Both fidelities completed the mission and landed with positive battery reserve."
            if overall_pass
            else "At least one fidelity did not complete the mission with positive battery reserve."
        ),
        "per_fidelity": per_fidelity,
    }
