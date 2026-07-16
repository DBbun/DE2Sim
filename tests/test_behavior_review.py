from __future__ import annotations

import unittest

from de2sim.behaviors.proposal_generator import generate_behavior_proposals
from de2sim.visualization.behavior_review import build_behavior_review_data, render_behavior_review_html
from tests.test_asot_schema import representative_asot


class BehaviorReviewTests(unittest.TestCase):
    def test_review_html_is_standalone_safe_and_contains_decision_tools(self) -> None:
        asot = representative_asot().to_dict()
        _prompt, proposals = generate_behavior_proposals(asot, "offline")
        data = build_behavior_review_data(asot, proposals)
        html = render_behavior_review_html(data)
        self.assertIn("Behavior Proposal Review", html)
        self.assertIn("State-machine diagram", html)
        self.assertIn("Download decisions JSON", html)
        self.assertIn("Approve", html)
        self.assertIn("Reject", html)
        self.assertIn("Needs revision", html)
        self.assertIn("createElementNS", html)
        self.assertNotIn('src="http', html)
        self.assertNotIn("<link", html.lower())
        for unsafe in ("eval(", "exec(", "Function(", "document.write", "innerHTML", "insertAdjacentHTML"):
            self.assertNotIn(unsafe, html)


if __name__ == "__main__":
    unittest.main()
