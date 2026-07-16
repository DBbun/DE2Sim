"""Extract Phase 5A simulation facts from an approved ASOT."""

from __future__ import annotations

import math
from typing import Any

from de2sim.asot.schema import ASOTDocument
from de2sim.asot.validators import validate_asot
from de2sim.simulation.schema import SimulationASOTFacts, STATES


class SimulationASOTError(Exception):
    """Controlled approved-ASOT extraction failure."""


def extract_simulation_facts(asot: ASOTDocument | dict[str, Any]) -> SimulationASOTFacts:
    payload = asot.to_dict() if isinstance(asot, ASOTDocument) else asot
    if not isinstance(payload, dict):
        raise SimulationASOTError("ASOT must be a JSON object")
    result = validate_asot(payload)
    if not result.ok:
        raise SimulationASOTError("malformed ASOT: " + "; ".join(result.errors))

    behaviors = _items(payload.get("behaviors"))
    approved = [b for b in behaviors if _text(b.get("name")) == "Low Battery Return-to-Base"]
    if not approved:
        raise SimulationASOTError("approved behavior named Low Battery Return-to-Base is absent")
    behavior = approved[0]
    if _text(behavior.get("approval_status")) != "approved" or _text(behavior.get("status")) != "approved":
        raise SimulationASOTError("Low Battery Return-to-Base behavior is not approved")

    source_rtb = _source_return_to_base_behavior(behaviors)
    params = {_text(item.get("name")).lower(): item for item in _items(payload.get("parameters"))}
    battery_threshold = _numeric_param(params, "battery_threshold")
    battery_capacity = _numeric_param(params, "battery_capacity")
    max_speed = _numeric_param(params, "max_speed")

    reqs = _items(payload.get("requirements"))
    low_req = _requirement(reqs, "low battery return")
    speed_req = _requirement(reqs, "maximum speed")
    all_ids = _known_ids(payload)
    referenced = set(_list_text(behavior.get("referenced_requirement_ids")))
    referenced.update(_list_text(behavior.get("referenced_parameter_ids")))
    referenced.update(_list_text(behavior.get("referenced_physical_model_ids")))
    referenced.update(_list_text(behavior.get("source_provenance_ids")))
    referenced.update(_list_text(behavior.get("source_references")))
    for ref in sorted(referenced):
        if ref and ref not in all_ids:
            raise SimulationASOTError(f"referenced ASOT entity does not exist: {ref}")

    required_ids = {
        _text(low_req.get("stable_id")),
        _text(speed_req.get("stable_id")),
        _text(params["battery_threshold"].get("stable_id")),
        _text(params["battery_capacity"].get("stable_id")),
        _text(params["max_speed"].get("stable_id")),
    }
    missing_links = sorted(item for item in required_ids if item not in referenced)
    if missing_links:
        raise SimulationASOTError("approved behavior is missing required ASOT links: " + ", ".join(missing_links))

    transition_sequence = _transition_sequence(behavior)
    provenance_ids = set(_list_text(behavior.get("source_provenance_ids")) + _list_text(behavior.get("source_references")))
    for item in (low_req, speed_req, params["battery_threshold"], params["battery_capacity"], params["max_speed"], source_rtb):
        provenance_ids.update(_list_text(item.get("source_references")))
        provenance_ids.update(_list_text(item.get("source_provenance_ids")))
    geometry = _simulation_geometry(payload)

    return SimulationASOTFacts(
        asot_id=_text(payload.get("asot_id")),
        title=_text((payload.get("metadata") or {}).get("title")) if isinstance(payload.get("metadata"), dict) else "",
        approved_behavior_id=_text(behavior.get("stable_id")),
        approved_behavior_name=_text(behavior.get("name")),
        source_return_to_base_behavior_id=_text(source_rtb.get("stable_id")),
        return_to_base_action="ReturnToBase",
        transition_sequence=tuple(transition_sequence),
        battery_threshold_percent=battery_threshold,
        battery_capacity_wh=battery_capacity,
        max_speed_mps=max_speed,
        low_battery_requirement_id=_text(low_req.get("stable_id")),
        max_speed_requirement_id=_text(speed_req.get("stable_id")),
        battery_threshold_parameter_id=_text(params["battery_threshold"].get("stable_id")),
        battery_capacity_parameter_id=_text(params["battery_capacity"].get("stable_id")),
        max_speed_parameter_id=_text(params["max_speed"].get("stable_id")),
        provenance_ids=tuple(sorted(provenance_ids)),
        geometry=geometry,
    )


def _source_return_to_base_behavior(behaviors: list[dict[str, Any]]) -> dict[str, Any]:
    for behavior in behaviors:
        actions = {_text(item) for item in _list_text(behavior.get("actions"))}
        if _text(behavior.get("name")) == "ReturnToBase" or "ReturnToBase" in actions:
            if _text(behavior.get("generated_by")) == "source" or _text(behavior.get("status")) == "source-derived":
                return behavior
    raise SimulationASOTError("source-derived ReturnToBase behavior is absent")


def _numeric_param(params: dict[str, dict[str, Any]], name: str) -> float:
    if name not in params:
        raise SimulationASOTError(f"{name} parameter is absent")
    value = params[name].get("value")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise SimulationASOTError(f"{name} parameter is nonnumeric") from exc
    if not math.isfinite(numeric):
        raise SimulationASOTError(f"{name} parameter is nonnumeric")
    return numeric


def _requirement(requirements: list[dict[str, Any]], normalized_name: str) -> dict[str, Any]:
    target = normalized_name.lower()
    for req in requirements:
        haystack = " ".join((_text(req.get("name")), _text(req.get("requirement_id")), _text(req.get("text")))).lower()
        if target in haystack:
            return req
    raise SimulationASOTError(f"{normalized_name} requirement is absent")


def _transition_sequence(behavior: dict[str, Any]) -> list[tuple[str, str, str, str, str]]:
    states = set(_list_text(behavior.get("states")))
    for state in STATES:
        if state not in states:
            raise SimulationASOTError(f"required state is absent from approved behavior: {state}")
    desired = [("preflight", "mission_flight"), ("mission_flight", "return_to_base"), ("return_to_base", "landed")]
    transitions = _items(behavior.get("transitions"))
    sequence = []
    for source, target in desired:
        match = next((item for item in transitions if _text(item.get("from")) == source and _text(item.get("to")) == target), None)
        if match is None:
            raise SimulationASOTError("required transition sequence is absent")
        sequence.append((source, target, _text(match.get("trigger")), _text(match.get("guard")), _text(match.get("action"))))
    if sequence[1][3] != "battery_state <= battery_threshold":
        raise SimulationASOTError("required low-battery guard is absent")
    if "ReturnToBase" not in sequence[1][4]:
        raise SimulationASOTError("required ReturnToBase action is absent")
    return sequence


def _known_ids(payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for section in ("components", "requirements", "interfaces", "parameters", "physical_models", "behaviors", "geometry"):
        ids.update(_text(item.get("stable_id")) for item in _items(payload.get(section)))
    ids.update(_text(item.get("provenance_id")) for item in _items(payload.get("provenance")))
    return {item for item in ids if item}


def _simulation_geometry(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = [item for item in _items(payload.get("geometry")) if _text(item.get("parser_status")) == "parsed"]
    if not parsed:
        return {}
    geometry = parsed[0]
    return {
        "geometry_id": _text(geometry.get("stable_id")),
        "geometry_source_format": _text(geometry.get("source_format") or geometry.get("geometry_format")),
        "geometry_dimensions": geometry.get("dimensions") if isinstance(geometry.get("dimensions"), dict) else {},
        "geometry_unit": _text(geometry.get("unit")),
        "geometry_authoritativeness": _text(geometry.get("authoritativeness")),
        "geometry_used_for_visualization": True,
        "geometry_used_for_flight_dynamics": False,
    }


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None or str(value).strip() == "":
        return []
    return [str(value).strip()]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()
