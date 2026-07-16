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


def make_demo_inputs(root: Path) -> tuple[Path, Path, Path, Path]:
    engineering = root / "Demo UAS.zip"
    with zipfile.ZipFile(engineering, "w") as archive:
        archive.writestr("requirements/reqs.txt", "low battery return\n")
    behavior_dir = root / "behavior"
    behavior_dir.mkdir()
    asot = approved_asot()
    behavior = asot["behaviors"][0]
    proposal_id = "proposal-low"
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
        "behavior_prompt.json": {"schema_version": "de2sim.behavior_prompt.v1", "prompt_hash": "prompt-abc", "prompt": {"safe": True}},
        "behavior_proposals.json": {"schema_version": "de2sim.behavior_proposals.v1", "asot_id": asot["asot_id"], "provider": "offline", "model": "deterministic-uas-template-v1", "prompt_hash": "prompt-abc", "generated_at_utc": "2026-01-01T00:00:00Z", "proposals": [{**copy.deepcopy(behavior), "proposal_id": proposal_id, "generated_by": "offline_template", "provider": "offline", "model": "deterministic-uas-template-v1", "prompt_hash": "prompt-abc"}]},
        "behavior_decisions.json": {"schema_version": "de2sim.behavior_decisions.v1", "decisions": [{"proposal_id": proposal_id, "approval_status": "approved", "decided_at_utc": "2026-01-01T00:00:00Z"}]},
        "behavior_approval_report.json": {"valid": True, "approved_count": 1, "skipped_count": 0, "errors": [], "warnings": [], "decisions": [{"proposal_id": proposal_id, "approval_status": "approved"}]},
        "asot_with_approved_behaviors.json": asot,
    }.items():
        _write_json(behavior_dir / name, payload)
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
            self.assertIn("Eight-Stage Pipeline", dashboard)
            self.assertNotIn("Seven-Stage Pipeline", dashboard)
            for stage in (
                "Engineering Package",
                "Parsed Artifacts",
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
            for bad in ("src=\"http", "href=\"http", "<link", "eval(", "Function(", "document.write", "fetch("):
                self.assertNotIn(bad, dashboard)
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

    def test_mocked_standard_library_openai_and_anthropic_adapters(self) -> None:
        openai_response = {"output_text": json.dumps({"proposals": [{"name": "OpenAI proposal"}]})}
        anthropic_response = {"content": [{"type": "text", "text": json.dumps({"proposals": [{"name": "Anthropic proposal"}]})}]}
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "secret", "ANTHROPIC_API_KEY": "secret"}):
            with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(openai_response)):
                self.assertEqual(OpenAIProvider().propose({})[0]["name"], "OpenAI proposal")
            with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(anthropic_response)):
                self.assertEqual(AnthropicProvider().propose({})[0]["name"], "Anthropic proposal")


if __name__ == "__main__":
    unittest.main()
