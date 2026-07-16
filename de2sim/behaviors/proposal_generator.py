"""Generate and validate Phase 4A behavior proposals."""

from __future__ import annotations

import json
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


def generate_behavior_proposals(asot: dict[str, Any], provider_name: str = "offline") -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = build_behavior_prompt(asot)
    phash = prompt_hash(prompt)
    try:
        provider = get_provider(provider_name)
        raw_proposals = provider.propose(prompt)
    except BehaviorProviderError as exc:
        raise BehaviorProposalError(str(exc)) from exc
    generated_at = utc_now()
    proposals: list[dict[str, Any]] = []
    for raw in raw_proposals:
        raw = dict(raw)
        raw["provider"] = provider.provider_name
        raw["model"] = provider.model
        raw["prompt_hash"] = phash
        raw["generated_at_utc"] = generated_at
        raw["approval_status"] = "proposed"
        raw["generated_by"] = provider.generated_by
        raw["proposal_id"] = deterministic_proposal_id(raw)
        proposal = behavior_proposal_from_dict(raw)
        warnings = sorted(set(proposal.validation_warnings + validate_behavior_proposal(proposal, asot)))
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
        "proposals": proposals,
    }
    prompt_payload = {"schema_version": "de2sim.behavior_prompt.v1", "prompt_hash": phash, "prompt": prompt}
    return prompt_payload, proposal_payload


def write_behavior_generation_outputs(
    asot: dict[str, Any],
    output_dir: Path | str,
    provider_name: str = "offline",
) -> dict[str, Path]:
    from de2sim.visualization.behavior_review import write_behavior_review

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    prompt_payload, proposal_payload = generate_behavior_proposals(asot, provider_name)
    prompt_path = output / "behavior_prompt.json"
    proposals_path = output / "behavior_proposals.json"
    report_path = output / "behavior_generation_report.json"
    review_path = output / "behavior_review.html"
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
            "Phase 4A produces review candidates only.",
            "Offline candidates are deterministic templates, not generative-AI output.",
            "No simulation or executable behavior code is generated.",
        ],
    }
    _write_json(report, report_path)
    write_behavior_review(asot, proposal_payload, review_path)
    return {
        "behavior_prompt": prompt_path,
        "behavior_proposals": proposals_path,
        "behavior_review": review_path,
        "behavior_generation_report": report_path,
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
