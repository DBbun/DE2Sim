"""Scenario inputs for Phase 5A simulation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from de2sim.simulation.schema import ScenarioValue


class ScenarioError(Exception):
    """Controlled scenario validation failure."""


SCENARIO_FIELDS: dict[str, tuple[float | str, str, str]] = {
    "scenario_id": ("deterministic-demo-uAS-phase5a", "identifier", "Stable deterministic demonstration scenario identifier."),
    "home_x_m": (0.0, "m", "Home position x coordinate for the demonstration scenario."),
    "home_y_m": (0.0, "m", "Home position y coordinate for the demonstration scenario."),
    "mission_waypoint_x_m": (36000.0, "m", "Mission waypoint x coordinate chosen to exercise return-to-base behavior while leaving landing reserve."),
    "mission_waypoint_y_m": (0.0, "m", "Mission waypoint y coordinate chosen to keep path interpretation simple."),
    "arrival_radius_m": (75.0, "m", "Arrival radius used for waypoint and home confirmation."),
    "initial_battery_percent": (100.0, "percent", "Initial state of charge for the demonstration run."),
    "nominal_power_draw_w": (1200.0, "W", "Low-fidelity constant power draw assumption."),
    "high_fidelity_idle_power_w": (1140.0, "W", "Idle power used by the demonstrative point-mass model."),
    "high_fidelity_speed_power_coefficient": (0.3, "W/(m/s)^2", "Quadratic speed power coefficient for the demonstrative point-mass model."),
    "acceleration_limit_mps2": (2.0, "m/s^2", "Acceleration limit used to smooth the high-fidelity velocity response."),
    "wind_x_mps": (-2.0, "m/s", "Constant wind disturbance x component for the high-fidelity model."),
    "wind_y_mps": (0.5, "m/s", "Constant wind disturbance y component for the high-fidelity model."),
    "low_fidelity_time_step_s": (10.0, "s", "Fixed low-fidelity integration time step."),
    "high_fidelity_time_step_s": (2.0, "s", "Fixed high-fidelity integration time step."),
    "maximum_simulation_time_s": (20000.0, "s", "Deterministic safety limit for simulation termination."),
    "playback_seconds_per_simulation_second": (0.0025, "s/s", "Default viewer playback scale selected to show the complete demonstration mission in roughly 20 to 45 seconds."),
}


def default_scenario() -> dict[str, dict[str, Any]]:
    return {
        name: ScenarioValue(value, unit, "demonstration_assumption", explanation).to_dict()
        for name, (value, unit, explanation) in SCENARIO_FIELDS.items()
    }


def load_scenario(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    scenario = default_scenario()
    if path is None:
        validate_scenario(scenario)
        return scenario
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"malformed scenario JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except OSError as exc:
        raise ScenarioError(f"failed to read scenario JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScenarioError("scenario JSON root must be an object")
    for name, incoming in payload.items():
        if name not in SCENARIO_FIELDS:
            raise ScenarioError(f"unknown scenario field: {name}")
        base = scenario[name]
        if isinstance(incoming, dict):
            value = incoming.get("value", base["value"])
            unit = str(incoming.get("unit", base["unit"]))
            source = str(incoming.get("source_classification", "user_scenario"))
            explanation = str(incoming.get("explanation", "User-supplied scenario override."))
        else:
            value = incoming
            unit = str(base["unit"])
            source = "user_scenario"
            explanation = "User-supplied scenario override."
        scenario[name] = ScenarioValue(value, unit, source, explanation).to_dict()
    validate_scenario(scenario)
    return scenario


def scenario_values(scenario: dict[str, dict[str, Any]]) -> dict[str, float | str]:
    return {name: item["value"] for name, item in scenario.items()}


def validate_scenario(scenario: dict[str, dict[str, Any]]) -> None:
    missing = sorted(set(SCENARIO_FIELDS) - set(scenario))
    if missing:
        raise ScenarioError("scenario is missing fields: " + ", ".join(missing))
    for name, item in scenario.items():
        if not isinstance(item, dict):
            raise ScenarioError(f"scenario field must include value/unit/source/explanation: {name}")
        for key in ("value", "unit", "source_classification", "explanation"):
            if key not in item:
                raise ScenarioError(f"scenario field {name} is missing {key}")
        source = item["source_classification"]
        if source not in {"asot", "user_scenario", "demonstration_assumption"}:
            raise ScenarioError(f"scenario field {name} has invalid source classification: {source}")
        if name == "scenario_id":
            if not str(item["value"]).strip():
                raise ScenarioError("scenario_id must not be empty")
            continue
        number = _number(item["value"], name)
        item["value"] = number
    values = scenario_values(scenario)
    positive = (
        "arrival_radius_m",
        "nominal_power_draw_w",
        "high_fidelity_idle_power_w",
        "acceleration_limit_mps2",
        "low_fidelity_time_step_s",
        "high_fidelity_time_step_s",
        "maximum_simulation_time_s",
        "playback_seconds_per_simulation_second",
    )
    for name in positive:
        if float(values[name]) <= 0.0:
            raise ScenarioError(f"scenario field must be positive: {name}")
    if float(values["high_fidelity_speed_power_coefficient"]) < 0.0:
        raise ScenarioError("high_fidelity_speed_power_coefficient must be nonnegative")
    if not 0.0 <= float(values["initial_battery_percent"]) <= 100.0:
        raise ScenarioError("initial_battery_percent must be from 0 through 100")
    if float(values["high_fidelity_time_step_s"]) > float(values["low_fidelity_time_step_s"]):
        raise ScenarioError("high-fidelity time step must be no larger than low-fidelity time step")


def _number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ScenarioError(f"scenario field is nonnumeric: {name}") from exc
    if not math.isfinite(number):
        raise ScenarioError(f"scenario field is nonfinite: {name}")
    return number
