from __future__ import annotations

import unittest

from de2sim.behaviors.schema import behavior_proposal_from_dict, behavior_proposal_to_dict, deterministic_proposal_id, validate_behavior_proposal
from tests.test_asot_schema import representative_asot


class BehaviorSchemaTests(unittest.TestCase):
    def proposal(self) -> dict:
        asot = representative_asot().to_dict()
        payload = {
            "name": "Review Loiter",
            "description": "Candidate only",
            "behavior_type": "state_machine",
            "owning_component_id": asot["components"][0]["stable_id"],
            "states": ["ready", "active"],
            "transitions": [{"from": "ready", "to": "active", "trigger": "review"}],
            "triggers": ["review"],
            "guards": ["human approval"],
            "actions": ["record review"],
            "referenced_requirement_ids": [asot["requirements"][0]["stable_id"]],
            "referenced_parameter_ids": [asot["parameters"][0]["stable_id"]],
            "referenced_physical_model_ids": [asot["physical_models"][0]["stable_id"]],
            "source_provenance_ids": [asot["provenance"][0]["provenance_id"]],
            "provider": "offline",
            "model": "deterministic-template-v1",
            "prompt_hash": "a" * 64,
            "generated_at_utc": "2026-07-16T00:00:00Z",
            "confidence": 0.5,
            "assumptions": ["review required"],
            "risks": ["generic"],
            "generated_by": "offline_template",
        }
        payload["proposal_id"] = deterministic_proposal_id(payload)
        return payload

    def test_deterministic_proposal_ids(self) -> None:
        payload = self.proposal()
        copy = dict(payload)
        self.assertEqual(deterministic_proposal_id(payload), deterministic_proposal_id(copy))

    def test_validation_accepts_supported_references_and_rejects_unknowns(self) -> None:
        asot = representative_asot().to_dict()
        proposal = behavior_proposal_from_dict(self.proposal())
        self.assertEqual(validate_behavior_proposal(proposal, asot), [])
        proposal.owning_component_id = "missing"
        self.assertIn("unknown owning_component_id", "\n".join(validate_behavior_proposal(proposal, asot)))

    def test_schema_round_trip_preserves_required_fields(self) -> None:
        proposal = behavior_proposal_from_dict(self.proposal())
        payload = behavior_proposal_to_dict(proposal)
        self.assertEqual(payload["approval_status"], "proposed")
        self.assertEqual(payload["generated_by"], "offline_template")


if __name__ == "__main__":
    unittest.main()
