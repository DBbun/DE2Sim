"""Provider-neutral behavior proposal schema for DE2Sim Phase 4A."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


ALLOWED_APPROVAL_STATUSES = {"proposed", "approved", "rejected", "needs_revision"}


@dataclass
class BehaviorProposal:
    proposal_id: str
    name: str
    description: str
    behavior_type: str
    owning_component_id: str
    states: list[str] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    guards: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    referenced_requirement_ids: list[str] = field(default_factory=list)
    referenced_parameter_ids: list[str] = field(default_factory=list)
    referenced_physical_model_ids: list[str] = field(default_factory=list)
    source_provenance_ids: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    prompt_hash: str = ""
    generated_at_utc: str = ""
    confidence: float = 0.0
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    approval_status: str = "proposed"
    generated_by: str = ""


def deterministic_proposal_id(payload: dict[str, Any]) -> str:
    normalized = _normalized_identity(payload)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "behavior-proposal-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def behavior_proposal_to_dict(proposal: BehaviorProposal) -> dict[str, Any]:
    return {
        "proposal_id": proposal.proposal_id,
        "name": proposal.name,
        "description": proposal.description,
        "behavior_type": proposal.behavior_type,
        "owning_component_id": proposal.owning_component_id,
        "states": _sorted_texts(proposal.states),
        "transitions": sorted((_canonical(item) for item in proposal.transitions if isinstance(item, dict)), key=lambda item: json.dumps(item, sort_keys=True)),
        "triggers": _sorted_texts(proposal.triggers),
        "guards": _sorted_texts(proposal.guards),
        "actions": _sorted_texts(proposal.actions),
        "referenced_requirement_ids": _sorted_texts(proposal.referenced_requirement_ids),
        "referenced_parameter_ids": _sorted_texts(proposal.referenced_parameter_ids),
        "referenced_physical_model_ids": _sorted_texts(proposal.referenced_physical_model_ids),
        "source_provenance_ids": _sorted_texts(proposal.source_provenance_ids),
        "provider": proposal.provider,
        "model": proposal.model,
        "prompt_hash": proposal.prompt_hash,
        "generated_at_utc": proposal.generated_at_utc,
        "confidence": proposal.confidence,
        "assumptions": _sorted_texts(proposal.assumptions),
        "risks": _sorted_texts(proposal.risks),
        "validation_warnings": _sorted_texts(proposal.validation_warnings),
        "approval_status": proposal.approval_status,
        "generated_by": proposal.generated_by,
    }


def behavior_proposal_from_dict(data: dict[str, Any]) -> BehaviorProposal:
    return BehaviorProposal(
        proposal_id=str(data.get("proposal_id", "")),
        name=str(data.get("name", "")),
        description=str(data.get("description", "")),
        behavior_type=str(data.get("behavior_type", "")),
        owning_component_id=str(data.get("owning_component_id", "")),
        states=_list_text(data.get("states")),
        transitions=[dict(item) for item in data.get("transitions", []) if isinstance(item, dict)],
        triggers=_list_text(data.get("triggers")),
        guards=_list_text(data.get("guards")),
        actions=_list_text(data.get("actions")),
        referenced_requirement_ids=_list_text(data.get("referenced_requirement_ids")),
        referenced_parameter_ids=_list_text(data.get("referenced_parameter_ids")),
        referenced_physical_model_ids=_list_text(data.get("referenced_physical_model_ids")),
        source_provenance_ids=_list_text(data.get("source_provenance_ids")),
        provider=str(data.get("provider", "")),
        model=str(data.get("model", "")),
        prompt_hash=str(data.get("prompt_hash", "")),
        generated_at_utc=str(data.get("generated_at_utc", "")),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        assumptions=_list_text(data.get("assumptions")),
        risks=_list_text(data.get("risks")),
        validation_warnings=_list_text(data.get("validation_warnings")),
        approval_status=str(data.get("approval_status", "proposed")),
        generated_by=str(data.get("generated_by", "")),
    )


def validate_behavior_proposal(proposal: BehaviorProposal | dict[str, Any], asot: dict[str, Any]) -> list[str]:
    item = behavior_proposal_from_dict(proposal) if isinstance(proposal, dict) else proposal
    warnings: list[str] = []
    component_ids = {str(record.get("stable_id", "")) for record in _items(asot.get("components"))}
    requirement_ids = {str(record.get("stable_id", "")) for record in _items(asot.get("requirements"))}
    parameter_ids = {str(record.get("stable_id", "")) for record in _items(asot.get("parameters"))}
    model_ids = {str(record.get("stable_id", "")) for record in _items(asot.get("physical_models"))}
    provenance_ids = {str(record.get("provenance_id", "")) for record in _items(asot.get("provenance"))}
    if not item.proposal_id:
        warnings.append("proposal is missing proposal_id")
    elif item.proposal_id != deterministic_proposal_id(behavior_proposal_to_dict(item)):
        warnings.append("proposal_id is not deterministic for normalized proposal")
    if item.approval_status not in ALLOWED_APPROVAL_STATUSES:
        warnings.append(f"invalid approval_status: {item.approval_status}")
    if item.owning_component_id and item.owning_component_id not in component_ids:
        warnings.append(f"unknown owning_component_id: {item.owning_component_id}")
    if not item.owning_component_id:
        warnings.append("owning_component_id is required and must come from ASOT")
    for ref in item.referenced_requirement_ids:
        if ref not in requirement_ids:
            warnings.append(f"unknown referenced_requirement_id: {ref}")
    for ref in item.referenced_parameter_ids:
        if ref not in parameter_ids:
            warnings.append(f"unknown referenced_parameter_id: {ref}")
    for ref in item.referenced_physical_model_ids:
        if ref not in model_ids:
            warnings.append(f"unknown referenced_physical_model_id: {ref}")
    for ref in item.source_provenance_ids:
        if ref not in provenance_ids:
            warnings.append(f"unknown source_provenance_id: {ref}")
    if not item.assumptions:
        warnings.append("assumptions must be explicitly listed")
    if item.confidence < 0.0 or item.confidence > 1.0:
        warnings.append(f"invalid confidence: {item.confidence}")
    for text in item.guards + item.actions + item.triggers:
        if any(token in text.lower() for token in ("```", "def ", "class ", "import ", "gdscript", "python", "eval(", "exec(")):
            warnings.append("proposal contains executable-code-like text, which is not allowed in Phase 4A")
            break
    return sorted(set(warnings))


def _normalized_identity(payload: dict[str, Any]) -> dict[str, Any]:
    excluded = {"proposal_id", "generated_at_utc", "validation_warnings", "approval_status"}
    return _canonical({key: value for key, value in payload.items() if key not in excluded})


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        items = [_canonical(item) for item in value]
        if all(not isinstance(item, (dict, list)) for item in items):
            return sorted(items, key=lambda item: str(item))
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return "" if value is None else value


def _sorted_texts(values: list[str]) -> list[str]:
    return sorted({str(item).strip() for item in values if str(item).strip()})


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return _sorted_texts([str(item) for item in value])
    if value is None or str(value).strip() == "":
        return []
    return [str(value).strip()]


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
