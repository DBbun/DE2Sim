from __future__ import annotations

import copy
import unittest

from de2sim.behaviors.approval import BehaviorApprovalError, apply_behavior_decisions
from de2sim.behaviors.proposal_generator import generate_behavior_proposals
from tests.test_asot_schema import representative_asot


class BehaviorApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.asot = representative_asot().to_dict()
        _prompt, self.proposals = generate_behavior_proposals(self.asot, "offline")
        self.proposal_id = self.proposals["proposals"][0]["proposal_id"]

    def test_only_approved_behaviors_enter_new_asot_and_source_behaviors_remain(self) -> None:
        original = copy.deepcopy(self.asot)
        document, decisions, report = apply_behavior_decisions(
            self.asot,
            self.proposals,
            {"decisions": [{"proposal_id": self.proposal_id, "approval_status": "approved"}]},
        )
        payload = document.to_dict()
        self.assertEqual(len(payload["behaviors"]), len(original["behaviors"]) + 1)
        self.assertIn(original["behaviors"][0]["stable_id"], {item["stable_id"] for item in payload["behaviors"]})
        self.assertIn("offline_template", {item["generated_by"] for item in payload["behaviors"]})
        self.assertEqual(decisions["decisions"][0]["approval_status"], "approved")
        self.assertTrue(report["valid"])

    def test_reviewer_and_comment_survive_decision_application(self) -> None:
        reviewer = "Uri Kartoun, PhD — Founder, DBbun LLC"
        comment = (
            "Reviewed the local-AI behavior enrichment against the ASOT requirements, "
            "parameters, provenance, state transitions, and low-battery return logic. "
            "Approved for inclusion in the demonstration ASOT."
        )
        document, decisions, report = apply_behavior_decisions(
            self.asot,
            self.proposals,
            {
                "decisions": [
                    {
                        "proposal_id": self.proposal_id,
                        "approval_status": "approved",
                        "reviewer": reviewer,
                        "comment": comment,
                        "decided_at_utc": "2026-07-16T18:35:17Z",
                    }
                ]
            },
        )
        approved = next(item for item in document.to_dict()["behaviors"] if item.get("proposal_id") == self.proposal_id)
        self.assertEqual(decisions["decisions"][0]["reviewer"], reviewer)
        self.assertEqual(decisions["decisions"][0]["comment"], comment)
        self.assertEqual(report["decisions"][0]["reviewer"], reviewer)
        self.assertEqual(report["decisions"][0]["comment"], comment)
        self.assertEqual(approved["approval_decision"]["reviewer"], reviewer)
        self.assertEqual(approved["approval_decision"]["comment"], comment)

    def test_rejected_and_needs_revision_do_not_enter_asot(self) -> None:
        for status in ("rejected", "needs_revision"):
            document, _decisions, report = apply_behavior_decisions(
                self.asot,
                self.proposals,
                {"decisions": [{"proposal_id": self.proposal_id, "approval_status": status}]},
            )
            self.assertEqual(len(document.behaviors), len(self.asot["behaviors"]))
            self.assertEqual(report["skipped_count"], 1)

    def test_unknown_and_duplicate_decisions_are_rejected(self) -> None:
        with self.assertRaisesRegex(BehaviorApprovalError, "unknown"):
            apply_behavior_decisions(self.asot, self.proposals, {"decisions": [{"proposal_id": "missing", "approval_status": "approved"}]})
        with self.assertRaisesRegex(BehaviorApprovalError, "duplicate"):
            apply_behavior_decisions(
                self.asot,
                self.proposals,
                {"decisions": [{"proposal_id": self.proposal_id, "approval_status": "approved"}, {"proposal_id": self.proposal_id, "approval_status": "rejected"}]},
            )


if __name__ == "__main__":
    unittest.main()
