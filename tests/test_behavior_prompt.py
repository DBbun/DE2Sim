from __future__ import annotations

import json
import os
import unittest

from de2sim.behaviors.prompt_builder import build_behavior_prompt, prompt_hash
from tests.test_asot_schema import representative_asot


class BehaviorPromptTests(unittest.TestCase):
    def test_prompt_contains_relevant_asot_evidence_and_constraints(self) -> None:
        prompt = build_behavior_prompt(representative_asot().to_dict())
        text = json.dumps(prompt)
        self.assertIn("components", prompt)
        self.assertIn("requirements", prompt)
        self.assertIn("parameters", prompt)
        self.assertIn("physical_models", prompt)
        self.assertIn("existing_source_derived_behaviors", prompt)
        self.assertIn("provenance_references", prompt)
        self.assertIn("Do not invent unsupported numerical values", text)
        self.assertIn("assumptions", text)
        self.assertEqual(len(prompt_hash(prompt)), 64)

    def test_prompt_excludes_credentials_and_unrelated_files(self) -> None:
        os.environ["OPENAI_API_KEY"] = "secret-test-key"
        prompt_text = json.dumps(build_behavior_prompt(representative_asot().to_dict()))
        self.assertNotIn("secret-test-key", prompt_text)
        self.assertNotIn("paper_to_simulator_builder_v3_4.py", prompt_text)


if __name__ == "__main__":
    unittest.main()
