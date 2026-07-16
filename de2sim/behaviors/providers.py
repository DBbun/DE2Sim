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
        components = prompt.get("components", []) if isinstance(prompt.get("components"), list) else []
        requirements = prompt.get("requirements", []) if isinstance(prompt.get("requirements"), list) else []
        parameters = prompt.get("parameters", []) if isinstance(prompt.get("parameters"), list) else []
        models = prompt.get("physical_models", []) if isinstance(prompt.get("physical_models"), list) else []
        existing = prompt.get("existing_source_derived_behaviors", []) if isinstance(prompt.get("existing_source_derived_behaviors"), list) else []
        provenance = prompt.get("provenance_references", []) if isinstance(prompt.get("provenance_references"), list) else []
        proposals = []
        for component in components:
            component_id = str(component.get("stable_id", ""))
            if not component_id:
                continue
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
