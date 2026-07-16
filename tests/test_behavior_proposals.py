from __future__ import annotations

import os
import unittest
from unittest import mock

from de2sim.behaviors.proposal_generator import BehaviorProposalError, generate_behavior_proposals
from de2sim.behaviors.providers import AnthropicProvider, OpenAIProvider
from tests.test_asot_schema import representative_asot


class BehaviorProposalTests(unittest.TestCase):
    def test_offline_proposal_generation_is_labeled_non_generative(self) -> None:
        _prompt, proposals = generate_behavior_proposals(representative_asot().to_dict(), "offline")
        self.assertGreater(len(proposals["proposals"]), 0)
        proposal = proposals["proposals"][0]
        self.assertEqual(proposal["generated_by"], "offline_template")
        self.assertNotEqual(proposal["generated_by"], "ai_provider")
        self.assertEqual(proposal["provider"], "offline")
        self.assertNotIn("10", " ".join(proposal["guards"]))

    def test_mocked_openai_provider_response(self) -> None:
        asot = representative_asot().to_dict()
        component_id = asot["components"][0]["stable_id"]
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            provider = OpenAIProvider(client=lambda _prompt: {"proposals": [{"name": "A", "description": "B", "behavior_type": "state_machine", "owning_component_id": component_id, "states": ["a"], "assumptions": ["x"], "risks": ["y"]}]})
            raw = provider.propose({"components": []})
        self.assertEqual(raw[0]["name"], "A")

    def test_mocked_anthropic_provider_response(self) -> None:
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            provider = AnthropicProvider(client=lambda _prompt: {"proposals": [{"name": "A"}]})
            self.assertEqual(provider.propose({})[0]["name"], "A")

    def test_missing_keys_are_controlled_errors(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(Exception, "OPENAI_API_KEY"):
                OpenAIProvider().propose({})
            with self.assertRaisesRegex(Exception, "ANTHROPIC_API_KEY"):
                AnthropicProvider().propose({})

    def test_unknown_provider_is_controlled_error(self) -> None:
        with self.assertRaises(BehaviorProposalError):
            generate_behavior_proposals(representative_asot().to_dict(), "unknown")


if __name__ == "__main__":
    unittest.main()
