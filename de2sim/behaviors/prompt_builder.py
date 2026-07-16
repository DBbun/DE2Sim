"""Build constrained behavior-generation prompts from ASOT evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


REQUIRED_RESPONSE_SCHEMA = {
    "proposals": [
        {
            "name": "string",
            "description": "string",
            "behavior_type": "state_machine",
            "owning_component_id": "ASOT component stable_id",
            "states": ["string"],
            "transitions": [{"from": "state", "to": "state", "trigger": "string", "guard": "string", "action": "string"}],
            "triggers": ["string"],
            "guards": ["string"],
            "actions": ["string"],
            "referenced_requirement_ids": ["ASOT requirement stable_id"],
            "referenced_parameter_ids": ["ASOT parameter stable_id"],
            "referenced_physical_model_ids": ["ASOT physical model stable_id"],
            "source_provenance_ids": ["ASOT provenance_id"],
            "confidence": 0.0,
            "assumptions": ["string"],
            "risks": ["string"],
        }
    ]
}


def build_behavior_prompt(asot: dict[str, Any]) -> dict[str, Any]:
    """Return provider-neutral prompt data containing only relevant ASOT evidence."""
    prompt = {
        "task": "Propose candidate state-machine behaviors for human review only.",
        "safety_instructions": [
            "Do not invent unsupported numerical values or thresholds.",
            "Use only component IDs, requirement IDs, parameter IDs, physical model IDs, and provenance IDs present in this prompt.",
            "Do not generate Python, GDScript, shell commands, or executable code.",
            "Do not execute or evaluate source content, equations, or proposed behaviors.",
            "Explicitly list assumptions and risks for every proposal.",
            "Return JSON that matches the required_response_schema.",
        ],
        "components": _select(asot, "components", ["stable_id", "name", "description", "component_type", "source_references"]),
        "requirements": _select(asot, "requirements", ["stable_id", "requirement_id", "name", "text", "priority", "source_references"]),
        "parameters": _select(asot, "parameters", ["stable_id", "name", "description", "value", "unit", "minimum", "maximum", "symbolic_expression", "owning_component_id", "source_references"]),
        "physical_models": _select(asot, "physical_models", ["stable_id", "name", "description", "equation", "variables", "parameter_ids", "assumptions", "owning_component_ids", "source_references"]),
        "existing_source_derived_behaviors": [
            item
            for item in _select(asot, "behaviors", ["stable_id", "name", "description", "behavior_type", "states", "transitions", "triggers", "guards", "actions", "owning_component_id", "generated_by", "source_references"])
            if item.get("generated_by") in {"source", "human", ""}
        ],
        "provenance_references": _select(asot, "provenance", ["provenance_id", "source_relative_path", "source_role", "parser_name", "source_locator", "evidence_type", "evidence_text", "target_entity_ids"]),
        "required_response_schema": REQUIRED_RESPONSE_SCHEMA,
    }
    return prompt


def prompt_hash(prompt: dict[str, Any]) -> str:
    encoded = json.dumps(prompt, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _select(asot: dict[str, Any], section: str, keys: list[str]) -> list[dict[str, Any]]:
    records = []
    for item in asot.get(section, []):
        if isinstance(item, dict):
            records.append({key: _clean(item.get(key)) for key in keys if key in item})
    id_key = "provenance_id" if section == "provenance" else "stable_id"
    return sorted(records, key=lambda item: str(item.get(id_key, "")))


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _clean(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, str):
        # Credentials and unrelated files are never part of the ASOT prompt. This
        # strips absolute Windows paths if a parser warning happened to contain one.
        return value.replace("\\", "/").replace("C:/Users/", "users/")
    return value
