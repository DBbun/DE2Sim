"""Generate and validate Phase 4A behavior proposals."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from de2sim.asot.schema import utc_now
from de2sim.behaviors.prompt_builder import build_behavior_prompt, prompt_hash
from de2sim.behaviors.providers import BehaviorProviderError, get_provider
from de2sim.behaviors.schema import (
    BehaviorProposal,
    behavior_proposal_from_dict,
    behavior_proposal_to_dict,
    deterministic_proposal_id,
    validate_behavior_proposal,
)


class BehaviorProposalError(Exception):
    """Controlled behavior proposal generation failure."""

    def __init__(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata or {}


def generate_behavior_proposals(
    asot: dict[str, Any],
    provider_name: str = "offline",
    model: str = "",
    timeout_seconds: float = 30.0,
    max_attempts: int = 1,
    external_generation_purpose: str = "",
    ollama_base_url: str = "http://localhost:11434",
) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = build_behavior_prompt(asot, external_generation_purpose)
    phash = prompt_hash(prompt)
    try:
        provider = get_provider(provider_name, model=model, timeout_s=timeout_seconds, max_attempts=max_attempts, ollama_base_url=ollama_base_url)
        raw_proposals = provider.propose(prompt)
    except BehaviorProviderError as exc:
        raise BehaviorProposalError(str(exc), exc.metadata) from exc
    generated_at = utc_now()
    proposals: list[dict[str, Any]] = []
    provider.last_metadata["prompt_hash"] = phash
    if provider.provider_name == "ollama":
        try:
            raw_proposals = [_merge_ollama_enrichment(asot, raw_proposals[0] if raw_proposals else {}, provider.last_metadata)]
        except BehaviorProposalError as exc:
            provider.last_metadata.setdefault("validation_status", "failed")
            provider.last_metadata.setdefault("validation_errors", [str(exc)])
            if provider.last_metadata.get("repair_attempted") and provider.last_metadata.get("repair_succeeded"):
                raise BehaviorProposalError("repaired enrichment failed schema validation: " + str(exc), provider.last_metadata) from exc
            raise BehaviorProposalError(str(exc), provider.last_metadata) from exc
    for raw in raw_proposals:
        raw = dict(raw)
        raw["provider"] = provider.provider_name
        raw["model"] = provider.model
        raw["prompt_hash"] = phash
        raw["request_hash"] = provider.last_metadata.get("request_hash", "")
        raw["response_hash"] = provider.last_metadata.get("response_hash", "")
        raw["actual_external_api_call_occurred"] = bool(provider.last_metadata.get("actual_external_api_call_occurred", False))
        raw["actual_local_model_inference_occurred"] = bool(provider.last_metadata.get("actual_local_model_inference_occurred", False))
        raw["evidence_status"] = str(provider.last_metadata.get("evidence_status", ""))
        raw["local_endpoint"] = str(provider.last_metadata.get("local_endpoint", ""))
        raw["generation_mode"] = str(provider.last_metadata.get("generation_mode", raw.get("generation_mode", "")))
        raw["enrichment_hash"] = str(provider.last_metadata.get("enrichment_hash", raw.get("enrichment_hash", "")))
        for evidence_key in (
            "enrichment_completeness",
            "generated_field_count",
            "generated_character_count",
            "generated_json_paths",
            "omitted_or_empty_json_paths",
            "deterministic_structure_json_paths",
            "normalized_enrichment_hash",
            "ai_contribution_manifest",
        ):
            if evidence_key in provider.last_metadata:
                raw[evidence_key] = provider.last_metadata[evidence_key]
        raw["generated_at_utc"] = generated_at
        raw["approval_status"] = "proposed"
        raw["generated_by"] = provider.generated_by
        raw["proposal_id"] = deterministic_proposal_id(raw)
        raw["validated_proposal_hash"] = _sha256_json(raw)
        provider.last_metadata["validated_proposal_hash"] = raw["validated_proposal_hash"]
        if provider.provider_name == "ollama" and isinstance(raw.get("ai_contribution_manifest"), dict):
            raw["ai_contribution_manifest"]["merged_proposal_hash"] = raw["validated_proposal_hash"]
            provider.last_metadata["ai_contribution_manifest"] = raw["ai_contribution_manifest"]
        proposal = behavior_proposal_from_dict(raw)
        warnings = sorted(set(proposal.validation_warnings + validate_behavior_proposal(proposal, asot)))
        if provider.provider_name in {"openai", "anthropic", "ollama"}:
            warnings = sorted(set(warnings + _validate_external_uas_proposal(proposal, asot)))
            if warnings:
                provider.last_metadata.setdefault("validation_status", "failed")
                raise BehaviorProposalError("external behavior proposal failed validation: " + "; ".join(warnings))
        if provider.provider_name == "ollama":
            provider.last_metadata["validation_status"] = "passed"
        proposal.validation_warnings = warnings
        proposals.append(behavior_proposal_to_dict(proposal))
    proposals = sorted(proposals, key=lambda item: item["proposal_id"])
    proposal_payload = {
        "schema_version": "de2sim.behavior_proposals.v1",
        "asot_id": str(asot.get("asot_id", "")),
        "provider": provider.provider_name,
        "model": provider.model,
        "prompt_hash": phash,
        "generated_at_utc": generated_at,
        "external_call_metadata": _safe_external_metadata(provider.last_metadata, provider.provider_name, provider.model, phash),
        "proposals": proposals,
    }
    prompt_payload = {"schema_version": "de2sim.behavior_prompt.v1", "prompt_hash": phash, "prompt": prompt}
    return prompt_payload, proposal_payload


def write_behavior_generation_outputs(
    asot: dict[str, Any],
    output_dir: Path | str,
    provider_name: str = "offline",
    model: str = "",
    timeout_seconds: float = 30.0,
    max_attempts: int = 1,
    external_generation_purpose: str = "",
    ollama_base_url: str = "http://localhost:11434",
) -> dict[str, Path]:
    from de2sim.visualization.behavior_review import write_behavior_review

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    try:
        prompt_payload, proposal_payload = generate_behavior_proposals(
            asot,
            provider_name,
            model=model,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            external_generation_purpose=external_generation_purpose,
            ollama_base_url=ollama_base_url,
        )
    except BehaviorProposalError as exc:
        if provider_name == "ollama" and exc.metadata:
            _write_ollama_diagnostics(output, exc.metadata)
        raise
    prompt_path = output / "behavior_prompt.json"
    proposals_path = output / "behavior_proposals.json"
    report_path = output / "behavior_generation_report.json"
    review_path = output / "behavior_review.html"
    audit_path = output / "external_generation_audit.json"
    summary_path = output / "external_generation_summary.md"
    _write_json(prompt_payload, prompt_path)
    _write_json(proposal_payload, proposals_path)
    report = {
        "valid": not any(item.get("validation_warnings") for item in proposal_payload["proposals"]),
        "proposal_count": len(proposal_payload["proposals"]),
        "provider": proposal_payload["provider"],
        "model": proposal_payload["model"],
        "prompt_hash": proposal_payload["prompt_hash"],
        "warnings": sorted({warning for item in proposal_payload["proposals"] for warning in item.get("validation_warnings", [])}),
        "limitations": [
            "Phase 4B produces review candidates only.",
            "Offline candidates are deterministic templates, not generative-AI output.",
            "No simulation or executable behavior code is generated.",
        ],
    }
    _write_json(report, report_path)
    if proposal_payload.get("provider") == "ollama":
        _write_ollama_diagnostics(output, proposal_payload.get("external_call_metadata", {}))
    if proposal_payload.get("provider") == "ollama":
        manifest = proposal_payload.get("external_call_metadata", {}).get("ai_contribution_manifest", {})
        if isinstance(manifest, dict) and manifest:
            _write_json(manifest, output / "ai_contribution_manifest.json")
    audit = build_external_generation_audit(asot, prompt_payload, proposal_payload, None)
    _write_json(audit, audit_path)
    summary_path.write_text(_external_generation_summary(audit), encoding="utf-8", newline="\n")
    write_behavior_review(asot, proposal_payload, review_path)
    return {
        "behavior_prompt": prompt_path,
        "behavior_proposals": proposals_path,
        "behavior_review": review_path,
        "behavior_generation_report": report_path,
        "external_generation_audit": audit_path,
        "external_generation_summary": summary_path,
        "ollama_response_audit": output / "ollama_response_audit.json",
        "ollama_model_output": output / "ollama_model_output.json",
        "ai_contribution_manifest": output / "ai_contribution_manifest.json",
    }


def load_behavior_proposals(path: Path | str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BehaviorProposalError(f"failed to read behavior proposals: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("proposals"), list):
        raise BehaviorProposalError("behavior proposals JSON must contain a proposals array")
    return payload


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def build_external_generation_audit(
    asot: dict[str, Any],
    prompt_payload: dict[str, Any],
    proposal_payload: dict[str, Any],
    approval_payload: dict[str, Any] | None,
    approved_asot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proposals = [item for item in proposal_payload.get("proposals", []) if isinstance(item, dict)]
    proposal = proposals[0] if proposals else {}
    metadata = proposal_payload.get("external_call_metadata", {}) if isinstance(proposal_payload.get("external_call_metadata"), dict) else {}
    generated_by = str(proposal.get("generated_by", ""))
    actual = bool(proposal.get("actual_external_api_call_occurred", False) and metadata.get("actual_external_api_call_occurred", False))
    local_actual = bool(proposal.get("actual_local_model_inference_occurred", False) and metadata.get("actual_local_model_inference_occurred", False))
    if generated_by == "offline_template" or proposal_payload.get("provider") == "offline":
        evidence_status = "offline_non_generative"
    elif metadata.get("evidence_status") == "mocked_test_only":
        evidence_status = "mocked_test_only"
    elif generated_by == "local_generative_ai" and local_actual and not actual:
        evidence_status = "confirmed_local_generation"
    elif generated_by == "external_generative_ai" and actual:
        evidence_status = "confirmed_external_generation"
    elif proposal_payload.get("provider") in {"openai", "anthropic", "ollama"}:
        evidence_status = "external_generation_failed"
    else:
        evidence_status = "not_available"
    decisions = approval_payload.get("decisions", []) if isinstance(approval_payload, dict) else []
    decision = next((item for item in decisions if isinstance(item, dict) and item.get("proposal_id") == proposal.get("proposal_id")), {})
    approved_behavior = {}
    if isinstance(approved_asot, dict):
        approved_behavior = next((item for item in approved_asot.get("behaviors", []) if isinstance(item, dict) and item.get("proposal_id") == proposal.get("proposal_id")), {})
    validated_hash = _sha256_json(proposal) if proposal else ""
    return {
        "schema_version": "de2sim.external_generation_audit.v1",
        "provider": proposal_payload.get("provider", ""),
        "model": proposal_payload.get("model", ""),
        "generated_by": generated_by,
        "evidence_status": evidence_status,
        "actual_external_api_call_occurred": actual,
        "actual_local_model_inference_occurred": local_actual,
        "local_endpoint": metadata.get("local_endpoint", proposal.get("local_endpoint", "")),
        "prompt_hash": prompt_payload.get("prompt_hash", proposal_payload.get("prompt_hash", "")),
        "request_hash": metadata.get("request_hash", proposal.get("request_hash", "")),
        "response_hash": metadata.get("response_hash", proposal.get("response_hash", "")),
        "validated_proposal_hash": validated_hash,
        "enrichment_hash": metadata.get("enrichment_hash", proposal.get("enrichment_hash", "")),
        "enrichment_completeness": metadata.get("enrichment_completeness", proposal.get("enrichment_completeness", "")),
        "generated_field_count": metadata.get("generated_field_count", proposal.get("generated_field_count", 0)),
        "generated_character_count": metadata.get("generated_character_count", proposal.get("generated_character_count", 0)),
        "generated_json_paths": metadata.get("generated_json_paths", proposal.get("generated_json_paths", [])),
        "omitted_or_empty_json_paths": metadata.get("omitted_or_empty_json_paths", proposal.get("omitted_or_empty_json_paths", [])),
        "deterministic_structure_json_paths": metadata.get("deterministic_structure_json_paths", proposal.get("deterministic_structure_json_paths", [])),
        "normalized_enrichment_hash": metadata.get("normalized_enrichment_hash", proposal.get("normalized_enrichment_hash", "")),
        "ai_contribution_manifest": metadata.get("ai_contribution_manifest", proposal.get("ai_contribution_manifest", {})),
        "generation_mode": metadata.get("generation_mode", proposal.get("generation_mode", "")),
        "provider_request_id": metadata.get("provider_request_id", ""),
        "attempt_count": metadata.get("attempt_count", 0),
        "timeout_seconds": metadata.get("timeout_seconds", 0),
        "http_status": metadata.get("http_status", ""),
        "created_at": metadata.get("created_at", ""),
        "done": metadata.get("done", ""),
        "done_reason": metadata.get("done_reason", ""),
        "prompt_eval_count": metadata.get("prompt_eval_count", ""),
        "eval_count": metadata.get("eval_count", ""),
        "total_duration": metadata.get("total_duration", ""),
        "parsing_status": metadata.get("parsing_status", ""),
        "repair_attempted": metadata.get("repair_attempted", False),
        "repair_succeeded": metadata.get("repair_succeeded", False),
        "original_response_hash": metadata.get("original_response_hash", ""),
        "repaired_response_hash": metadata.get("repaired_response_hash", ""),
        "request_started_at_utc": metadata.get("request_started_at_utc", ""),
        "response_received_at_utc": metadata.get("response_received_at_utc", ""),
        "validation_status": metadata.get("validation_status", "passed" if proposal and not proposal.get("validation_warnings") else "failed"),
        "proposal_id": proposal.get("proposal_id", ""),
        "proposal_name": proposal.get("name", ""),
        "approval_status": decision.get("approval_status", proposal.get("approval_status", "")),
        "approved_behavior_id": approved_behavior.get("stable_id", ""),
        "related_asot_ids": {
            "asot_id": asot.get("asot_id", ""),
            "approved_asot_id": approved_asot.get("asot_id", "") if isinstance(approved_asot, dict) else "",
        },
        "limitations": [
            "Generation is constrained to behavior proposal text and evidence references.",
            "Generated behavior still requires human approval before ASOT integration.",
            "No generated code is executed.",
        ],
    }


def _safe_external_metadata(metadata: dict[str, Any], provider: str, model: str, phash: str) -> dict[str, Any]:
    if not metadata:
        return {}
    allowed = {
        "request_started_at_utc",
        "response_received_at_utc",
        "http_status",
        "provider_request_id",
        "request_hash",
        "response_hash",
        "model_output_hash",
        "attempt_count",
        "timeout_seconds",
        "actual_external_api_call_occurred",
        "actual_local_model_inference_occurred",
        "evidence_status",
        "local_endpoint",
        "generation_mode",
        "enrichment_hash",
        "validated_proposal_hash",
        "created_at",
        "done",
        "done_reason",
        "prompt_eval_count",
        "eval_count",
        "total_duration",
        "parsing_status",
        "repair_attempted",
        "repair_succeeded",
        "original_response_hash",
        "repaired_response_hash",
        "failed_model_response",
        "validation_status",
        "validation_errors",
        "normalized_enrichment",
        "enrichment_completeness",
        "generated_field_count",
        "generated_character_count",
        "generated_json_paths",
        "omitted_or_empty_json_paths",
        "deterministic_structure_json_paths",
        "normalized_enrichment_hash",
        "merged_proposal_hash",
        "ai_contribution_manifest",
    }
    safe = {key: metadata[key] for key in sorted(allowed) if key in metadata}
    generated_by = "external_generative_ai" if provider in {"openai", "anthropic"} else "local_generative_ai" if provider == "ollama" else "offline_template"
    safe.update({"provider": provider, "model": model, "prompt_hash": phash, "generated_by": generated_by})
    return safe


def _write_ollama_diagnostics(output: Path, metadata: dict[str, Any]) -> None:
    audit = {
        "schema_version": "de2sim.ollama_response_audit.v1",
        "http_response_body_sha256": metadata.get("response_hash", ""),
        "model_generated_response_string_sha256": metadata.get("model_output_hash", metadata.get("original_response_hash", "")),
        "http_status": metadata.get("http_status", ""),
        "model": metadata.get("model", ""),
        "done": metadata.get("done", ""),
        "done_reason": metadata.get("done_reason", ""),
        "prompt_eval_count": metadata.get("prompt_eval_count", ""),
        "eval_count": metadata.get("eval_count", ""),
        "total_duration": metadata.get("total_duration", ""),
        "parsing_status": metadata.get("parsing_status", ""),
        "repair_attempted": bool(metadata.get("repair_attempted", False)),
        "repair_succeeded": bool(metadata.get("repair_succeeded", False)),
        "original_response_hash": metadata.get("original_response_hash", metadata.get("model_output_hash", "")),
        "repaired_response_hash": metadata.get("repaired_response_hash", ""),
        "limitations": [
            "Only the model-generated response string is written to ollama_failed_content.txt when parsing fails.",
            "Request headers, environment data, secrets, and unrelated paths are not written.",
            "JSON repair is limited to one local loopback Ollama inference.",
        ],
    }
    _write_json(audit, output / "ollama_response_audit.json")
    model_output = {
        "schema_version": "de2sim.ollama_model_output.v1",
        "provider": "ollama",
        "model": metadata.get("model", ""),
        "parsing_status": metadata.get("parsing_status", ""),
        "validation_status": metadata.get("validation_status", ""),
        "normalized_parsed_enrichment": metadata.get("normalized_enrichment", {}) if metadata.get("parsing_status") in {"parsed", "parsed_after_repair", "mocked_test_only"} else {},
        "model_output_hash": metadata.get("model_output_hash", metadata.get("original_response_hash", "")),
        "validation_errors": metadata.get("validation_errors", []),
    }
    _write_json(model_output, output / "ollama_model_output.json")
    if audit["parsing_status"] not in {"parsed", "parsed_after_repair", "mocked_test_only"} and metadata.get("failed_model_response"):
        (output / "ollama_failed_content.txt").write_text(str(metadata.get("failed_model_response", "")), encoding="utf-8", newline="\n")


def _validate_external_uas_proposal(proposal: Any, asot: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    evidence = _required_uas_ids(asot)
    if proposal.provider == "ollama":
        if proposal.generated_by != "local_generative_ai":
            warnings.append("local proposal must be labeled generated_by: local_generative_ai")
        if proposal.actual_external_api_call_occurred:
            warnings.append("local proposal must not record an external API call")
        if not proposal.actual_local_model_inference_occurred and proposal.evidence_status != "mocked_test_only":
            warnings.append("local proposal must confirm actual_local_model_inference_occurred")
        if proposal.local_endpoint != "loopback_only" and proposal.evidence_status != "mocked_test_only":
            warnings.append("local proposal must record loopback_only endpoint")
    elif proposal.generated_by != "external_generative_ai":
        warnings.append("external proposal must be labeled generated_by: external_generative_ai")
    if proposal.provider not in {"openai", "anthropic", "ollama"} or not proposal.model:
        warnings.append("external proposal must record provider and model")
    if proposal.provider in {"openai", "anthropic"} and not proposal.actual_external_api_call_occurred:
        warnings.append("external proposal must confirm actual_external_api_call_occurred")
    if proposal.name != "Low Battery Return-to-Base":
        warnings.append("external proposal must be named Low Battery Return-to-Base")
    if proposal.states != ["preflight", "mission_flight", "return_to_base", "landed"]:
        warnings.append("external proposal must use the required state order")
    sequence = [(item.get("from"), item.get("to")) for item in proposal.transitions]
    for edge in [("preflight", "mission_flight"), ("mission_flight", "return_to_base"), ("return_to_base", "landed")]:
        if edge not in sequence:
            warnings.append(f"missing required transition: {edge[0]} -> {edge[1]}")
    if "battery_state <= battery_threshold" not in proposal.guards and "battery_state <= battery_threshold" not in json.dumps(proposal.transitions):
        warnings.append("missing symbolic battery guard")
    for key, field in (
        ("low_battery_requirement", proposal.referenced_requirement_ids),
        ("max_speed_requirement", proposal.referenced_requirement_ids),
        ("battery_threshold", proposal.referenced_parameter_ids),
        ("max_speed", proposal.referenced_parameter_ids),
        ("battery_capacity", proposal.referenced_parameter_ids),
        ("return_to_base", proposal.referenced_behavior_ids),
    ):
        if evidence.get(key) and evidence[key] not in field:
            warnings.append(f"external proposal does not reference required ASOT evidence: {key}")
    return sorted(set(warnings))


def _merge_ollama_enrichment(asot: dict[str, Any], enrichment: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(enrichment, dict):
        raise BehaviorProposalError("Ollama enrichment must be a JSON object")
    normalized, contribution = _normalize_ollama_enrichment(enrichment, asot)
    scaffold = _canonical_ollama_scaffold(asot)
    enrichment_hash = _sha256_json(normalized)
    manifest = _ai_contribution_manifest(metadata, normalized, contribution)
    metadata["enrichment_hash"] = enrichment_hash
    metadata["normalized_enrichment_hash"] = enrichment_hash
    metadata["normalized_enrichment"] = normalized
    metadata["enrichment_completeness"] = contribution["enrichment_completeness"]
    metadata["generated_field_count"] = contribution["generated_field_count"]
    metadata["generated_character_count"] = contribution["generated_character_count"]
    metadata["generated_json_paths"] = contribution["generated_json_paths"]
    metadata["omitted_or_empty_json_paths"] = contribution["omitted_or_empty_json_paths"]
    metadata["deterministic_structure_json_paths"] = contribution["deterministic_structure_json_paths"]
    metadata["ai_contribution_manifest"] = manifest
    metadata["validation_status"] = "passed"
    metadata["generation_mode"] = "canonical_asot_scaffold_plus_local_ai_enrichment"
    state_actions = normalized.get("state_actions", {}) if isinstance(normalized.get("state_actions"), dict) else {}
    merged_actions = list(scaffold["actions"])
    for state in ("preflight", "mission_flight", "return_to_base", "landed"):
        merged_actions.extend(str(item).strip() for item in state_actions.get(state, []) if str(item).strip())
    return {
        **scaffold,
        "description": str(normalized.get("behavior_summary", "")).strip() or scaffold["description"],
        "actions": sorted(set(merged_actions)),
        "assumptions": sorted(set(scaffold["assumptions"] + [str(item).strip() for item in normalized.get("assumptions", []) if str(item).strip()])),
        "risks": sorted(set(scaffold["risks"] + [str(item).strip() for item in normalized.get("risks", []) if str(item).strip()])),
        "limitations": [str(item).strip() for item in normalized.get("limitations", []) if str(item).strip()],
        "local_ai_enrichment": normalized,
        "generation_mode": "canonical_asot_scaffold_plus_local_ai_enrichment",
        "enrichment_hash": enrichment_hash,
        "enrichment_completeness": contribution["enrichment_completeness"],
        "generated_field_count": contribution["generated_field_count"],
        "generated_character_count": contribution["generated_character_count"],
        "generated_json_paths": contribution["generated_json_paths"],
        "omitted_or_empty_json_paths": contribution["omitted_or_empty_json_paths"],
        "deterministic_structure_json_paths": contribution["deterministic_structure_json_paths"],
        "normalized_enrichment_hash": enrichment_hash,
        "ai_contribution_manifest": manifest,
        "confidence": 0.72,
    }


OLLAMA_ENRICHMENT_KEYS = {
    "behavior_summary",
    "state_descriptions",
    "transition_rationale",
    "state_actions",
    "risks",
    "assumptions",
    "limitations",
}
OLLAMA_STATES = ("preflight", "mission_flight", "return_to_base", "landed")
OLLAMA_RATIONALE_KEYS = ("preflight_to_mission_flight", "mission_flight_to_return_to_base", "return_to_base_to_landed")
DETERMINISTIC_STRUCTURE_JSON_PATHS = [
    "$.name",
    "$.states",
    "$.transitions",
    "$.guards",
    "$.referenced_requirement_ids",
    "$.referenced_parameter_ids",
    "$.referenced_behavior_ids",
    "$.source_provenance_ids",
    "$.proposal_id",
    "$.stable_id",
]


def _normalize_ollama_enrichment(enrichment: dict[str, Any], asot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    unknown = sorted(set(enrichment) - OLLAMA_ENRICHMENT_KEYS)
    if unknown:
        raise BehaviorProposalError("Ollama enrichment contains unknown keys: " + ", ".join(unknown))
    if "behavior_summary" in enrichment and not isinstance(enrichment.get("behavior_summary"), str):
        raise BehaviorProposalError("Ollama enrichment behavior_summary must be a string")
    normalized: dict[str, Any] = {
        "behavior_summary": str(enrichment.get("behavior_summary", "")).strip(),
        "state_descriptions": {},
        "transition_rationale": {},
        "state_actions": {},
        "risks": [],
        "assumptions": [],
        "limitations": [],
    }
    for key in ("risks", "assumptions", "limitations"):
        value = enrichment.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise BehaviorProposalError(f"Ollama enrichment {key} must be an array of strings")
        normalized[key] = [item.strip() for item in value if item.strip()]
    descriptions = enrichment.get("state_descriptions")
    if descriptions is None:
        descriptions = {}
    if not isinstance(descriptions, dict):
        raise BehaviorProposalError("Ollama enrichment state_descriptions must be an object")
    extra = sorted(set(descriptions) - set(OLLAMA_STATES))
    if extra:
        raise BehaviorProposalError("Ollama enrichment state_descriptions contains unknown states: " + ", ".join(extra))
    for state in OLLAMA_STATES:
        value = descriptions.get(state, "")
        if not isinstance(value, str):
            raise BehaviorProposalError(f"Ollama enrichment state description must be a string: {state}")
        if value.strip():
            normalized["state_descriptions"][state] = value.strip()
    rationale = enrichment.get("transition_rationale")
    if rationale is None:
        rationale = {}
    if not isinstance(rationale, dict):
        raise BehaviorProposalError("Ollama enrichment transition_rationale must be an object")
    extra = sorted(set(rationale) - set(OLLAMA_RATIONALE_KEYS))
    if extra:
        raise BehaviorProposalError("Ollama enrichment transition_rationale contains unknown transitions: " + ", ".join(extra))
    for key in OLLAMA_RATIONALE_KEYS:
        value = rationale.get(key, "")
        if not isinstance(value, str):
            raise BehaviorProposalError(f"Ollama enrichment transition_rationale must be a string: {key}")
        if value.strip():
            normalized["transition_rationale"][key] = value.strip()
    actions = enrichment.get("state_actions")
    if actions is None:
        actions = {}
    if not isinstance(actions, dict):
        raise BehaviorProposalError("Ollama enrichment state_actions must be an object")
    extra = sorted(set(actions) - set(OLLAMA_STATES))
    if extra:
        raise BehaviorProposalError("Ollama enrichment state_actions contains unknown states: " + ", ".join(extra))
    for state in OLLAMA_STATES:
        value = actions.get(state, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise BehaviorProposalError(f"Ollama enrichment state_actions must be an array of strings: {state}")
        cleaned = [item.strip() for item in value if item.strip()]
        if cleaned:
            normalized["state_actions"][state] = cleaned
    allowed_numbers = set(_numbers_in_text(json.dumps(asot, sort_keys=True)))
    enrichment_numbers = set(_numbers_in_text(json.dumps(normalized, sort_keys=True)))
    invented = sorted(enrichment_numbers - allowed_numbers)
    if invented:
        raise BehaviorProposalError("Ollama enrichment contains unsupported numerical claims: " + ", ".join(invented))
    executable = [path for path, text in _generated_strings(normalized) if _looks_executable(text)]
    if executable:
        raise BehaviorProposalError("Ollama enrichment contains executable-code-like text: " + ", ".join(executable))
    generated_strings = _generated_strings(normalized)
    if not generated_strings:
        raise BehaviorProposalError("Ollama enrichment contains no substantive model-generated contribution")
    generated_paths = [path for path, _text in generated_strings]
    omitted = [path for path in _requested_enrichment_paths() if not _path_supplied(path, generated_paths)]
    contribution = {
        "enrichment_completeness": "complete" if not omitted else "partial",
        "generated_field_count": len(generated_strings),
        "generated_character_count": sum(len(text) for _path, text in generated_strings),
        "generated_json_paths": generated_paths,
        "omitted_or_empty_json_paths": omitted,
        "deterministic_structure_json_paths": list(DETERMINISTIC_STRUCTURE_JSON_PATHS),
    }
    return normalized, contribution


def _ai_contribution_manifest(metadata: dict[str, Any], normalized: dict[str, Any], contribution: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "de2sim.ai_contribution_manifest.v1",
        "provider": "ollama",
        "model": metadata.get("model", ""),
        "generation_mode": "canonical_asot_scaffold_plus_local_ai_enrichment",
        "enrichment_completeness": contribution["enrichment_completeness"],
        "substantive_ai_contribution_confirmed": contribution["generated_field_count"] > 0,
        "generated_field_count": contribution["generated_field_count"],
        "generated_character_count": contribution["generated_character_count"],
        "generated_json_paths": contribution["generated_json_paths"],
        "omitted_or_empty_json_paths": contribution["omitted_or_empty_json_paths"],
        "deterministic_structure_json_paths": contribution["deterministic_structure_json_paths"],
        "prompt_hash": metadata.get("prompt_hash", ""),
        "original_response_hash": metadata.get("original_response_hash", metadata.get("model_output_hash", "")),
        "repaired_response_hash": metadata.get("repaired_response_hash", ""),
        "normalized_enrichment_hash": _sha256_json(normalized),
        "merged_proposal_hash": metadata.get("validated_proposal_hash", ""),
        "actual_local_model_inference_occurred": bool(metadata.get("actual_local_model_inference_occurred", False)),
        "actual_external_api_call_occurred": bool(metadata.get("actual_external_api_call_occurred", False)),
        "validation_status": metadata.get("validation_status", "passed"),
        "limitations": [
            "Authoritative ASOT behavior structure is deterministic and not model generated.",
            "Missing enrichment fields are not replaced with fabricated narrative text.",
        ],
    }


def _requested_enrichment_paths() -> list[str]:
    paths = ["$.behavior_summary"]
    paths.extend(f"$.state_descriptions.{state}" for state in OLLAMA_STATES)
    paths.extend(f"$.transition_rationale.{key}" for key in OLLAMA_RATIONALE_KEYS)
    paths.extend(f"$.state_actions.{state}" for state in OLLAMA_STATES)
    paths.extend(f"$.{key}[]" for key in ("risks", "assumptions", "limitations"))
    return paths


def _generated_strings(enrichment: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    summary = str(enrichment.get("behavior_summary", "")).strip()
    if summary:
        values.append(("$.behavior_summary", summary))
    for state in OLLAMA_STATES:
        text = str(enrichment.get("state_descriptions", {}).get(state, "")).strip()
        if text:
            values.append((f"$.state_descriptions.{state}", text))
    for key in OLLAMA_RATIONALE_KEYS:
        text = str(enrichment.get("transition_rationale", {}).get(key, "")).strip()
        if text:
            values.append((f"$.transition_rationale.{key}", text))
    for state in OLLAMA_STATES:
        for index, item in enumerate(enrichment.get("state_actions", {}).get(state, [])):
            text = str(item).strip()
            if text:
                values.append((f"$.state_actions.{state}[{index}]", text))
    for key in ("risks", "assumptions", "limitations"):
        for index, item in enumerate(enrichment.get(key, [])):
            text = str(item).strip()
            if text:
                values.append((f"$.{key}[{index}]", text))
    return values


def _path_supplied(requested_path: str, generated_paths: list[str]) -> bool:
    if requested_path.endswith("[]"):
        prefix = requested_path[:-2] + "["
        return any(path.startswith(prefix) for path in generated_paths)
    if requested_path.startswith("$.state_actions."):
        return any(path.startswith(requested_path + "[") for path in generated_paths)
    return requested_path in set(generated_paths)


def _looks_executable(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("<script", "</script", "javascript:", "```", "def ", "class ", "import ", "eval(", "exec("))


def _numbers_in_text(text: str) -> list[str]:
    return re.findall(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?(?![A-Za-z0-9_])", text)


def _canonical_ollama_scaffold(asot: dict[str, Any]) -> dict[str, Any]:
    ids = _required_uas_ids(asot)
    required = ("low_battery_requirement", "max_speed_requirement", "battery_threshold", "max_speed", "battery_capacity", "return_to_base")
    missing = [key for key in required if not ids.get(key)]
    if missing:
        raise BehaviorProposalError("Ollama scaffold cannot be built because required ASOT evidence is missing: " + ", ".join(sorted(missing)))
    evidence_records = _records_by_ids(asot, ids)
    provenance_ids = _source_ids_from_asot_records(evidence_records, asot)
    transitions = [
        {
            "from": "preflight",
            "to": "mission_flight",
            "trigger": "mission_started",
            "guard": "required mission evidence is available",
            "action": "begin mission while respecting documented operating limits, including max_speed",
        },
        {
            "from": "mission_flight",
            "to": "return_to_base",
            "trigger": "battery_threshold_reached",
            "guard": "battery_state <= battery_threshold",
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
        "description": "ASOT-bound low-battery return-to-base behavior with local generative-AI enrichment.",
        "behavior_type": "state_machine",
        "owning_component_id": "",
        "states": ["preflight", "mission_flight", "return_to_base", "landed"],
        "transitions": transitions,
        "triggers": ["mission_started", "battery_threshold_reached", "home_position_reached"],
        "guards": ["required mission evidence is available", "battery_state <= battery_threshold", "return-to-base behavior is active and home arrival is confirmed"],
        "actions": [item["action"] for item in transitions],
        "referenced_requirement_ids": [ids["low_battery_requirement"], ids["max_speed_requirement"]],
        "referenced_parameter_ids": [ids["battery_threshold"], ids["max_speed"], ids["battery_capacity"]],
        "referenced_physical_model_ids": [],
        "referenced_behavior_ids": [ids["return_to_base"]],
        "source_provenance_ids": provenance_ids,
        "confidence": 0.72,
        "assumptions": ["Authoritative behavior structure and ASOT references are computed locally from validated ASOT evidence."],
        "risks": ["Local AI enrichment requires human review before ASOT integration."],
    }


def _records_by_ids(asot: dict[str, Any], ids: dict[str, str]) -> list[dict[str, Any]]:
    wanted = {value for value in ids.values() if value}
    records: list[dict[str, Any]] = []
    for section in ("requirements", "parameters", "behaviors"):
        for item in asot.get(section, []) if isinstance(asot.get(section), list) else []:
            if isinstance(item, dict) and item.get("stable_id") in wanted:
                records.append(item)
    return records


def _source_ids_from_asot_records(records: list[dict[str, Any]], asot: dict[str, Any]) -> list[str]:
    provenance_ids = {str(pid) for record in records for pid in record.get("source_references", []) if str(pid)}
    known = {str(item.get("provenance_id", "")) for item in asot.get("provenance", []) if isinstance(item, dict)}
    if not provenance_ids:
        for record in records:
            rid = str(record.get("stable_id", ""))
            for provenance in asot.get("provenance", []) if isinstance(asot.get("provenance"), list) else []:
                if isinstance(provenance, dict) and rid in (provenance.get("target_entity_ids") or []):
                    provenance_ids.add(str(provenance.get("provenance_id", "")))
    return sorted(pid for pid in provenance_ids if pid in known)


def _required_uas_ids(asot: dict[str, Any]) -> dict[str, str]:
    def text(item: dict[str, Any]) -> str:
        return json.dumps(item, sort_keys=True).lower()
    reqs = [item for item in asot.get("requirements", []) if isinstance(item, dict)]
    params = [item for item in asot.get("parameters", []) if isinstance(item, dict)]
    behaviors = [item for item in asot.get("behaviors", []) if isinstance(item, dict)]
    low = next((item for item in reqs if "battery" in text(item) and "return" in text(item) and "base" in text(item)), {})
    speed_req = next((item for item in reqs if "maximum" in text(item) and "speed" in text(item)), {})
    threshold = next((item for item in params if "battery" in text(item) and "threshold" in text(item)), {})
    speed_param = next((item for item in params if "speed" in text(item) and ("max" in text(item) or "maximum" in text(item))), {})
    capacity = next((item for item in params if "battery" in text(item) and "capacity" in text(item)), {})
    rtb = next((item for item in behaviors if "returntobase" in text(item).replace("_", "").replace("-", "").replace(" ", "") or ("return" in text(item) and "base" in text(item))), {})
    return {
        "low_battery_requirement": str(low.get("stable_id", "")),
        "max_speed_requirement": str(speed_req.get("stable_id", "")),
        "battery_threshold": str(threshold.get("stable_id", "")),
        "max_speed": str(speed_param.get("stable_id", "")),
        "battery_capacity": str(capacity.get("stable_id", "")),
        "return_to_base": str(rtb.get("stable_id", "")),
    }


def _external_generation_summary(audit: dict[str, Any]) -> str:
    return (
        "# External Generation Summary\n\n"
        f"- Evidence status: {audit.get('evidence_status', '')}\n"
        f"- Provider: {audit.get('provider', '')}\n"
        f"- Model: {audit.get('model', '')}\n"
        f"- Proposal: {audit.get('proposal_id', '')} {audit.get('proposal_name', '')}\n"
        f"- Prompt hash: {audit.get('prompt_hash', '')}\n"
        f"- Response hash: {audit.get('response_hash', '')}\n"
    )


def _sha256_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
