"""Schema helpers for deterministic Phase 5A simulation outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SIMULATION_SCHEMA_VERSION = "de2sim.simulation.v1"
FIDELITIES = ("low", "high")
STATES = ("preflight", "mission_flight", "return_to_base", "landed")
EVENT_ORDER = (
    "mission_started",
    "mission_waypoint_reached",
    "battery_threshold_reached",
    "return_to_base_invoked",
    "home_position_reached",
    "landed",
    "battery_depleted",
)
TELEMETRY_COLUMNS = (
    "time_s",
    "fidelity",
    "state",
    "x_m",
    "y_m",
    "ground_speed_mps",
    "commanded_speed_mps",
    "battery_energy_wh",
    "battery_state_percent",
    "distance_to_home_m",
    "distance_to_waypoint_m",
    "event",
    "requirement_low_battery_return_status",
    "requirement_max_speed_status",
)


@dataclass(frozen=True)
class ScenarioValue:
    value: float | str
    unit: str
    source_classification: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "source_classification": self.source_classification,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class SimulationASOTFacts:
    asot_id: str
    title: str
    approved_behavior_id: str
    approved_behavior_name: str
    source_return_to_base_behavior_id: str
    return_to_base_action: str
    transition_sequence: tuple[tuple[str, str, str, str, str], ...]
    battery_threshold_percent: float
    battery_capacity_wh: float
    max_speed_mps: float
    low_battery_requirement_id: str
    max_speed_requirement_id: str
    battery_threshold_parameter_id: str
    battery_capacity_parameter_id: str
    max_speed_parameter_id: str
    provenance_ids: tuple[str, ...] = field(default_factory=tuple)
    geometry: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asot_id": self.asot_id,
            "title": self.title,
            "approved_behavior_id": self.approved_behavior_id,
            "approved_behavior_name": self.approved_behavior_name,
            "source_return_to_base_behavior_id": self.source_return_to_base_behavior_id,
            "return_to_base_action": self.return_to_base_action,
            "transition_sequence": [
                {
                    "from": item[0],
                    "to": item[1],
                    "trigger": item[2],
                    "guard": item[3],
                    "action": item[4],
                }
                for item in self.transition_sequence
            ],
            "battery_threshold_percent": self.battery_threshold_percent,
            "battery_capacity_wh": self.battery_capacity_wh,
            "max_speed_mps": self.max_speed_mps,
            "requirement_ids": {
                "low_battery_return": self.low_battery_requirement_id,
                "maximum_speed": self.max_speed_requirement_id,
            },
            "parameter_ids": {
                "battery_threshold": self.battery_threshold_parameter_id,
                "battery_capacity": self.battery_capacity_parameter_id,
                "max_speed": self.max_speed_parameter_id,
            },
            "provenance_ids": list(self.provenance_ids),
            "geometry": self.geometry,
        }
