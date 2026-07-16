from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import zipfile

from de2sim.demo import DemoPackageError, build_demo_package
from de2sim.simulation.runner import run_simulation_build
from de2sim.behaviors.providers import AnthropicProvider, OpenAIProvider
from tests.test_simulation_adapter import approved_asot


CHALLENGE_TITLE = "Army Training Verse — Challenge II: Intelligent Simulation Pipeline"
CHALLENGE_INTRODUCTION = (
    "DE2Sim demonstrates an end-to-end Challenge II pipeline that transforms "
    "standards-based digital-engineering artifacts into a validated ASOT, "
    "human-approved AI-assisted behavior, and executable low- and high-fidelity "
    "simulation outputs."
)
REVIEWER = "Uri Kartoun, PhD — Founder, DBbun LLC"
REVIEW_COMMENT = (
    "Reviewed the local-AI behavior enrichment against the ASOT requirements, "
    "parameters, provenance, state transitions, and low-battery return logic. "
    "Approved for inclusion in the demonstration ASOT."
)


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_demo_inputs(root: Path, external_ai: bool = False, local_ai: bool = False, repaired: bool = False) -> tuple[Path, Path, Path, Path]:
    engineering = root / "Demo UAS.zip"
    with zipfile.ZipFile(engineering, "w") as archive:
        archive.writestr("requirements/reqs.txt", "low battery return\n")
    behavior_dir = root / "behavior"
    behavior_dir.mkdir()
    asot = approved_asot()
    behavior = asot["behaviors"][0]
    proposal_id = "proposal-low"
    prompt_hash = "prompt-abc"
    response_hash = "response-abc"
    request_hash = "request-abc"
    enrichment_hash = "enrichment-abc"
    normalized_enrichment_hash = "normalized-enrichment-abc"
    generation_mode = "canonical_asot_scaffold_plus_local_ai_enrichment"
    generated_json_paths = ["$.behavior_summary"]
    omitted_or_empty_json_paths = ["$.state_descriptions.preflight"]
    contribution_manifest = {
        "schema_version": "de2sim.ai_contribution_manifest.v1",
        "provider": "ollama" if local_ai else "",
        "model": "gemma3:4b" if local_ai else "",
        "generation_mode": generation_mode if local_ai else "",
        "enrichment_completeness": "partial" if local_ai else "",
        "substantive_ai_contribution_confirmed": bool(local_ai),
        "generated_field_count": 1 if local_ai else 0,
        "generated_character_count": 8 if local_ai else 0,
        "generated_json_paths": generated_json_paths if local_ai else [],
        "omitted_or_empty_json_paths": omitted_or_empty_json_paths if local_ai else [],
        "deterministic_structure_json_paths": ["$.name", "$.states"] if local_ai else [],
        "prompt_hash": prompt_hash if local_ai else "",
        "original_response_hash": response_hash if local_ai else "",
        "repaired_response_hash": "",
        "normalized_enrichment_hash": normalized_enrichment_hash if local_ai else "",
        "merged_proposal_hash": "validated-abc" if local_ai else "",
        "actual_local_model_inference_occurred": bool(local_ai),
        "actual_external_api_call_occurred": False,
        "validation_status": "passed" if local_ai else "",
        "limitations": [],
    }
    if external_ai or local_ai:
        behavior["generated_by"] = "local_generative_ai" if local_ai else "external_generative_ai"
        behavior["provider"] = "ollama" if local_ai else "openai"
        behavior["model"] = "gemma3:4b" if local_ai else "gpt-test"
        behavior["prompt_hash"] = prompt_hash
        behavior["response_hash"] = response_hash
        behavior["request_hash"] = request_hash
        behavior["actual_external_api_call_occurred"] = external_ai
        behavior["actual_local_model_inference_occurred"] = local_ai
        behavior["evidence_status"] = "confirmed_local_generation" if local_ai else ""
        behavior["local_endpoint"] = "loopback_only" if local_ai else ""
        behavior["generation_mode"] = generation_mode if local_ai else ""
        behavior["enrichment_hash"] = enrichment_hash if local_ai else ""
        behavior["enrichment_completeness"] = "partial" if local_ai else ""
        behavior["generated_field_count"] = 1 if local_ai else 0
        behavior["generated_character_count"] = 8 if local_ai else 0
        behavior["generated_json_paths"] = generated_json_paths if local_ai else []
        behavior["omitted_or_empty_json_paths"] = omitted_or_empty_json_paths if local_ai else []
        behavior["deterministic_structure_json_paths"] = ["$.name", "$.states"] if local_ai else []
        behavior["normalized_enrichment_hash"] = normalized_enrichment_hash if local_ai else ""
        behavior["ai_contribution_manifest"] = contribution_manifest if local_ai else {}
        behavior["validated_proposal_hash"] = "validated-abc" if local_ai else ""
        behavior["local_ai_enrichment"] = {"behavior_summary": "enriched"} if local_ai else {}
        behavior["proposal_id"] = proposal_id
    for name, payload in {
        "package_manifest.json": {"schema_version": "pkg", "source_package_sha256": "abc"},
        "parsed_artifacts.json": {"schema_version": "parsed", "records": []},
        "asot.json": {**copy.deepcopy(asot), "behaviors": [copy.deepcopy(asot["behaviors"][1])]},
        "asot_validation.json": {"errors": [], "warnings": []},
        "provenance_manifest.json": {
            "schema_version": "prov",
            "source_files": [{"source_relative_path": "requirements/reqs.txt", "role": "requirements", "size_bytes": 1, "sha256": "x", "parser_status": "parsed", "referenced_entity_ids": ["requirement-low"], "warnings": []}],
            "provenance_records": asot["provenance"],
        },
        "traceability_report.json": {"valid": True, "coverage_summary": {"traceability_percentage": 100.0}},
        "behavior_prompt.json": {"schema_version": "de2sim.behavior_prompt.v1", "prompt_hash": prompt_hash, "prompt": {"safe": True}},
        "behavior_proposals.json": {"schema_version": "de2sim.behavior_proposals.v1", "asot_id": asot["asot_id"], "provider": "ollama" if local_ai else "openai" if external_ai else "offline", "model": "gemma3:4b" if local_ai else "gpt-test" if external_ai else "deterministic-uas-template-v1", "prompt_hash": prompt_hash, "generated_at_utc": "2026-01-01T00:00:00Z", "external_call_metadata": {"actual_external_api_call_occurred": external_ai, "actual_local_model_inference_occurred": local_ai, "request_hash": request_hash, "response_hash": response_hash, "local_endpoint": "loopback_only" if local_ai else "", "evidence_status": "confirmed_local_generation" if local_ai else "", "generation_mode": generation_mode if local_ai else "", "enrichment_hash": enrichment_hash if local_ai else "", "enrichment_completeness": "partial" if local_ai else "", "generated_field_count": 1 if local_ai else 0, "generated_character_count": 8 if local_ai else 0, "generated_json_paths": generated_json_paths if local_ai else [], "omitted_or_empty_json_paths": omitted_or_empty_json_paths if local_ai else [], "normalized_enrichment_hash": normalized_enrichment_hash if local_ai else "", "ai_contribution_manifest": contribution_manifest if local_ai else {}} if (external_ai or local_ai) else {}, "proposals": [{**copy.deepcopy(behavior), "proposal_id": proposal_id, "generated_by": "local_generative_ai" if local_ai else "external_generative_ai" if external_ai else "offline_template", "provider": "ollama" if local_ai else "openai" if external_ai else "offline", "model": "gemma3:4b" if local_ai else "gpt-test" if external_ai else "deterministic-uas-template-v1", "prompt_hash": prompt_hash, "response_hash": response_hash if (external_ai or local_ai) else "", "request_hash": request_hash if (external_ai or local_ai) else "", "actual_external_api_call_occurred": external_ai, "actual_local_model_inference_occurred": local_ai, "evidence_status": "confirmed_local_generation" if local_ai else "", "local_endpoint": "loopback_only" if local_ai else "", "generation_mode": generation_mode if local_ai else "", "enrichment_hash": enrichment_hash if local_ai else "", "enrichment_completeness": "partial" if local_ai else "", "generated_field_count": 1 if local_ai else 0, "generated_character_count": 8 if local_ai else 0, "generated_json_paths": generated_json_paths if local_ai else [], "omitted_or_empty_json_paths": omitted_or_empty_json_paths if local_ai else [], "normalized_enrichment_hash": normalized_enrichment_hash if local_ai else "", "ai_contribution_manifest": contribution_manifest if local_ai else {}, "validated_proposal_hash": "validated-abc" if local_ai else ""}]},
        "behavior_decisions.json": {"schema_version": "de2sim.behavior_decisions.v1", "decisions": [{"proposal_id": proposal_id, "approval_status": "approved", "reviewer": REVIEWER, "comment": REVIEW_COMMENT, "decided_at_utc": "2026-01-01T00:00:00Z"}]},
        "behavior_approval_report.json": {"valid": True, "approved_count": 1, "skipped_count": 0, "errors": [], "warnings": [], "decisions": [{"proposal_id": proposal_id, "approval_status": "approved", "reviewer": REVIEWER, "comment": REVIEW_COMMENT, "decided_at_utc": "2026-01-01T00:00:00Z"}]},
        "asot_with_approved_behaviors.json": asot,
    }.items():
        _write_json(behavior_dir / name, payload)
    if external_ai or local_ai:
        _write_json(
            behavior_dir / "external_generation_audit.json",
            {
                "schema_version": "de2sim.external_generation_audit.v1",
                "provider": "ollama" if local_ai else "openai",
                "model": "gemma3:4b" if local_ai else "gpt-test",
                "generated_by": "local_generative_ai" if local_ai else "external_generative_ai",
                "evidence_status": "confirmed_local_generation" if local_ai else "confirmed_external_generation",
                "actual_external_api_call_occurred": external_ai,
                "actual_local_model_inference_occurred": local_ai,
                "local_endpoint": "loopback_only" if local_ai else "",
                "repair_attempted": repaired,
                "repair_succeeded": repaired,
                "prompt_hash": prompt_hash,
                "request_hash": request_hash,
                "response_hash": response_hash,
                "validated_proposal_hash": "validated-abc",
                "enrichment_hash": enrichment_hash if local_ai else "",
                "enrichment_completeness": "partial" if local_ai else "",
                "generated_field_count": 1 if local_ai else 0,
                "generated_character_count": 8 if local_ai else 0,
                "generated_json_paths": generated_json_paths if local_ai else [],
                "omitted_or_empty_json_paths": omitted_or_empty_json_paths if local_ai else [],
                "normalized_enrichment_hash": normalized_enrichment_hash if local_ai else "",
                "ai_contribution_manifest": contribution_manifest if local_ai else {},
                "generation_mode": generation_mode if local_ai else "",
                "provider_request_id": "req-safe",
                "attempt_count": 1,
                "validation_status": "passed",
                "proposal_id": proposal_id,
                "proposal_name": "Low Battery Return-to-Base",
                "approval_status": "approved",
                "approved_behavior_id": behavior["stable_id"],
                "related_asot_ids": {"asot_id": asot["asot_id"], "approved_asot_id": asot["asot_id"]},
                "limitations": [],
            },
        )
        if local_ai:
            _write_json(behavior_dir / "ai_contribution_manifest.json", contribution_manifest)
            _write_json(
                behavior_dir / "ollama_model_output.json",
                {
                    "schema_version": "de2sim.ollama_model_output.v1",
                    "provider": "ollama",
                    "model": "gemma3:4b",
                    "parsing_status": "parsed",
                    "validation_status": "passed",
                    "normalized_parsed_enrichment": {"behavior_summary": "enriched"},
                    "model_output_hash": response_hash,
                    "validation_errors": [],
                },
            )
        (behavior_dir / "external_generation_summary.md").write_text("# External Generation Summary\n", encoding="utf-8")
    (behavior_dir / "asot_summary.md").write_text("# ASOT Summary\n", encoding="utf-8")
    (behavior_dir / "traceability_report.md").write_text("# Traceability\n", encoding="utf-8")
    (behavior_dir / "behavior_review.html").write_text("<!doctype html><title>review</title>", encoding="utf-8")
    simulation_dir = root / "simulation"
    run_simulation_build(behavior_dir / "asot_with_approved_behaviors.json", simulation_dir)
    return engineering, behavior_dir / "asot_with_approved_behaviors.json", behavior_dir, simulation_dir


class DemoPackageTests(unittest.TestCase):
    def test_demo_package_artifacts_links_manifest_and_zip_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engineering, approved, behavior_dir, simulation_dir = make_demo_inputs(root)
            out1 = root / "out1"
            out2 = root / "out2"
            first = build_demo_package(engineering, approved, behavior_dir, simulation_dir, out1, "DE2Sim v0.6.0-phase6a", "Ran 139 tests OK")
            second = build_demo_package(engineering, approved, behavior_dir, simulation_dir, out2, "DE2Sim v0.6.0-phase6a", "Ran 139 tests OK")
            self.assertEqual(first["zip"].read_bytes(), second["zip"].read_bytes())
            dashboard = first["dashboard"].read_text(encoding="utf-8")
            self.assertIn("Nine-Stage Pipeline", dashboard)
            self.assertIn(CHALLENGE_TITLE, dashboard)
            self.assertIn(CHALLENGE_INTRODUCTION, dashboard)
            self.assertNotIn("Eight-Stage Pipeline", dashboard)
            for stage in (
                "Engineering Package",
                "Parsed Artifacts",
                "CAD Geometry Transformation",
                "ASOT",
                "Provenance and Traceability",
                "Behavior Proposal",
                "Human Approval",
                "Executable Simulation",
                "Requirement Evidence",
            ):
                self.assertIn(stage, dashboard)
            self.assertIn("grid-template-columns:repeat(4,minmax(150px,1fr))", dashboard)
            self.assertIn("@media(max-width:980px){.pipeline{grid-template-columns:repeat(2,minmax(150px,1fr))}}", dashboard)
            self.assertIn("@media(max-width:560px){.pipeline{grid-template-columns:1fr}", dashboard)
            self.assertIn("ASOT Validation", dashboard)
            self.assertIn("PASSED", dashboard)
            self.assertIn("artifacts/asot_validation.json", dashboard)
            self.assertIn("Provenance Coverage", dashboard)
            self.assertIn("Coverage: ", dashboard)
            self.assertIn("artifacts/provenance_manifest.json", dashboard)
            self.assertIn("artifacts/traceability_report.json", dashboard)
            self.assertIn("Human Approval", dashboard)
            self.assertIn("Approved proposal ID", dashboard)
            self.assertIn("Approved behavior stable ID", dashboard)
            self.assertIn("Approval status", dashboard)
            self.assertIn("Decision timestamp", dashboard)
            self.assertIn(REVIEWER, dashboard)
            self.assertIn(REVIEW_COMMENT, dashboard)
            self.assertIn("2026-01-01T00:00:00Z", dashboard)
            self.assertIn("Low fidelity", dashboard)
            self.assertIn("High fidelity", dashboard)
            self.assertIn("Low Battery Return", dashboard)
            self.assertIn("Maximum Speed", dashboard)
            self.assertIn('"status": "PASS"', dashboard)
            self.assertIn("max observed speed", dashboard)
            self.assertIn("requirement_id", dashboard)
            self.assertIn("Known Limitations", dashboard)
            for limitation in (
                "demonstrative point-mass simulation",
                "no flight certification",
                "no authoritative vehicle validation",
                "no Godot export",
                "current proposal is an offline deterministic template",
            ):
                self.assertIn(limitation, dashboard)
            self.assertNotIn("telemetry_indices", dashboard)
            self.assertNotIn("JSON.stringify(data.requirements", dashboard)
            self.assertIn("viewers/simulation_viewer.html", dashboard)
            self.assertNotIn("C:\\", dashboard)
            for bad_claim in ("Challenge I:", "Challenge I -", "Challenge I —", "Challenge III", "Challenge IV", "Army approval", "government approval", "external approval", "independent approval"):
                self.assertNotIn(bad_claim, dashboard)
            for bad in ("src=\"http", "href=\"http", "<link", "eval(", "Function(", "document.write", "fetch("):
                self.assertNotIn(bad, dashboard)
            for rel in ("reports/challenge_alignment.md", "reports/technical_summary.md", "reports/demo_script.md"):
                text = (first["package_root"] / rel).read_text(encoding="utf-8")
                self.assertIn(CHALLENGE_TITLE, text)
                self.assertIn(CHALLENGE_INTRODUCTION, text)
                for bad_claim in ("Challenge I:", "Challenge I -", "Challenge I —", "Challenge III", "Challenge IV", "Army approval", "government approval", "external approval", "independent approval"):
                    self.assertNotIn(bad_claim, text)
            technical = (first["package_root"] / "reports" / "technical_summary.md").read_text(encoding="utf-8")
            demo_script = (first["package_root"] / "reports" / "demo_script.md").read_text(encoding="utf-8")
            self.assertIn(REVIEWER, technical)
            self.assertIn(REVIEW_COMMENT, technical)
            self.assertIn(REVIEWER, demo_script)
            self.assertIn(REVIEW_COMMENT, demo_script)
            packaged_decisions = json.loads((first["package_root"] / "artifacts" / "behavior_decisions.json").read_text(encoding="utf-8"))
            packaged_report = json.loads((first["package_root"] / "reports" / "behavior_approval_report.json").read_text(encoding="utf-8"))
            self.assertEqual(packaged_decisions["decisions"][0]["reviewer"], REVIEWER)
            self.assertEqual(packaged_decisions["decisions"][0]["comment"], REVIEW_COMMENT)
            self.assertEqual(packaged_report["decisions"][0]["reviewer"], REVIEWER)
            self.assertEqual(packaged_report["decisions"][0]["comment"], REVIEW_COMMENT)
            source_asot = json.loads((behavior_dir / "asot_with_approved_behaviors.json").read_text(encoding="utf-8"))
            packaged_asot = json.loads((first["package_root"] / "artifacts" / "asot_with_approved_behaviors.json").read_text(encoding="utf-8"))
            for section in ("components", "requirements", "interfaces", "parameters", "physical_models", "behaviors", "geometry"):
                self.assertEqual([item["stable_id"] for item in packaged_asot.get(section, [])], [item["stable_id"] for item in source_asot.get(section, [])])
            for rel in ("telemetry_low.csv", "telemetry_high.csv", "requirements_evaluation.json"):
                self.assertEqual((first["package_root"] / "artifacts" / rel).read_bytes(), (simulation_dir / rel).read_bytes())
            manifest = json.loads(first["manifest"].read_text(encoding="utf-8"))
            paths = [item["relative_path"] for item in manifest["files"]]
            self.assertEqual(paths, sorted(paths))
            self.assertIn("demo_dashboard.html", paths)
            self.assertIn("viewers/asot_traceability_viewer.html", paths)
            with zipfile.ZipFile(first["zip"]) as archive:
                names = archive.namelist()
            self.assertEqual(names, sorted(names))
            self.assertTrue(all(name.startswith("DE2Sim_Submission_Demo/") and ".." not in name for name in names))

    def test_missing_artifact_controlled_error_and_ai_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engineering, approved, behavior_dir, simulation_dir = make_demo_inputs(root)
            (behavior_dir / "behavior_decisions.json").unlink()
            with self.assertRaisesRegex(DemoPackageError, "missing behavior artifact"):
                build_demo_package(engineering, approved, behavior_dir, simulation_dir, root / "out", "DE2Sim v0.6.0-phase6a")

    def test_external_ai_audit_drives_package_classification_and_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engineering, approved, behavior_dir, simulation_dir = make_demo_inputs(root, external_ai=True)
            result = build_demo_package(engineering, approved, behavior_dir, simulation_dir, root / "out", "DE2Sim v0.6.1-phase6b")
            evidence = json.loads(result["ai_generation_evidence"].read_text(encoding="utf-8"))
            dashboard = result["dashboard"].read_text(encoding="utf-8")
            self.assertEqual(evidence["evidence_status"], "confirmed_external_generation")
            self.assertTrue(evidence["actual_external_api_call_occurred"])
            self.assertEqual(evidence["generated_by"], ["external_generative_ai"])
            self.assertEqual(evidence["proposal_id"], "proposal-low")
            self.assertIn("Confirmed External Generative AI", dashboard)
            self.assertIn("gpt-test", dashboard)
            self.assertIn("response-abc", dashboard)
            self.assertNotIn("current proposal is an offline deterministic template", dashboard)

    def test_local_ai_audit_drives_package_classification_and_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engineering, approved, behavior_dir, simulation_dir = make_demo_inputs(root, local_ai=True)
            result = build_demo_package(engineering, approved, behavior_dir, simulation_dir, root / "out", "DE2Sim v0.6.2-phase6b-local")
            evidence = json.loads(result["ai_generation_evidence"].read_text(encoding="utf-8"))
            dashboard = result["dashboard"].read_text(encoding="utf-8")
            technical = (result["package_root"] / "reports" / "technical_summary.md").read_text(encoding="utf-8")
            demo_script = (result["package_root"] / "reports" / "demo_script.md").read_text(encoding="utf-8")
            self.assertEqual(evidence["evidence_status"], "confirmed_local_generation")
            self.assertTrue(evidence["actual_local_model_inference_occurred"])
            self.assertFalse(evidence["actual_external_api_call_occurred"])
            self.assertEqual(evidence["provider"], "ollama")
            self.assertIn("Confirmed Local Generative AI", dashboard)
            self.assertIn("ASOT-bound behavior structure with local AI enrichment", dashboard)
            self.assertNotIn("current proposal is an offline deterministic template", dashboard)
            self.assertIn("authoritative behavior structure is ASOT-derived and deterministic", dashboard)
            self.assertIn("behavioral narrative enrichment was generated locally with Ollama", dashboard)
            self.assertIn("local AI enrichment may be partial", dashboard)
            self.assertIn("no external AI service was used", dashboard)
            self.assertIn("Offline template mode is non-generative; this package uses confirmed local generative AI through Ollama with human approval.", dashboard)
            self.assertIn("Offline template mode is non-generative; this package uses confirmed local generative AI through Ollama with human approval.", technical)
            self.assertNotIn("offline behavior proposals are deterministic templates rather than confirmed external generative-AI output", technical)
            self.assertIn("narrative enrichment was generated locally with Ollama", demo_script)
            self.assertIn('"provider": "Ollama"', dashboard)
            self.assertIn('"model": "gemma3:4b"', dashboard)
            self.assertIn('"generation_mode": "canonical_asot_scaffold_plus_local_ai_enrichment"', dashboard)
            self.assertEqual(evidence["generation_mode"], "canonical_asot_scaffold_plus_local_ai_enrichment")
            self.assertEqual(evidence["enrichment_hash"], "enrichment-abc")
            self.assertEqual(evidence["enrichment_completeness"], "partial")
            self.assertEqual(evidence["generated_field_count"], 1)
            self.assertIn("$.behavior_summary", evidence["generated_json_paths"])
            self.assertIn("$.state_descriptions.preflight", evidence["omitted_or_empty_json_paths"])
            self.assertIn("enrichment completeness", dashboard)
            self.assertIn('"generated_field_count": 1', dashboard)
            self.assertIn('"actual_local_model_inference_occurred": true', dashboard)
            self.assertIn('"actual_external_api_call_occurred": false', dashboard)
            self.assertIn("human approval status", dashboard)

    def test_local_ai_dashboard_discloses_json_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engineering, approved, behavior_dir, simulation_dir = make_demo_inputs(root, local_ai=True, repaired=True)
            result = build_demo_package(engineering, approved, behavior_dir, simulation_dir, root / "out", "DE2Sim v0.6.4-phase6b-local")
            evidence = json.loads(result["ai_generation_evidence"].read_text(encoding="utf-8"))
            dashboard = result["dashboard"].read_text(encoding="utf-8")
            self.assertTrue(evidence["repair_attempted"])
            self.assertIn('"repair_attempted": true', dashboard)
            self.assertIn("Local JSON syntax repair", dashboard)

    def test_mocked_standard_library_openai_and_anthropic_adapters(self) -> None:
        openai_response = {"output_text": json.dumps({"proposals": [{"name": "OpenAI proposal"}]})}
        anthropic_response = {"content": [{"type": "text", "text": json.dumps({"proposals": [{"name": "Anthropic proposal"}]})}]}
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "secret", "ANTHROPIC_API_KEY": "secret"}):
            with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(openai_response)):
                self.assertEqual(OpenAIProvider(model="gpt-test").propose({})[0]["name"], "OpenAI proposal")
            with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(anthropic_response)):
                self.assertEqual(AnthropicProvider(model="claude-test").propose({})[0]["name"], "Anthropic proposal")


if __name__ == "__main__":
    unittest.main()
