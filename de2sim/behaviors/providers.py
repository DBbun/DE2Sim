"""Behavior proposal providers for DE2Sim Phase 4A."""

from __future__ import annotations

import importlib
import json
import os
from typing import Any, Protocol


class BehaviorProviderError(Exception):
    """Controlled behavior provider failure."""


class BehaviorProvider(Protocol):
    provider_name: str
    model: str
    generated_by: str

    def propose(self, prompt: dict[str, Any]) -> list[dict[str, Any]]:
        """Return raw proposal dictionaries without executing generated content."""


class OfflineTemplateProvider:
    provider_name = "offline"
    model = "deterministic-template-v1"
    generated_by = "offline_template"

    def propose(self, prompt: dict[str, Any]) -> list[dict[str, Any]]:
        self.model = "deterministic-template-v1"
        components = prompt.get("components", []) if isinstance(prompt.get("components"), list) else []
        requirements = prompt.get("requirements", []) if isinstance(prompt.get("requirements"), list) else []
        parameters = prompt.get("parameters", []) if isinstance(prompt.get("parameters"), list) else []
        models = prompt.get("physical_models", []) if isinstance(prompt.get("physical_models"), list) else []
        existing = prompt.get("existing_source_derived_behaviors", []) if isinstance(prompt.get("existing_source_derived_behaviors"), list) else []
        provenance = prompt.get("provenance_references", []) if isinstance(prompt.get("provenance_references"), list) else []
        uas_evidence = _uas_operational_evidence(requirements, parameters, existing)
        if uas_evidence["complete"]:
            self.model = "deterministic-uas-template-v1"
            return [_uas_operational_proposal(uas_evidence, provenance)]

        missing_warning = _missing_uas_warning(uas_evidence)
        proposals = []
        seen_component_names: set[str] = set()
        for component in components:
            component_id = str(component.get("stable_id", ""))
            if not component_id:
                continue
            normalized_name = _normalized_name(str(component.get("name") or component_id))
            if normalized_name in seen_component_names:
                continue
            seen_component_names.add(normalized_name)
            reqs = _matching_requirements(requirements, provenance, component_id)
            params = _matching_parameters(parameters, component_id)
            ph_models = _matching_models(models, component_id, params)
            if not (reqs or params or ph_models or existing):
                continue
            name = f"{component.get('name') or component_id} review behavior"
            states = ["uninitialized", "ready", "active", "complete"]
            triggers = ["source evidence available", "reviewed condition satisfied"]
            guards = ["requires human approval before use"]
            actions = ["record proposed behavior for review"]
            if params:
                param_names = ", ".join(str(item.get("name", item.get("stable_id"))) for item in params[:3])
                guards.append(f"uses only documented parameters: {param_names}")
            transitions = [
                {"from": "uninitialized", "to": "ready", "trigger": "source evidence available", "guard": "ASOT references are valid", "action": "prepare review state"},
                {"from": "ready", "to": "active", "trigger": "reviewed condition satisfied", "guard": "human reviewer approves proposal", "action": "mark behavior approved"},
                {"from": "active", "to": "complete", "trigger": "review complete", "guard": "no unsupported thresholds added", "action": "retain approval record"},
            ]
            proposals.append(
                {
                    "name": name,
                    "description": "Deterministic offline candidate assembled from explicit ASOT evidence for human review.",
                    "behavior_type": "state_machine",
                    "owning_component_id": component_id,
                    "states": states,
                    "transitions": transitions,
                    "triggers": triggers,
                    "guards": guards,
                    "actions": actions,
                    "referenced_requirement_ids": [str(item.get("stable_id", "")) for item in reqs if item.get("stable_id")],
                    "referenced_parameter_ids": [str(item.get("stable_id", "")) for item in params if item.get("stable_id")],
                    "referenced_physical_model_ids": [str(item.get("stable_id", "")) for item in ph_models if item.get("stable_id")],
                    "referenced_behavior_ids": [],
                    "source_provenance_ids": _source_ids(reqs + params + ph_models + existing, provenance),
                    "confidence": 0.55,
                    "assumptions": [
                        "Candidate is a deterministic template and is not generative-AI output.",
                        "Reviewer will confirm whether the state names match the intended system behavior.",
                    ],
                    "risks": [
                        "Template behavior may be too generic for direct engineering use.",
                        "No simulation semantics are produced in Phase 4A.",
                    ],
                    "validation_warnings": [missing_warning] if missing_warning else [],
                }
            )
        return proposals


class OpenAIProvider:
    provider_name = "openai"
    model = "configured-openai-model"
    generated_by = "ai_provider"

    def __init__(self, model: str = "gpt-5", client: Any | None = None) -> None:
        self.model = model
        self._client = client

    def propose(self, prompt: dict[str, Any]) -> list[dict[str, Any]]:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise BehaviorProviderError("OPENAI_API_KEY is required for the OpenAI behavior provider")
        if self._client is not None:
            return _extract_json_proposals(self._client(prompt))
        try:
            importlib.import_module("openai")
        except ImportError as exc:
            raise BehaviorProviderError("OpenAI provider package is unavailable") from exc
        raise BehaviorProviderError("OpenAI network calls are not performed by this Phase 4A adapter without an injected client")


class AnthropicProvider:
    provider_name = "anthropic"
    model = "configured-anthropic-model"
    generated_by = "ai_provider"

    def __init__(self, model: str = "claude-sonnet-4", client: Any | None = None) -> None:
        self.model = model
        self._client = client

    def propose(self, prompt: dict[str, Any]) -> list[dict[str, Any]]:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise BehaviorProviderError("ANTHROPIC_API_KEY is required for the Anthropic behavior provider")
        if self._client is not None:
            return _extract_json_proposals(self._client(prompt))
        try:
            importlib.import_module("anthropic")
        except ImportError as exc:
            raise BehaviorProviderError("Anthropic provider package is unavailable") from exc
        raise BehaviorProviderError("Anthropic network calls are not performed by this Phase 4A adapter without an injected client")


def get_provider(name: str) -> BehaviorProvider:
    normalized = str(name or "offline").strip().lower()
    if normalized == "offline":
        return OfflineTemplateProvider()
    if normalized == "openai":
        return OpenAIProvider()
    if normalized == "anthropic":
        return AnthropicProvider()
    raise BehaviorProviderError(f"unsupported behavior AI provider: {name}")


def _extract_json_proposals(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, dict):
        payload = response
    else:
        payload = json.loads(str(response))
    proposals = payload.get("proposals") if isinstance(payload, dict) else None
    if not isinstance(proposals, list) or not all(isinstance(item, dict) for item in proposals):
        raise BehaviorProviderError("provider response must contain a proposals array")
    return proposals


def _matching_parameters(parameters: list[dict[str, Any]], component_id: str) -> list[dict[str, Any]]:
    owned = [item for item in parameters if item.get("owning_component_id") == component_id]
    return owned or parameters[:3]


def _matching_models(models: list[dict[str, Any]], component_id: str, params: list[dict[str, Any]]) -> list[dict[str, Any]]:
    param_ids = {item.get("stable_id") for item in params}
    return [
        item
        for item in models
        if component_id in item.get("owning_component_ids", []) or any(pid in item.get("parameter_ids", []) for pid in param_ids)
    ][:3]


def _matching_requirements(requirements: list[dict[str, Any]], provenance: list[dict[str, Any]], component_id: str) -> list[dict[str, Any]]:
    provenance_ids = {
        str(record.get("provenance_id", ""))
        for record in provenance
        if component_id in (record.get("target_entity_ids") or [])
    }
    matched = [item for item in requirements if set(item.get("source_references") or []) & provenance_ids]
    return matched or requirements[:3]


def _source_ids(records: list[dict[str, Any]], provenance: list[dict[str, Any]]) -> list[str]:
    ids = {str(pid) for record in records for pid in (record.get("source_references") or []) if str(pid)}
    if not ids:
        ids = {str(item.get("provenance_id", "")) for item in provenance[:3] if item.get("provenance_id")}
    return sorted(ids)


def _uas_operational_evidence(
    requirements: list[dict[str, Any]],
    parameters: list[dict[str, Any]],
    behaviors: list[dict[str, Any]],
) -> dict[str, Any]:
    low_battery_requirement = next((item for item in requirements if _is_low_battery_rtb_requirement(item)), None)
    battery_threshold = next((item for item in parameters if _is_battery_threshold_parameter(item)), None)
    return_to_base = next((item for item in behaviors if _is_return_to_base_behavior(item)), None)
    max_speed_requirement = next((item for item in requirements if _is_max_speed_requirement(item)), None)
    max_speed_parameter = next((item for item in parameters if _is_max_speed_parameter(item)), None)
    battery_capacity = next((item for item in parameters if _is_battery_capacity_parameter(item)), None)
    return {
        "low_battery_requirement": low_battery_requirement,
        "battery_threshold": battery_threshold,
        "return_to_base": return_to_base,
        "max_speed_requirement": max_speed_requirement,
        "max_speed_parameter": max_speed_parameter,
        "battery_capacity": battery_capacity,
        "complete": bool(low_battery_requirement and battery_threshold and return_to_base),
    }


def _uas_operational_proposal(evidence: dict[str, Any], provenance: list[dict[str, Any]]) -> dict[str, Any]:
    requirement = evidence["low_battery_requirement"]
    threshold = evidence["battery_threshold"]
    behavior = evidence["return_to_base"]
    threshold_name = _symbolic_name(threshold)
    max_speed_requirement = evidence.get("max_speed_requirement")
    max_speed_parameter = evidence.get("max_speed_parameter")
    battery_capacity = evidence.get("battery_capacity")
    actions = [
        "begin mission while respecting documented operating limits",
        "invoke the explicit source-derived ReturnToBase behavior",
        "land and terminate the mission",
    ]
    referenced_requirements = [str(requirement.get("stable_id", ""))]
    referenced_parameters = [str(threshold.get("stable_id", ""))]
    provenance_records = [requirement, threshold, behavior]
    assumptions = [
        "This proposal is a deterministic offline template and not generative-AI output.",
        "Owning component is unresolved because explicit source evidence does not provide unambiguous ownership.",
    ]
    if max_speed_requirement and max_speed_parameter:
        max_speed_name = _symbolic_name(max_speed_parameter)
        referenced_requirements.append(str(max_speed_requirement.get("stable_id", "")))
        referenced_parameters.append(str(max_speed_parameter.get("stable_id", "")))
        provenance_records.extend([max_speed_requirement, max_speed_parameter])
        actions[0] = f"begin mission while respecting documented operating limits, including {max_speed_name}"
    if battery_capacity:
        capacity_name = _symbolic_name(battery_capacity)
        referenced_parameters.append(str(battery_capacity.get("stable_id", "")))
        provenance_records.append(battery_capacity)
        assumptions.append(f"{capacity_name} is available as a model input only and is not used as a trigger.")
    transitions = [
        {
            "from": "preflight",
            "to": "mission_flight",
            "trigger": "mission_started",
            "guard": "required mission evidence is available",
            "action": actions[0],
        },
        {
            "from": "mission_flight",
            "to": "return_to_base",
            "trigger": "battery_threshold_reached",
            "guard": f"battery_state <= {threshold_name}",
            "action": "invoke the explicit source-derived ReturnToBase behavior",
        },
        {
            "from": "return_to_base",
            "to": "landed",
            "trigger": "home_position_reached",
            "guard": "return-to-base behavior is active and home arrival is confirmed",
            "action": "land and terminate the mission",
        },
    ]
    return {
        "name": "Low Battery Return-to-Base",
        "description": "Deterministic operational UAS mission behavior assembled only from explicit low-battery return-to-base ASOT evidence.",
        "behavior_type": "state_machine",
        "owning_component_id": "",
        "states": ["preflight", "mission_flight", "return_to_base", "landed"],
        "transitions": transitions,
        "triggers": ["mission_started", "battery_threshold_reached", "home_position_reached"],
        "guards": [
            "required mission evidence is available",
            f"battery_state <= {threshold_name}",
            "return-to-base behavior is active and home arrival is confirmed",
        ],
        "actions": actions,
        "referenced_requirement_ids": [item for item in referenced_requirements if item],
        "referenced_parameter_ids": [item for item in referenced_parameters if item],
        "referenced_physical_model_ids": [],
        "referenced_behavior_ids": [str(behavior.get("stable_id", ""))] if behavior.get("stable_id") else [],
        "source_provenance_ids": _source_ids(provenance_records, provenance),
        "confidence": 0.68,
        "assumptions": assumptions,
        "risks": [
            "Simulation semantics have not yet been generated.",
            "Mission start and home arrival events require later review before simulation execution.",
        ],
    }


def _missing_uas_warning(evidence: dict[str, Any]) -> str:
    missing = []
    if not evidence.get("low_battery_requirement"):
        missing.append("low-battery return-to-base requirement")
    if not evidence.get("battery_threshold"):
        missing.append("battery-threshold parameter")
    if not evidence.get("return_to_base"):
        missing.append("source-derived ReturnToBase behavior")
    if not missing:
        return ""
    return "UAS operational behavior template not generated because required evidence is absent: " + ", ".join(missing)


def _is_low_battery_rtb_requirement(item: dict[str, Any]) -> bool:
    text = _evidence_text(item, ("requirement_id", "name", "text", "description"))
    return _has_low_battery(text) and _has_return_to_base(text)


def _is_battery_threshold_parameter(item: dict[str, Any]) -> bool:
    text = _evidence_text(item, ("stable_id", "name", "description", "symbolic_expression"))
    return "battery" in text and "threshold" in text


def _is_return_to_base_behavior(item: dict[str, Any]) -> bool:
    text = _evidence_text(item, ("stable_id", "name", "description", "behavior_type"))
    nested = " ".join(str(value).lower() for key in ("states", "transitions", "triggers", "guards", "actions") for value in item.get(key, []) if not isinstance(value, dict))
    if item.get("transitions"):
        nested += " " + json.dumps(item.get("transitions"), sort_keys=True).lower()
    return _has_return_to_base(text + " " + nested)


def _is_max_speed_requirement(item: dict[str, Any]) -> bool:
    text = _evidence_text(item, ("requirement_id", "name", "text", "description"))
    return "maximum" in text and "speed" in text


def _is_max_speed_parameter(item: dict[str, Any]) -> bool:
    text = _evidence_text(item, ("stable_id", "name", "description", "symbolic_expression"))
    return ("max" in text or "maximum" in text) and "speed" in text


def _is_battery_capacity_parameter(item: dict[str, Any]) -> bool:
    text = _evidence_text(item, ("stable_id", "name", "description", "symbolic_expression"))
    return "battery" in text and "capacity" in text


def _has_low_battery(text: str) -> bool:
    return "battery" in text and ("low" in text or "depleted" in text or "minimum" in text)


def _has_return_to_base(text: str) -> bool:
    compact = text.replace("_", "").replace("-", "").replace(" ", "")
    return ("return" in text and "base" in text) or "returntobase" in compact or "rtb" in text.split()


def _evidence_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    return " ".join(str(item.get(key, "")) for key in keys).lower()


def _symbolic_name(parameter: dict[str, Any]) -> str:
    return str(parameter.get("name") or parameter.get("symbolic_expression") or parameter.get("stable_id") or "parameter").strip()


def _normalized_name(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())
