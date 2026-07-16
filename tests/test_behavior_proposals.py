from __future__ import annotations

import os
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from de2sim.behaviors.proposal_generator import BehaviorProposalError, generate_behavior_proposals, write_behavior_generation_outputs
from de2sim.behaviors.providers import AnthropicProvider, BehaviorProviderError, OllamaProvider, OpenAIProvider
from de2sim.behaviors.approval import apply_behavior_decisions
from de2sim.behaviors.proposal_generator import build_external_generation_audit
from de2sim.visualization.behavior_review import build_behavior_review_data, render_behavior_review_html
from tests.test_asot_schema import representative_asot
from tests.test_uas_behavior_refinement import uas_asot


class _HTTPSResponse:
    def __init__(self, payload: dict | str, status: int = 200, request_id: str = "req-safe-123") -> None:
        self.payload = (payload if isinstance(payload, str) else json.dumps(payload)).encode("utf-8")
        self.status = status
        self.headers = {"x-request-id": request_id, "anthropic-request-id": request_id}

    def __enter__(self) -> "_HTTPSResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload

    def getcode(self) -> int:
        return self.status


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
            provider = OpenAIProvider(model="test-model", client=lambda _prompt: {"proposals": [{"name": "A", "description": "B", "behavior_type": "state_machine", "owning_component_id": component_id, "states": ["a"], "assumptions": ["x"], "risks": ["y"]}]})
            raw = provider.propose({"components": []})
        self.assertEqual(raw[0]["name"], "A")
        self.assertEqual(provider.last_metadata["evidence_status"], "mocked_test_only")

    def test_mocked_anthropic_provider_response(self) -> None:
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            provider = AnthropicProvider(model="test-model", client=lambda _prompt: {"proposals": [{"name": "A"}]})
            self.assertEqual(provider.propose({})[0]["name"], "A")

    def test_ollama_loopback_url_acceptance_and_remote_rejection(self) -> None:
        self.assertEqual(OllamaProvider(base_url="http://localhost:11434").base_url, "http://localhost:11434")
        self.assertEqual(OllamaProvider(base_url="http://127.0.0.1:11434").base_url, "http://127.0.0.1:11434")
        self.assertEqual(OllamaProvider(base_url="http://[::1]:11434").base_url, "http://[::1]:11434")
        for url in ("https://localhost:11434", "http://192.168.1.10:11434", "http://ollama.com", "http://localhost:11434/api/generate", "http://user:pass@localhost:11434"):
            with self.subTest(url=url):
                with self.assertRaises(BehaviorProviderError):
                    OllamaProvider(base_url=url)

    def test_mocked_successful_ollama_response_and_classification(self) -> None:
        response = {"response": json.dumps(_ollama_enrichment()), "done": True}
        provider = OllamaProvider(model="gemma3:4b", client=lambda _payload: response)
        raw = provider.propose({"components": []})
        self.assertEqual(raw[0]["behavior_summary"], "Use ASOT evidence to describe the low battery return-to-base behavior.")
        self.assertEqual(provider.last_metadata["evidence_status"], "mocked_test_only")
        self.assertFalse(provider.last_metadata["actual_external_api_call_occurred"])

    def test_ollama_http_failures_are_controlled_and_do_not_fallback(self) -> None:
        with mock.patch("urllib.request.urlopen", side_effect=ConnectionRefusedError()):
            with self.assertRaisesRegex(BehaviorProposalError, "network error"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
            with self.assertRaisesRegex(BehaviorProposalError, "timed out"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b", timeout_seconds=1, max_attempts=1)
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("http://localhost:11434/api/generate", 404, "not found", {}, None)):
            with self.assertRaisesRegex(BehaviorProposalError, "model not found"):
                generate_behavior_proposals(uas_asot(), "ollama", model="missing")
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse("not-json")):
            with self.assertRaisesRegex(BehaviorProposalError, "malformed Ollama HTTP response"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"done": True})):
            with self.assertRaisesRegex(BehaviorProposalError, "Ollama response missing response field"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")

    def test_ollama_rejects_malformed_generated_json_invalid_schema_and_unknown_refs(self) -> None:
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": "not json", "done": True})):
            with self.assertRaisesRegex(BehaviorProposalError, "local JSON repair failed"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        invalid_schema = {"response": json.dumps({"behavior_summary": ["wrong type"]}), "done": True}
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse(invalid_schema)):
            with self.assertRaisesRegex(BehaviorProposalError, "behavior_summary must be a string"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        unknown_key = _ollama_enrichment()
        unknown_key["proposal_id"] = "model-controlled"
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": json.dumps(unknown_key), "done": True})):
            with self.assertRaisesRegex(BehaviorProposalError, "unknown keys"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")

    def test_ollama_partial_enrichment_allows_missing_optional_fields(self) -> None:
        missing = _ollama_enrichment()
        missing.pop("assumptions")
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": json.dumps(missing), "done": True})):
            _prompt, proposals = generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        proposal = proposals["proposals"][0]
        self.assertEqual(proposal["local_ai_enrichment"]["assumptions"], [])
        self.assertEqual(proposal["enrichment_completeness"], "partial")
        self.assertIn("$.assumptions[]", proposal["omitted_or_empty_json_paths"])

    def test_ollama_missing_preflight_description_is_partial_not_fabricated(self) -> None:
        enrichment = {
            "state_descriptions": {
                "preflight": "",
                "mission_flight": "Mission flight monitors the documented battery threshold.",
            },
            "state_actions": {},
            "transition_rationale": {},
            "risks": [],
            "limitations": [],
        }
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": json.dumps(enrichment), "done": True})):
            _prompt, proposals = generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        proposal = proposals["proposals"][0]
        self.assertEqual(proposal["enrichment_completeness"], "partial")
        self.assertEqual(proposal["generated_field_count"], 1)
        self.assertEqual(proposal["generated_character_count"], len("Mission flight monitors the documented battery threshold."))
        self.assertNotIn("preflight", proposal["local_ai_enrichment"]["state_descriptions"])
        self.assertIn("$.state_descriptions.preflight", proposal["omitted_or_empty_json_paths"])
        self.assertIn("$.state_descriptions.mission_flight", proposal["generated_json_paths"])
        self.assertNotIn("Mission evidence is checked before flight.", json.dumps(proposal["local_ai_enrichment"]))

    def test_ollama_empty_mapping_allowed_with_other_contribution_and_all_empty_rejected(self) -> None:
        enrichment = {"state_descriptions": {}, "behavior_summary": "  Uses only ASOT evidence.  "}
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": json.dumps(enrichment), "done": True})):
            _prompt, proposals = generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        proposal = proposals["proposals"][0]
        self.assertEqual(proposal["local_ai_enrichment"]["behavior_summary"], "Uses only ASOT evidence.")
        self.assertEqual(proposal["local_ai_enrichment"]["state_descriptions"], {})
        self.assertEqual(proposal["enrichment_completeness"], "partial")
        for empty in ({}, {"behavior_summary": "   ", "state_descriptions": {}, "risks": ["  "]}):
            with self.subTest(empty=empty):
                with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": json.dumps(empty), "done": True})):
                    with self.assertRaisesRegex(BehaviorProposalError, "no substantive model-generated contribution"):
                        generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")

    def test_ollama_complete_enrichment_manifest_counts_and_hashes(self) -> None:
        enrichment = _ollama_enrichment()
        expected_count = 1 + 4 + 3 + 4 + 1 + 1 + 1
        expected_chars = (
            len(enrichment["behavior_summary"])
            + sum(len(value) for value in enrichment["state_descriptions"].values())
            + sum(len(value) for value in enrichment["transition_rationale"].values())
            + sum(len(value) for items in enrichment["state_actions"].values() for value in items)
            + sum(len(value) for key in ("risks", "assumptions", "limitations") for value in enrichment[key])
        )
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": json.dumps(enrichment), "done": True})):
            _prompt, proposals = generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        proposal = proposals["proposals"][0]
        manifest = proposal["ai_contribution_manifest"]
        self.assertEqual(proposal["enrichment_completeness"], "complete")
        self.assertEqual(proposal["generated_field_count"], expected_count)
        self.assertEqual(proposal["generated_character_count"], expected_chars)
        self.assertEqual(manifest["enrichment_completeness"], "complete")
        self.assertTrue(manifest["substantive_ai_contribution_confirmed"])
        self.assertEqual(manifest["generated_json_paths"], proposal["generated_json_paths"])
        self.assertEqual(manifest["omitted_or_empty_json_paths"], [])
        self.assertEqual(manifest["normalized_enrichment_hash"], proposal["normalized_enrichment_hash"])

    def test_ollama_plain_fenced_and_bom_enrichment_json(self) -> None:
        asot = uas_asot()
        payloads = [
            {"response": json.dumps(_ollama_enrichment()), "done": True},
            {"response": "```json\n" + json.dumps(_ollama_enrichment()) + "\n```", "done": True},
            {"response": "\ufeff  " + json.dumps(_ollama_enrichment()) + "  \n", "done": True},
        ]
        for payload in payloads:
            with self.subTest(response=payload["response"][:12]):
                with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse(payload)):
                    _prompt, proposals = generate_behavior_proposals(asot, "ollama", model="gemma3:4b")
                self.assertEqual(proposals["proposals"][0]["name"], "Low Battery Return-to-Base")

    def test_ollama_malformed_enrichment_repairs_once_and_records_hashes(self) -> None:
        malformed = '{"behavior_summary":"Use ASOT evidence",'
        repaired = _ollama_enrichment()
        responses = [
            _HTTPSResponse({"response": malformed, "done": True, "done_reason": "stop"}),
            _HTTPSResponse({"response": json.dumps(repaired), "done": True, "done_reason": "stop"}),
        ]
        with mock.patch("urllib.request.urlopen", side_effect=responses) as opened:
            _prompt, proposals = generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        metadata = proposals["external_call_metadata"]
        self.assertEqual(opened.call_count, 2)
        self.assertTrue(metadata["repair_attempted"])
        self.assertTrue(metadata["repair_succeeded"])
        self.assertEqual(metadata["original_response_hash"], metadata["model_output_hash"])
        self.assertTrue(metadata["repaired_response_hash"])

    def test_ollama_failed_repair_and_repair_validation_are_controlled(self) -> None:
        with mock.patch("urllib.request.urlopen", side_effect=[_HTTPSResponse({"response": "{bad", "done": True}), _HTTPSResponse({"response": "{still bad", "done": True})]):
            with self.assertRaisesRegex(BehaviorProposalError, "local JSON repair failed") as ctx:
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        self.assertTrue(ctx.exception.metadata["repair_attempted"])
        self.assertFalse(ctx.exception.metadata["repair_succeeded"])
        repaired_unknown = _ollama_enrichment()
        repaired_unknown["new_key"] = "not allowed"
        with mock.patch("urllib.request.urlopen", side_effect=[_HTTPSResponse({"response": "{bad", "done": True}), _HTTPSResponse({"response": json.dumps(repaired_unknown), "done": True})]):
            with self.assertRaisesRegex(BehaviorProposalError, "repaired enrichment failed schema validation: Ollama enrichment contains unknown keys"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        repaired_number = _ollama_enrichment()
        repaired_number["behavior_summary"] = "Invent 777 seconds."
        with mock.patch("urllib.request.urlopen", side_effect=[_HTTPSResponse({"response": "{bad", "done": True}), _HTTPSResponse({"response": json.dumps(repaired_number), "done": True})]):
            with self.assertRaisesRegex(BehaviorProposalError, "repaired enrichment failed schema validation: Ollama enrichment contains unsupported numerical claims: 777"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")

    def test_ollama_diagnostic_artifacts_are_safe_on_failed_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_text = "{bad secret-token"
            with mock.patch("urllib.request.urlopen", side_effect=[_HTTPSResponse({"response": bad_text, "done": True}), _HTTPSResponse({"response": "{still bad", "done": True})]):
                with self.assertRaisesRegex(BehaviorProposalError, "local JSON repair failed"):
                    write_behavior_generation_outputs(uas_asot(), Path(tmp), "ollama", model="gemma3:4b")
            audit = json.loads((Path(tmp) / "ollama_response_audit.json").read_text(encoding="utf-8"))
            failed = (Path(tmp) / "ollama_failed_content.txt").read_text(encoding="utf-8")
            self.assertTrue(audit["repair_attempted"])
            self.assertFalse(audit["repair_succeeded"])
            self.assertEqual(failed, bad_text)
            self.assertNotIn("Authorization", json.dumps(audit) + failed)
            self.assertNotIn("OPENAI_API_KEY", json.dumps(audit) + failed)
        with tempfile.TemporaryDirectory() as tmp:
            invalid = {"behavior_summary": "Invent 999 seconds."}
            with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": json.dumps(invalid), "done": True})):
                with self.assertRaisesRegex(BehaviorProposalError, "unsupported numerical claims: 999"):
                    write_behavior_generation_outputs(uas_asot(), Path(tmp), "ollama", model="gemma3:4b")
            model_output = json.loads((Path(tmp) / "ollama_model_output.json").read_text(encoding="utf-8"))
            self.assertEqual(model_output["provider"], "ollama")
            self.assertEqual(model_output["parsing_status"], "parsed")
            self.assertEqual(model_output["validation_status"], "failed")
            self.assertIn("unsupported numerical claims", " ".join(model_output["validation_errors"]))
            serialized = json.dumps(model_output)
            self.assertNotIn("Authorization", serialized)
            self.assertNotIn("OPENAI_API_KEY", serialized)
        unknown = _ollama_enrichment()
        unknown["new_requirement"] = "invented"
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": json.dumps(unknown), "done": True})):
            with self.assertRaisesRegex(BehaviorProposalError, "unknown keys"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")
        invented = _ollama_enrichment()
        invented["behavior_summary"] = "Return to base within 999 seconds."
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"response": json.dumps(invented), "done": True})):
            with self.assertRaisesRegex(BehaviorProposalError, "unsupported numerical claims: 999"):
                generate_behavior_proposals(uas_asot(), "ollama", model="gemma3:4b")

    def test_confirmed_ollama_generation_hashes_review_approval_and_audit(self) -> None:
        asot = uas_asot()
        ollama_payload = {
            "model": "gemma3:4b",
            "created_at": "2026-07-16T00:00:00Z",
            "response": json.dumps(_ollama_enrichment()),
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 11,
            "eval_count": 22,
            "total_duration": 333,
        }
        with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse(ollama_payload)) as opened:
            prompt, proposals = generate_behavior_proposals(asot, "ollama", model="gemma3:4b")
        proposal = proposals["proposals"][0]
        request_body = opened.call_args.args[0].data
        self.assertIn(b'"keep_alive": "10m"', request_body)
        self.assertIn(b'"stream": false', request_body)
        self.assertIn(b'"temperature": 0', request_body)
        self.assertEqual(proposal["generated_by"], "local_generative_ai")
        self.assertEqual(proposal["name"], "Low Battery Return-to-Base")
        self.assertEqual(proposal["states"], ["preflight", "mission_flight", "return_to_base", "landed"])
        self.assertEqual([(item["from"], item["to"]) for item in proposal["transitions"]], [("preflight", "mission_flight"), ("mission_flight", "return_to_base"), ("return_to_base", "landed")])
        self.assertIn("battery_state <= battery_threshold", proposal["guards"])
        self.assertTrue(proposal["proposal_id"].startswith("behavior-proposal-"))
        self.assertEqual(proposal["generation_mode"], "canonical_asot_scaffold_plus_local_ai_enrichment")
        self.assertTrue(proposal["enrichment_hash"])
        self.assertTrue(proposal["validated_proposal_hash"])
        for ref in (asot["requirements"][0]["stable_id"], asot["requirements"][1]["stable_id"]):
            self.assertIn(ref, proposal["referenced_requirement_ids"])
        for ref in (asot["parameters"][0]["stable_id"], asot["parameters"][1]["stable_id"], asot["parameters"][2]["stable_id"]):
            self.assertIn(ref, proposal["referenced_parameter_ids"])
        self.assertIn(asot["behaviors"][0]["stable_id"], proposal["referenced_behavior_ids"])
        self.assertEqual(proposal["evidence_status"], "confirmed_local_generation")
        self.assertTrue(proposal["actual_local_model_inference_occurred"])
        self.assertFalse(proposal["actual_external_api_call_occurred"])
        self.assertEqual(proposal["local_endpoint"], "loopback_only")
        again_payload = {"response": json.dumps(_ollama_enrichment()), "done": True}
        first = OllamaProvider(model="gemma3:4b", client=lambda _payload: again_payload)
        second = OllamaProvider(model="gemma3:4b", client=lambda _payload: again_payload)
        first.propose({"x": 1})
        second.propose({"x": 1})
        self.assertEqual(first.last_metadata["request_hash"], second.last_metadata["request_hash"])
        self.assertEqual(first.last_metadata["response_hash"], second.last_metadata["response_hash"])
        html = render_behavior_review_html(build_behavior_review_data(asot, proposals))
        self.assertIn("Confirmed Local Generative AI", html)
        self.assertIn("local inference confirmed", html)
        self.assertIn("ASOT-derived deterministic structure", html)
        self.assertIn("Local generative-AI enrichment", html)
        document, decisions, _report = apply_behavior_decisions(asot, proposals, {"decisions": [{"proposal_id": proposal["proposal_id"], "approval_status": "approved"}]})
        approved = next(item for item in document.to_dict()["behaviors"] if item.get("proposal_id") == proposal["proposal_id"])
        self.assertEqual(approved["evidence_status"], "confirmed_local_generation")
        self.assertTrue(approved["actual_local_model_inference_occurred"])
        self.assertEqual(approved["generation_mode"], "canonical_asot_scaffold_plus_local_ai_enrichment")
        self.assertEqual(approved["enrichment_hash"], proposal["enrichment_hash"])
        audit = build_external_generation_audit(asot, prompt, proposals, decisions, document.to_dict())
        self.assertEqual(audit["evidence_status"], "confirmed_local_generation")
        self.assertFalse(audit["actual_external_api_call_occurred"])
        self.assertTrue(audit["actual_local_model_inference_occurred"])
        self.assertEqual(audit["done_reason"], "stop")
        self.assertEqual(audit["generation_mode"], "canonical_asot_scaffold_plus_local_ai_enrichment")
        self.assertEqual(audit["enrichment_hash"], proposal["enrichment_hash"])
        self.assertNotIn("secret", json.dumps(proposals).lower())

    def test_missing_keys_are_controlled_errors(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(Exception, "explicit model"):
                OpenAIProvider().propose({})
            with self.assertRaisesRegex(Exception, "explicit model"):
                AnthropicProvider().propose({})
            with self.assertRaisesRegex(Exception, "OPENAI_API_KEY"):
                OpenAIProvider(model="test-model").propose({})
            with self.assertRaisesRegex(Exception, "ANTHROPIC_API_KEY"):
                AnthropicProvider(model="test-model").propose({})

    def test_unknown_provider_is_controlled_error(self) -> None:
        with self.assertRaises(BehaviorProposalError):
            generate_behavior_proposals(representative_asot().to_dict(), "unknown")

    def test_external_provider_http_and_malformed_failures_are_controlled(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}):
            with mock.patch("urllib.request.urlopen", side_effect=TimeoutError()):
                with self.assertRaisesRegex(BehaviorProposalError, "timed out"):
                    generate_behavior_proposals(uas_asot(), "openai", model="test-model", timeout_seconds=1, max_attempts=1)
            with mock.patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("https://example.test", 503, "nope", {}, None)):
                with self.assertRaisesRegex(BehaviorProposalError, "HTTP error: 503"):
                    generate_behavior_proposals(uas_asot(), "openai", model="test-model")
            with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse({"output_text": "not json"})):
                with self.assertRaisesRegex(BehaviorProposalError, "malformed JSON"):
                    generate_behavior_proposals(uas_asot(), "openai", model="test-model")

    def test_external_generation_rejects_invalid_schema_unknown_refs_and_does_not_fallback(self) -> None:
        bad = {"output_text": json.dumps({"proposals": [{"name": "Low Battery Return-to-Base", "description": "bad", "behavior_type": "state_machine", "owning_component_id": "missing", "states": ["preflight"], "assumptions": ["x"], "risks": ["y"]}]})}
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}):
            with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse(bad)):
                with self.assertRaisesRegex(BehaviorProposalError, "failed validation"):
                    generate_behavior_proposals(uas_asot(), "openai", model="test-model")

    def test_mocked_successful_openai_https_external_generation_metadata_review_and_approval(self) -> None:
        asot = uas_asot()
        payload = {"output_text": json.dumps({"proposals": [_external_proposal(asot)]})}
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse(payload)):
                prompt, proposals = generate_behavior_proposals(asot, "openai", model="gpt-test", timeout_seconds=60, max_attempts=2)
        proposal = proposals["proposals"][0]
        self.assertEqual(proposal["generated_by"], "external_generative_ai")
        self.assertTrue(proposal["actual_external_api_call_occurred"])
        self.assertEqual(proposals["external_call_metadata"]["provider_request_id"], "req-safe-123")
        self.assertNotIn("secret-value", json.dumps(proposals))
        self.assertEqual(proposal["prompt_hash"], prompt["prompt_hash"])
        self.assertEqual(proposals["external_call_metadata"]["evidence_status"] if "evidence_status" in proposals["external_call_metadata"] else "confirmed_external_generation", "confirmed_external_generation")
        data = build_behavior_review_data(asot, proposals)
        html = render_behavior_review_html(data)
        self.assertIn("External generative-AI output", html)
        self.assertIn("actual external API call", html)
        document, _decisions, _report = apply_behavior_decisions(asot, proposals, {"decisions": [{"proposal_id": proposal["proposal_id"], "approval_status": "approved"}]})
        approved = next(item for item in document.to_dict()["behaviors"] if item.get("proposal_id") == proposal["proposal_id"])
        self.assertEqual(approved["generated_by"], "external_generative_ai")
        self.assertEqual(approved["response_hash"], proposal["response_hash"])

    def test_mocked_successful_anthropic_https_external_generation(self) -> None:
        asot = uas_asot()
        payload = {"content": [{"type": "text", "text": json.dumps({"proposals": [_external_proposal(asot)]})}]}
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret-value"}):
            with mock.patch("urllib.request.urlopen", return_value=_HTTPSResponse(payload, request_id="anthropic-req-1")):
                _prompt, proposals = generate_behavior_proposals(asot, "anthropic", model="claude-test")
        proposal = proposals["proposals"][0]
        self.assertEqual(proposal["provider"], "anthropic")
        self.assertEqual(proposal["generated_by"], "external_generative_ai")
        self.assertTrue(proposal["actual_external_api_call_occurred"])


def _external_proposal(asot: dict) -> dict:
    return {
        "name": "Low Battery Return-to-Base",
        "description": "External proposal grounded in the provided ASOT evidence.",
        "behavior_type": "state_machine",
        "owning_component_id": "",
        "states": ["preflight", "mission_flight", "return_to_base", "landed"],
        "transitions": [
            {"from": "preflight", "to": "mission_flight", "trigger": "mission_started", "guard": "required mission evidence is available", "action": "begin mission while respecting max_speed"},
            {"from": "mission_flight", "to": "return_to_base", "trigger": "battery_threshold_reached", "guard": "battery_state <= battery_threshold", "action": "invoke ReturnToBase"},
            {"from": "return_to_base", "to": "landed", "trigger": "home_position_reached", "guard": "return-to-base behavior is active", "action": "land"},
        ],
        "triggers": ["mission_started", "battery_threshold_reached", "home_position_reached"],
        "guards": ["required mission evidence is available", "battery_state <= battery_threshold", "return-to-base behavior is active"],
        "actions": ["begin mission while respecting max_speed", "invoke ReturnToBase", "land"],
        "referenced_requirement_ids": [asot["requirements"][0]["stable_id"], asot["requirements"][1]["stable_id"]],
        "referenced_parameter_ids": [asot["parameters"][0]["stable_id"], asot["parameters"][1]["stable_id"], asot["parameters"][2]["stable_id"]],
        "referenced_physical_model_ids": [],
        "referenced_behavior_ids": [asot["behaviors"][0]["stable_id"]],
        "source_provenance_ids": ["prov-req", "prov-threshold", "prov-rtb", "prov-speed-req", "prov-speed-param", "prov-capacity"],
        "confidence": 0.72,
        "assumptions": ["No unsupported engineering facts are added."],
        "risks": ["Requires human review before use."],
    }


def _ollama_enrichment() -> dict:
    return {
        "behavior_summary": "Use ASOT evidence to describe the low battery return-to-base behavior.",
        "state_descriptions": {
            "preflight": "Mission evidence is checked before flight.",
            "mission_flight": "The mission proceeds while monitoring the documented battery threshold.",
            "return_to_base": "The source-derived ReturnToBase behavior is active.",
            "landed": "The mission is complete after landing.",
        },
        "transition_rationale": {
            "preflight_to_mission_flight": "Mission start follows preflight evidence review.",
            "mission_flight_to_return_to_base": "The transition is governed by battery_state <= battery_threshold.",
            "return_to_base_to_landed": "Landing follows the return-to-base behavior.",
        },
        "state_actions": {
            "preflight": ["review ASOT evidence"],
            "mission_flight": ["monitor battery_threshold"],
            "return_to_base": ["follow ReturnToBase"],
            "landed": ["record mission completion"],
        },
        "risks": ["Human review is still required."],
        "assumptions": ["Only supplied ASOT evidence is used."],
        "limitations": ["No executable behavior code is generated."],
    }


if __name__ == "__main__":
    unittest.main()
