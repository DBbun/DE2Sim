"""Shared fixed simulation logic for Phase 5A."""

from __future__ import annotations

import math
from typing import Any

from de2sim.simulation.scenario import scenario_values
from de2sim.simulation.schema import SimulationASOTFacts


def simulate(facts: SimulationASOTFacts, scenario: dict[str, dict[str, Any]], fidelity: str) -> dict[str, Any]:
    values = scenario_values(scenario)
    dt = float(values["low_fidelity_time_step_s"] if fidelity == "low" else values["high_fidelity_time_step_s"])
    home = (float(values["home_x_m"]), float(values["home_y_m"]))
    waypoint = (float(values["mission_waypoint_x_m"]), float(values["mission_waypoint_y_m"]))
    arrival_radius = float(values["arrival_radius_m"])
    max_time = float(values["maximum_simulation_time_s"])
    max_speed = float(facts.max_speed_mps)
    capacity = float(facts.battery_capacity_wh)
    energy = capacity * float(values["initial_battery_percent"]) / 100.0
    x, y = home
    vx = vy = 0.0
    ground_speed_report = 0.0
    commanded_speed_report = 0.0
    time_s = 0.0
    state = "preflight"
    telemetry: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    waypoint_reached = False
    terminal_reason = ""
    mission_completed = False

    def battery_percent() -> float:
        return max(0.0, min(100.0, energy / capacity * 100.0))

    def record(event: str = "") -> None:
        telemetry.append(
            _row(
                time_s,
                fidelity,
                state,
                x,
                y,
                ground_speed_report,
                commanded_speed_report,
                energy,
                battery_percent(),
                _dist((x, y), home),
                _dist((x, y), waypoint),
                event,
            )
        )

    def add_event(event_type: str, before: str, after: str, trigger: str, guard: str, action: str) -> None:
        events.append(
            {
                "time_s": _round(time_s),
                "fidelity": fidelity,
                "state_before": before,
                "state_after": after,
                "event_type": event_type,
                "trigger": trigger,
                "guard": guard,
                "action": action,
                "related_behavior_ids": [facts.approved_behavior_id, facts.source_return_to_base_behavior_id]
                if event_type == "return_to_base_invoked"
                else [facts.approved_behavior_id],
                "related_requirement_ids": [facts.low_battery_requirement_id, facts.max_speed_requirement_id],
                "related_parameter_ids": [
                    facts.battery_threshold_parameter_id,
                    facts.battery_capacity_parameter_id,
                    facts.max_speed_parameter_id,
                ],
                "provenance_ids": list(facts.provenance_ids),
            }
        )

    record()
    add_event("mission_started", "preflight", "mission_flight", "mission_started", facts.transition_sequence[0][3], facts.transition_sequence[0][4])
    state = "mission_flight"
    record("mission_started")

    while not terminal_reason and time_s < max_time:
        previous_state = state
        if energy <= 0.0:
            vx = vy = 0.0
            ground_speed_report = 0.0
            commanded_speed_report = 0.0
            add_event("battery_depleted", state, state, "battery_energy_wh <= 0", "usable battery energy depleted", "terminate simulation without inventing a new ASOT state")
            terminal_reason = "battery_depleted_before_landing"
            record("battery_depleted")
            break
        holding_at_waypoint = state == "mission_flight" and waypoint_reached
        target = waypoint if state == "mission_flight" and not waypoint_reached else home if state == "return_to_base" else (x, y)
        distance_before = _dist((x, y), target)
        cmd_vx, cmd_vy = (0.0, 0.0) if holding_at_waypoint else _command_velocity((x, y), target, max_speed, arrival_radius)
        commanded_speed_report = 0.0 if energy <= 0.0 else min(max_speed, math.hypot(cmd_vx, cmd_vy))
        if fidelity == "low":
            vx, vy = cmd_vx, cmd_vy
            move_dt = min(dt, distance_before / max_speed) if max_speed > 0 and distance_before > arrival_radius and math.hypot(vx, vy) > 0 else dt
            x += vx * move_dt
            y += vy * move_dt
            ground_speed_report = min(max_speed, math.hypot(vx, vy))
            power_w = float(values["nominal_power_draw_w"]) if state != "landed" else 0.0
        else:
            if holding_at_waypoint:
                vx = vy = 0.0
                air_speed = 0.0
                x, y = waypoint
                ground_speed_report = 0.0
            else:
                ax, ay = cmd_vx - vx, cmd_vy - vy
                change = math.hypot(ax, ay)
                limit = float(values["acceleration_limit_mps2"]) * dt
                if change > limit > 0.0:
                    ax *= limit / change
                    ay *= limit / change
                vx += ax
                vy += ay
                air_speed = math.hypot(vx, vy)
                if air_speed > max_speed:
                    vx *= max_speed / air_speed
                    vy *= max_speed / air_speed
                    air_speed = max_speed
                gx = vx + float(values["wind_x_mps"])
                gy = vy + float(values["wind_y_mps"])
                ground_speed = math.hypot(gx, gy)
                if ground_speed > max_speed:
                    gx *= max_speed / ground_speed
                    gy *= max_speed / ground_speed
                    ground_speed = max_speed
                x += gx * dt
                y += gy * dt
                ground_speed_report = ground_speed
            power_w = float(values["high_fidelity_idle_power_w"]) + float(values["high_fidelity_speed_power_coefficient"]) * air_speed * air_speed
        if state != "landed":
            energy = max(0.0, energy - power_w * dt / 3600.0)
        event_text = ""
        if state == "mission_flight" and not waypoint_reached and _dist((x, y), waypoint) <= arrival_radius:
            waypoint_reached = True
            x, y = waypoint
            vx = vy = 0.0
            ground_speed_report = 0.0
            commanded_speed_report = 0.0
            event_text = "mission_waypoint_reached"
            add_event(event_text, state, state, event_text, "distance_to_waypoint <= arrival_radius", "continue mission flight or loiter")
        if state == "mission_flight" and battery_percent() <= facts.battery_threshold_percent:
            add_event("battery_threshold_reached", state, state, "battery_threshold_reached", "battery_state <= battery_threshold", "evaluate low-battery transition")
            add_event("return_to_base_invoked", state, "return_to_base", "battery_threshold_reached", "battery_state <= battery_threshold", "ReturnToBase")
            state = "return_to_base"
            commanded_speed_report = max_speed if energy > 0.0 else 0.0
            event_text = "return_to_base_invoked"
        if state == "return_to_base" and _dist((x, y), home) <= arrival_radius:
            before = state
            add_event("home_position_reached", before, before, "home_position_reached", "distance_to_home <= arrival_radius", "confirm home arrival")
            state = "landed"
            vx = vy = 0.0
            ground_speed_report = 0.0
            commanded_speed_report = 0.0
            add_event("landed", before, state, "home_position_reached", facts.transition_sequence[2][3], facts.transition_sequence[2][4])
            event_text = "landed"
            terminal_reason = "landed"
            mission_completed = True
        elif energy <= 0.0:
            vx = vy = 0.0
            ground_speed_report = 0.0
            commanded_speed_report = 0.0
            add_event("battery_depleted", state, state, "battery_energy_wh <= 0", "usable battery energy depleted", "terminate simulation without inventing a new ASOT state")
            event_text = "battery_depleted"
            terminal_reason = "battery_depleted_before_landing"
        time_s = _round(time_s + dt)
        record(event_text)
        if previous_state == state == "landed":
            break
    if not terminal_reason:
        terminal_reason = "maximum_simulation_time_exceeded"
    final_row = telemetry[-1]
    return {
        "fidelity": fidelity,
        "telemetry": telemetry,
        "events": events,
        "mission_completed": mission_completed,
        "terminal_reason": terminal_reason,
        "battery_reserve_at_landing_percent": final_row["battery_state_percent"] if mission_completed else None,
        "battery_depleted_before_landing": terminal_reason == "battery_depleted_before_landing",
    }


def _command_velocity(pos: tuple[float, float], target: tuple[float, float], max_speed: float, radius: float) -> tuple[float, float]:
    distance = _dist(pos, target)
    if distance <= radius or max_speed <= 0.0:
        return 0.0, 0.0
    return ((target[0] - pos[0]) / distance * max_speed, (target[1] - pos[1]) / distance * max_speed)


def _row(time_s: float, fidelity: str, state: str, x: float, y: float, ground_speed: float, commanded_speed: float, energy: float, battery: float, home: float, waypoint: float, event: str) -> dict[str, Any]:
    return {
        "time_s": _round(time_s),
        "fidelity": fidelity,
        "state": state,
        "x_m": _round(x),
        "y_m": _round(y),
        "ground_speed_mps": _round(ground_speed),
        "commanded_speed_mps": _round(commanded_speed),
        "battery_energy_wh": _round(energy),
        "battery_state_percent": _round(battery),
        "distance_to_home_m": _round(home),
        "distance_to_waypoint_m": _round(waypoint),
        "event": event,
        "requirement_low_battery_return_status": "not_evaluated",
        "requirement_max_speed_status": "not_evaluated",
    }


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _round(value: float) -> float:
    return round(float(value), 6)
