"""Behavior proposal, review, and approval support for DE2Sim Phase 4A."""

from de2sim.behaviors.approval import BehaviorApprovalError, apply_behavior_decisions
from de2sim.behaviors.prompt_builder import build_behavior_prompt
from de2sim.behaviors.proposal_generator import BehaviorProposalError, generate_behavior_proposals
from de2sim.behaviors.providers import BehaviorProviderError, get_provider
from de2sim.behaviors.schema import (
    ALLOWED_APPROVAL_STATUSES,
    BehaviorProposal,
    behavior_proposal_from_dict,
    behavior_proposal_to_dict,
    validate_behavior_proposal,
)

__all__ = [
    "ALLOWED_APPROVAL_STATUSES",
    "BehaviorApprovalError",
    "BehaviorProposal",
    "BehaviorProposalError",
    "BehaviorProviderError",
    "apply_behavior_decisions",
    "behavior_proposal_from_dict",
    "behavior_proposal_to_dict",
    "build_behavior_prompt",
    "generate_behavior_proposals",
    "get_provider",
    "validate_behavior_proposal",
]
