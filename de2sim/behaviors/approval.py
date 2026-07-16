"""Apply explicit human behavior approval decisions to a new ASOT."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from de2sim.asot.io import write_asot_json
from de2sim.asot.schema import ASOTDocument, ASOTValidationState, Behavior, stable_id, utc_now
from de2sim.asot.validators import validate_asot
from de2sim.behaviors.schema import ALLOWED_APPROVAL_STATUSES, behavior_proposal_from_dict


class BehaviorApprovalError(Exception):
    """Controlled behavior approval failure."""


def apply_behavior_decisions(
    asot: dict[str, Any],
    proposals_payload: dict[str, Any],
    decisions_payload: dict[str, Any],
) -> tuple[ASOTDocument, dict[str, Any], dict[str, Any]]:
    decisions = _decisions(decisions_payload)
    proposals = {str(item.get("proposal_id", "")): item for item in proposals_payload.get("proposals", []) if isinstance(item, dict)}
    seen: set[str] = set()
    normalized_decisions = []
    for decision in decisions:
        proposal_id = str(decision.get("proposal_id", ""))
        status = str(decision.get("approval_status", ""))
        if proposal_id in seen:
            raise BehaviorApprovalError(f"duplicate behavior decision for proposal_id: {proposal_id}")
        if proposal_id not in proposals:
            raise BehaviorApprovalError(f"unknown behavior proposal_id in decision: {proposal_id}")
        if status not in ALLOWED_APPROVAL_STATUSES - {"proposed"}:
            raise BehaviorApprovalError(f"invalid approval decision status for {proposal_id}: {status}")
        seen.add(proposal_id)
        normalized_decisions.append(
            {
                "proposal_id": proposal_id,
                "approval_status": status,
                "reviewer": str(decision.get("reviewer", "")),
                "comment": str(decision.get("comment", "")),
                "decided_at_utc": str(decision.get("decided_at_utc") or utc_now()),
            }
        )

    document = ASOTDocument.from_dict(copy.deepcopy(asot))
    source_behavior_ids = {item.stable_id for item in document.behaviors}
    approved_count = 0
    skipped_count = 0
    for decision in normalized_decisions:
        proposal = behavior_proposal_from_dict(proposals[decision["proposal_id"]])
        if decision["approval_status"] != "approved":
            skipped_count += 1
            continue
        behavior_id = stable_id(
            "behavior",
            {
                "proposal_id": proposal.proposal_id,
                "owning_component_id": proposal.owning_component_id,
                "name": proposal.name,
                "prompt_hash": proposal.prompt_hash,
            },
        )
        if behavior_id in source_behavior_ids:
            raise BehaviorApprovalError(f"approved behavior would overwrite existing source-derived behavior: {behavior_id}")
        behavior = Behavior(
            stable_id=behavior_id,
            name=proposal.name,
            description=proposal.description,
            source_references=proposal.source_provenance_ids,
            traceability_status="precise" if proposal.source_provenance_ids else "not_provided",
            status="approved",
            warnings=proposal.validation_warnings,
            behavior_type=proposal.behavior_type,
            states=proposal.states,
            transitions=proposal.transitions,
            triggers=proposal.triggers,
            guards=proposal.guards,
            actions=proposal.actions,
            owning_component_id=proposal.owning_component_id,
            generated_by=proposal.generated_by,
            approval_status="approved",
            provider=proposal.provider,
            model=proposal.model,
            prompt_hash=proposal.prompt_hash,
            proposal_id=proposal.proposal_id,
            referenced_requirement_ids=proposal.referenced_requirement_ids,
            referenced_parameter_ids=proposal.referenced_parameter_ids,
            referenced_physical_model_ids=proposal.referenced_physical_model_ids,
            source_provenance_ids=proposal.source_provenance_ids,
            approval_decision=decision,
        )
        document.behaviors.append(behavior)
        for component in document.components:
            if component.stable_id == behavior.owning_component_id:
                component.behavior_ids = sorted(set(component.behavior_ids + [behavior.stable_id]))
        approved_count += 1
    validation = validate_asot(document)
    document.validation = ASOTValidationState(errors=validation.errors, warnings=validation.warnings)
    report = {
        "valid": validation.ok,
        "approved_count": approved_count,
        "skipped_count": skipped_count,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "decisions": normalized_decisions,
        "safeguards": [
            "Only approved proposals are copied into asot_with_approved_behaviors.json.",
            "The original asot.json is not modified in place.",
            "Existing source-derived behaviors are preserved.",
            "Generated behavior content is never executed or evaluated.",
        ],
    }
    return document, {"schema_version": "de2sim.behavior_decisions.v1", "decisions": normalized_decisions}, report


def write_behavior_approval_outputs(
    asot: dict[str, Any],
    proposals_payload: dict[str, Any],
    decisions_payload: dict[str, Any],
    output_dir: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    document, decisions, report = apply_behavior_decisions(asot, proposals_payload, decisions_payload)
    decisions_path = output / "behavior_decisions.json"
    asot_path = output / "asot_with_approved_behaviors.json"
    report_path = output / "behavior_approval_report.json"
    _write_json(decisions, decisions_path)
    write_asot_json(document, asot_path)
    _write_json(report, report_path)
    return {
        "behavior_decisions": decisions_path,
        "asot_with_approved_behaviors": asot_path,
        "behavior_approval_report": report_path,
    }


def load_decisions(path: Path | str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BehaviorApprovalError(f"failed to read behavior decisions: {exc}") from exc
    if not isinstance(payload, (dict, list)):
        raise BehaviorApprovalError("behavior decisions JSON must be an object or list")
    return {"decisions": payload} if isinstance(payload, list) else payload


def _decisions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("decisions")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise BehaviorApprovalError("behavior decisions JSON must contain a decisions array")
    return value


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
