"""Behavior proposal providers for DE2Sim behavior generation."""

from __future__ import annotations

import importlib
import hashlib
import json
import os
import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urlparse
import urllib.error
import urllib.request
from typing import Any, Protocol


class BehaviorProviderError(Exception):
    """Controlled behavior provider failure."""

    def __init__(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata or {}


class BehaviorProvider(Protocol):
    provider_name: str
    model: str
    generated_by: str
    last_metadata: dict[str, Any]

    def propose(self, prompt: dict[str, Any]) -> list[dict[str, Any]]:
        """Return raw proposal dictionaries without executing generated content."""


class OfflineTemplateProvider:
    provider_name = "offline"
    model = "deterministic-template-v1"
    generated_by = "offline_template"
    last_metadata: dict[str, Any] = {}

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
    model = ""
    generated_by = "external_generative_ai"

    def __init__(self, model: str = "", client: Any | None = None, timeout_s: float = 30.0, max_attempts: int = 1) -> None:
        self.model = model
        self._client = client
        self.timeout_s = timeout_s
        self.max_attempts = max(1, int(max_attempts))
        self.last_metadata: dict[str, Any] = {}

    def propose(self, prompt: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.model:
            raise BehaviorProviderError("OpenAI behavior provider requires an explicit model")
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise BehaviorProviderError("OPENAI_API_KEY is required for the OpenAI behavior provider")
        if self._client is not None:
            payload = self._client(prompt)
            response_text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True, ensure_ascii=False)
            self.last_metadata = _mock_metadata("openai", self.model, prompt, response_text, self.timeout_s)
            return _extract_json_proposals(payload)
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": "Return strict JSON with a top-level proposals array."},
                {"role": "user", "content": json.dumps(prompt, sort_keys=True, ensure_ascii=False)},
            ],
        }
        response, metadata = _https_json(
            "https://api.openai.com/v1/responses",
            payload,
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            self.timeout_s,
            self.max_attempts,
        )
        self.last_metadata = metadata
        text = _openai_text(response)
        self.last_metadata["model_output_hash"] = _sha256_text(text)
        return _extract_json_proposals(text)


class AnthropicProvider:
    provider_name = "anthropic"
    model = ""
    generated_by = "external_generative_ai"

    def __init__(self, model: str = "", client: Any | None = None, timeout_s: float = 30.0, max_attempts: int = 1) -> None:
        self.model = model
        self._client = client
        self.timeout_s = timeout_s
        self.max_attempts = max(1, int(max_attempts))
        self.last_metadata: dict[str, Any] = {}

    def propose(self, prompt: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.model:
            raise BehaviorProviderError("Anthropic behavior provider requires an explicit model")
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise BehaviorProviderError("ANTHROPIC_API_KEY is required for the Anthropic behavior provider")
        if self._client is not None:
            payload = self._client(prompt)
            response_text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True, ensure_ascii=False)
            self.last_metadata = _mock_metadata("anthropic", self.model, prompt, response_text, self.timeout_s)
            return _extract_json_proposals(payload)
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [
                {"role": "user", "content": "Return strict JSON with a top-level proposals array.\n" + json.dumps(prompt, sort_keys=True, ensure_ascii=False)}
            ],
        }
        response, metadata = _https_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            self.timeout_s,
            self.max_attempts,
        )
        self.last_metadata = metadata
        text = _anthropic_text(response)
        self.last_metadata["model_output_hash"] = _sha256_text(text)
        return _extract_json_proposals(text)


class OllamaProvider:
    provider_name = "ollama"
    generated_by = "local_generative_ai"
    default_base_url = "http://localhost:11434"
    deterministic_seed = 4262062

    def __init__(
        self,
        model: str = "gemma3:4b",
        base_url: str = default_base_url,
        client: Any | None = None,
        timeout_s: float = 30.0,
        max_attempts: int = 1,
    ) -> None:
        self.model = model or "gemma3:4b"
        self.base_url = _validate_loopback_ollama_base_url(base_url or self.default_base_url)
        self._client = client
        self.timeout_s = timeout_s
        self.max_attempts = max(1, int(max_attempts))
        self.last_metadata: dict[str, Any] = {}

    def propose(self, prompt: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.model:
            raise BehaviorProviderError("Ollama behavior provider requires an explicit model")
        payload = _ollama_payload(self.model, prompt, self.deterministic_seed)
        if self._client is not None:
            response = self._client(payload)
            response_text = response if isinstance(response, str) else json.dumps(response, sort_keys=True, ensure_ascii=False)
            self.last_metadata = _mock_metadata("ollama", self.model, payload, response_text, self.timeout_s)
            self.last_metadata.update(
                {
                    "generated_by": self.generated_by,
                    "actual_local_model_inference_occurred": False,
                    "actual_external_api_call_occurred": False,
                    "local_endpoint": "loopback_only",
                    "ollama_base_url": self.base_url,
                    "generation_mode": "canonical_asot_scaffold_plus_local_ai_enrichment",
                }
            )
            return [_extract_ollama_enrichment(response, self.last_metadata)]
        response, metadata = _http_json(
            self.base_url.rstrip("/") + "/api/generate",
            payload,
            {"Content-Type": "application/json"},
            self.timeout_s,
            self.max_attempts,
            actual_external_api_call_occurred=False,
        )
        text = _ollama_text(response, metadata)
        metadata.update(
            {
                "provider": "ollama",
                "model": self.model,
                "generated_by": self.generated_by,
                "actual_local_model_inference_occurred": True,
                "actual_external_api_call_occurred": False,
                "local_endpoint": "loopback_only",
                "ollama_base_url": self.base_url,
                "evidence_status": "confirmed_local_generation",
                "generation_mode": "canonical_asot_scaffold_plus_local_ai_enrichment",
                "created_at": str(response.get("created_at", "")),
                "done": bool(response.get("done", False)),
                "done_reason": str(response.get("done_reason", "")),
                "prompt_eval_count": response.get("prompt_eval_count", ""),
                "eval_count": response.get("eval_count", ""),
                "total_duration": response.get("total_duration", ""),
                "model_output_hash": _sha256_text(text),
                "original_response_hash": _sha256_text(text),
                "repair_attempted": False,
                "repair_succeeded": False,
                "parsing_status": "pending",
            }
        )
        self.last_metadata = metadata
        return [self._parse_or_repair_enrichment(text, metadata)]

    def _parse_or_repair_enrichment(self, text: str, metadata: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_model_json_text(text)
        try:
            result = _extract_json_object(normalized, "Ollama enrichment", "model enrichment is not valid JSON")
            metadata["parsing_status"] = "parsed"
            return result
        except BehaviorProviderError:
            metadata["parsing_status"] = "model enrichment is not valid JSON"
            metadata["failed_model_response"] = text
        metadata["repair_attempted"] = True
        repair_payload = _ollama_repair_payload(self.model, text, self.deterministic_seed)
        try:
            repaired_response, repair_metadata = _http_json(
                self.base_url.rstrip("/") + "/api/generate",
                repair_payload,
                {"Content-Type": "application/json"},
                self.timeout_s,
                1,
                actual_external_api_call_occurred=False,
            )
            repaired_text = _ollama_text(repaired_response, repair_metadata)
            metadata["repaired_response_hash"] = _sha256_text(repaired_text)
            metadata["attempt_count"] = int(metadata.get("attempt_count", 1) or 1) + int(repair_metadata.get("attempt_count", 1) or 1)
            result = _extract_json_object(_normalize_model_json_text(repaired_text), "Ollama enrichment", "local JSON repair failed")
            metadata["repair_succeeded"] = True
            metadata["parsing_status"] = "parsed_after_repair"
            return result
        except BehaviorProviderError as exc:
            metadata["repair_succeeded"] = False
            metadata["parsing_status"] = "local JSON repair failed"
            raise BehaviorProviderError("local JSON repair failed", metadata) from exc


def get_provider(
    name: str,
    model: str = "",
    timeout_s: float = 30.0,
    max_attempts: int = 1,
    ollama_base_url: str = OllamaProvider.default_base_url,
) -> BehaviorProvider:
    normalized = str(name or "offline").strip().lower()
    if normalized == "offline":
        return OfflineTemplateProvider()
    if normalized == "openai":
        return OpenAIProvider(model=model or os.environ.get("DE2SIM_OPENAI_MODEL", ""), timeout_s=timeout_s, max_attempts=max_attempts)
    if normalized == "anthropic":
        return AnthropicProvider(model=model or os.environ.get("DE2SIM_ANTHROPIC_MODEL", ""), timeout_s=timeout_s, max_attempts=max_attempts)
    if normalized == "ollama":
        return OllamaProvider(model=model or os.environ.get("DE2SIM_OLLAMA_MODEL", "gemma3:4b"), base_url=ollama_base_url, timeout_s=timeout_s, max_attempts=max_attempts)
    raise BehaviorProviderError(f"unsupported behavior AI provider: {name}")


def _extract_json_proposals(response: Any) -> list[dict[str, Any]]:
    try:
        if isinstance(response, dict):
            payload = response
        else:
            payload = json.loads(str(response))
    except json.JSONDecodeError as exc:
        raise BehaviorProviderError("provider returned malformed JSON") from exc
    proposals = payload.get("proposals") if isinstance(payload, dict) else None
    if not isinstance(proposals, list) or not all(isinstance(item, dict) for item in proposals):
        raise BehaviorProviderError("provider response must contain a proposals array")
    return proposals


def _https_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_s: float, max_attempts: int) -> tuple[dict[str, Any], dict[str, Any]]:
    return _http_json(url, payload, headers, timeout_s, max_attempts, actual_external_api_call_occurred=True)


def _http_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
    max_attempts: int,
    actual_external_api_call_occurred: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    started = _utc_now()
    attempts = 0
    last_exc: Exception | None = None
    metadata: dict[str, Any] = {}
    while attempts < max(1, int(max_attempts)):
        attempts += 1
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                raw = response.read().decode("utf-8")
                status = int(response.getcode() if hasattr(response, "getcode") and response.getcode() is not None else getattr(response, "status", 200))
                if status < 200 or status >= 300:
                    raise BehaviorProviderError(f"provider HTTP error: {status}")
                received = _utc_now()
                metadata = {
                    "request_started_at_utc": started,
                    "response_received_at_utc": received,
                    "http_status": status,
                    "provider_request_id": _safe_header(response, ("x-request-id", "request-id", "anthropic-request-id")),
                    "request_hash": _sha256_bytes(body),
                    "response_hash": _sha256_text(raw),
                    "attempt_count": attempts,
                    "timeout_seconds": timeout_s,
                    "actual_external_api_call_occurred": actual_external_api_call_occurred,
                }
                break
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            if "not found" in detail.lower() or exc.code == 404:
                raise BehaviorProviderError(f"provider model not found or HTTP error: {exc.code}") from exc
            raise BehaviorProviderError(f"provider HTTP error: {exc.code}") from exc
        except TimeoutError as exc:
            last_exc = exc
            if attempts >= max(1, int(max_attempts)):
                raise BehaviorProviderError("provider request timed out") from exc
        except (urllib.error.URLError, socket.gaierror, ssl.SSLError, OSError) as exc:
            last_exc = exc
            if attempts >= max(1, int(max_attempts)):
                raise BehaviorProviderError("provider network error") from exc
    else:
        raise BehaviorProviderError("provider network error") from last_exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        message = "provider returned malformed JSON" if actual_external_api_call_occurred else "malformed Ollama HTTP response"
        raise BehaviorProviderError(message, metadata) from exc
    if not isinstance(decoded, dict):
        raise BehaviorProviderError("provider JSON response must be an object")
    return decoded, metadata


def _mock_metadata(provider: str, model: str, prompt: dict[str, Any], response_text: str, timeout_s: float) -> dict[str, Any]:
    body = json.dumps({"model": model, "prompt": prompt}, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {
        "provider": provider,
        "model": model,
        "request_started_at_utc": "mocked-test-only",
        "response_received_at_utc": "mocked-test-only",
        "http_status": 200,
        "provider_request_id": "",
        "request_hash": _sha256_bytes(body),
        "response_hash": _sha256_text(response_text),
        "attempt_count": 1,
        "timeout_seconds": timeout_s,
        "actual_external_api_call_occurred": False,
        "actual_local_model_inference_occurred": False,
        "evidence_status": "mocked_test_only",
        "repair_attempted": False,
        "repair_succeeded": False,
        "parsing_status": "mocked_test_only",
    }


def _safe_header(response: Any, names: tuple[str, ...]) -> str:
    headers = getattr(response, "headers", None)
    for name in names:
        value = ""
        if headers is not None and hasattr(headers, "get"):
            value = str(headers.get(name, "") or "")
        elif hasattr(response, "getheader"):
            value = str(response.getheader(name, "") or "")
        if value and all(ch.isalnum() or ch in "-_." for ch in value):
            return value[:128]
    return ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _openai_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    texts: list[str] = []
    for item in response.get("output", []) if isinstance(response.get("output"), list) else []:
        for content in item.get("content", []) if isinstance(item, dict) and isinstance(item.get("content"), list) else []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                texts.append(content["text"])
    if not texts:
        raise BehaviorProviderError("OpenAI response did not contain JSON text")
    return "\n".join(texts)


def _anthropic_text(response: dict[str, Any]) -> str:
    texts = [
        item.get("text", "")
        for item in response.get("content", [])
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
    ]
    if not texts:
        raise BehaviorProviderError("Anthropic response did not contain JSON text")
    return "\n".join(texts)


def _ollama_payload(model: str, prompt: dict[str, Any], seed: int) -> dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "behavior_summary",
            "state_descriptions",
            "transition_rationale",
            "state_actions",
            "risks",
            "assumptions",
            "limitations",
        ],
        "properties": {
            "behavior_summary": {"type": "string"},
            "state_descriptions": {
                "type": "object",
                "additionalProperties": False,
                "required": ["preflight", "mission_flight", "return_to_base", "landed"],
                "properties": {
                    "preflight": {"type": "string"},
                    "mission_flight": {"type": "string"},
                    "return_to_base": {"type": "string"},
                    "landed": {"type": "string"},
                },
            },
            "transition_rationale": {
                "type": "object",
                "additionalProperties": False,
                "required": ["preflight_to_mission_flight", "mission_flight_to_return_to_base", "return_to_base_to_landed"],
                "properties": {
                    "preflight_to_mission_flight": {"type": "string"},
                    "mission_flight_to_return_to_base": {"type": "string"},
                    "return_to_base_to_landed": {"type": "string"},
                },
            },
            "state_actions": {
                "type": "object",
                "additionalProperties": False,
                "required": ["preflight", "mission_flight", "return_to_base", "landed"],
                "properties": {
                    state: {"type": "array", "items": {"type": "string"}}
                    for state in ("preflight", "mission_flight", "return_to_base", "landed")
                },
            },
            "risks": {
                "type": "array",
                "items": {"type": "string"},
            },
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
    }
    prompt_text = (
        "Return strict JSON only. Generate only the requested enrichment JSON object. "
        "All entries must be based only on the supplied ASOT evidence. "
        "Do not introduce new numerical values. Do not invent new requirements, parameters, components, "
        "physical models, ownership, performance values, or source claims. "
        "Assumptions must be explicitly listed. Empty arrays are allowed when the evidence does not support additional detail. "
        "Do not return proposal IDs, stable IDs, states, transitions, guards, provider metadata, or evidence status.\n"
        + json.dumps(_compact_ollama_prompt(prompt), sort_keys=True, ensure_ascii=False)
    )
    return {
        "model": model,
        "prompt": prompt_text,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0, "seed": seed, "num_ctx": 8192, "num_predict": 2048},
        "keep_alive": "10m",
    }


def _ollama_repair_payload(model: str, malformed_text: str, seed: int) -> dict[str, Any]:
    schema = _ollama_payload(model, {}, seed)["format"]
    prompt_text = (
        "Repair JSON syntax only. Return only the corrected JSON object matching the exact schema. "
        "Do not add content, values, numbers, facts, IDs, assumptions, claims, or fields. "
        "If syntax cannot be repaired without adding content, return the closest syntactically valid object using only existing content.\n"
        "Exact schema:\n"
        + json.dumps(schema, sort_keys=True, ensure_ascii=False)
        + "\nMalformed model-generated enrichment text:\n"
        + malformed_text
    )
    return {
        "model": model,
        "prompt": prompt_text,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0, "seed": seed, "num_ctx": 8192, "num_predict": 2048},
        "keep_alive": "10m",
    }


def _compact_ollama_prompt(prompt: dict[str, Any]) -> dict[str, Any]:
    def text(item: dict[str, Any]) -> str:
        return json.dumps(item, sort_keys=True).lower()

    requirements = [item for item in prompt.get("requirements", []) if isinstance(item, dict)]
    parameters = [item for item in prompt.get("parameters", []) if isinstance(item, dict)]
    behaviors = [item for item in prompt.get("existing_source_derived_behaviors", []) if isinstance(item, dict)]
    provenance = [item for item in prompt.get("provenance_references", []) if isinstance(item, dict)]
    selected_requirements = [item for item in requirements if ("battery" in text(item) and "return" in text(item) and "base" in text(item)) or ("maximum" in text(item) and "speed" in text(item))]
    selected_parameters = [item for item in parameters if ("battery" in text(item) and ("threshold" in text(item) or "capacity" in text(item))) or ("speed" in text(item) and ("max" in text(item) or "maximum" in text(item)))]
    selected_behaviors = [item for item in behaviors if "returntobase" in text(item).replace("_", "").replace("-", "").replace(" ", "") or ("return" in text(item) and "base" in text(item))]
    referenced = {str(ref) for item in selected_requirements + selected_parameters + selected_behaviors for ref in item.get("source_references", [])}
    selected_provenance = [item for item in provenance if item.get("provenance_id") in referenced or any(tid in {r.get("stable_id") for r in selected_requirements + selected_parameters + selected_behaviors} for tid in item.get("target_entity_ids", []))]
    return {
        "task": "Enrich the ASOT-bound Low Battery Return-to-Base behavior only.",
        "required_uas_behavior": prompt.get("required_uas_behavior", {}),
        "requirements": selected_requirements,
        "parameters": selected_parameters,
        "existing_source_derived_behaviors": selected_behaviors,
        "provenance_references": selected_provenance,
    }


def _extract_ollama_enrichment(response: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, dict) and "response" in response:
        text = _ollama_text(response, metadata)
        return _extract_json_object(_normalize_model_json_text(text), "Ollama enrichment", "model enrichment is not valid JSON")
    if isinstance(response, dict):
        return response
    return _extract_json_object(_normalize_model_json_text(str(response)), "Ollama enrichment", "model enrichment is not valid JSON")


def _extract_json_object(response: Any, label: str, malformed_message: str = "provider returned malformed JSON") -> dict[str, Any]:
    try:
        payload = response if isinstance(response, dict) else json.loads(str(response))
    except json.JSONDecodeError as exc:
        raise BehaviorProviderError(malformed_message) from exc
    if not isinstance(payload, dict):
        raise BehaviorProviderError(f"{label} response must be a JSON object")
    return payload


def _ollama_text(response: dict[str, Any], metadata: dict[str, Any]) -> str:
    if not isinstance(response.get("response"), str):
        metadata["parsing_status"] = "Ollama response missing response field"
        raise BehaviorProviderError("Ollama response missing response field", metadata)
    return response["response"]


def _normalize_model_json_text(text: str) -> str:
    normalized = text.lstrip("\ufeff").strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"} and lines[-1].strip() == "```":
            normalized = "\n".join(lines[1:-1]).strip()
    return normalized


def _validate_loopback_ollama_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "http":
        raise BehaviorProviderError("Ollama base URL must use http on a loopback host")
    host = parsed.hostname or ""
    if host.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise BehaviorProviderError("Ollama base URL must use a loopback host")
    if parsed.username or parsed.password:
        raise BehaviorProviderError("Ollama base URL must not include credentials")
    if "ollama.com" in base_url.lower():
        raise BehaviorProviderError("Ollama provider must not contact ollama.com")
    path = parsed.path.rstrip("/")
    if path not in {"", "/"}:
        raise BehaviorProviderError("Ollama base URL must not include a path; /api/generate is appended by DE2Sim")
    return base_url.rstrip("/")


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
