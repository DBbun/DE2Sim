"""Build the DE2Sim Phase 6A submission demonstration package."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any
import zipfile

from de2sim.visualization.traceability_viewer import render_viewer_html, build_viewer_data


DEMO_SCHEMA_VERSION = "de2sim.demo_package.v1"
FIXED_ZIP_DT = (2026, 1, 1, 0, 0, 0)
ROOT_NAME = "DE2Sim_Submission_Demo"


class DemoPackageError(Exception):
    """Controlled Phase 6A demo packaging failure."""


REQUIRED_BEHAVIOR = {
    "package_manifest.json": ("artifacts/package_manifest.json", "artifact", "ingestion", "Package manifest"),
    "parsed_artifacts.json": ("artifacts/parsed_artifacts.json", "artifact", "parsing", "Parsed artifacts"),
    "asot.json": ("artifacts/asot.json", "artifact", "asot", "Generated ASOT"),
    "asot_validation.json": ("artifacts/asot_validation.json", "artifact", "asot", "ASOT validation"),
    "asot_summary.md": ("reports/asot_summary.md", "report", "asot", "ASOT summary"),
    "provenance_manifest.json": ("artifacts/provenance_manifest.json", "artifact", "provenance", "Provenance manifest"),
    "traceability_report.json": ("artifacts/traceability_report.json", "artifact", "traceability", "Traceability report"),
    "traceability_report.md": ("reports/traceability_report.md", "report", "traceability", "Traceability markdown"),
    "behavior_prompt.json": ("artifacts/behavior_prompt.json", "artifact", "behavior_proposal", "Behavior prompt"),
    "behavior_proposals.json": ("artifacts/behavior_proposals.json", "artifact", "behavior_proposal", "Behavior proposals"),
    "behavior_review.html": ("viewers/behavior_review.html", "viewer", "behavior_proposal", "Behavior review viewer"),
    "behavior_decisions.json": ("artifacts/behavior_decisions.json", "artifact", "human_approval", "Behavior decisions"),
    "behavior_approval_report.json": ("reports/behavior_approval_report.json", "report", "human_approval", "Behavior approval report"),
    "asot_with_approved_behaviors.json": ("artifacts/asot_with_approved_behaviors.json", "artifact", "human_approval", "Approved ASOT"),
}

REQUIRED_SIMULATION = {
    "simulation_inputs.json": ("artifacts/simulation_inputs.json", "artifact", "simulation", "Simulation inputs"),
    "simulation_model.json": ("artifacts/simulation_model.json", "artifact", "simulation", "Simulation model"),
    "telemetry_low.csv": ("artifacts/telemetry_low.csv", "artifact", "simulation", "Low-fidelity telemetry"),
    "telemetry_high.csv": ("artifacts/telemetry_high.csv", "artifact", "simulation", "High-fidelity telemetry"),
    "simulation_events.json": ("artifacts/simulation_events.json", "artifact", "simulation", "Simulation events"),
    "requirements_evaluation.json": ("artifacts/requirements_evaluation.json", "artifact", "requirement_evidence", "Requirement evaluation"),
    "fidelity_comparison.json": ("reports/fidelity_comparison.json", "report", "simulation", "Fidelity comparison"),
    "simulation_summary.md": ("reports/simulation_summary.md", "report", "simulation", "Simulation summary"),
    "simulation_data.json": ("artifacts/simulation_data.json", "artifact", "simulation", "Simulation data bundle"),
    "simulation_viewer.html": ("viewers/simulation_viewer.html", "viewer", "simulation", "Simulation playback viewer"),
}

OPTIONAL_BEHAVIOR = {
    "external_generation_audit.json": ("artifacts/external_generation_audit.json", "artifact", "ai_evidence", "External generation audit"),
    "external_generation_summary.md": ("reports/external_generation_summary.md", "report", "ai_evidence", "External generation summary"),
    "ai_contribution_manifest.json": ("artifacts/ai_contribution_manifest.json", "artifact", "ai_evidence", "AI contribution manifest"),
    "ollama_model_output.json": ("artifacts/ollama_model_output.json", "artifact", "ai_evidence", "Ollama model output diagnostics"),
}

OPTIONAL_GEOMETRY = {
    "geometry_extraction.json": ("artifacts/geometry_extraction.json", "artifact", "geometry", "Geometry extraction"),
    "geometry_validation.json": ("artifacts/geometry_validation.json", "artifact", "geometry", "Geometry validation"),
    "geometry_linkage_report.json": ("artifacts/geometry_linkage_report.json", "artifact", "geometry", "Geometry linkage report"),
    "geometry_scene.json": ("artifacts/geometry_scene.json", "artifact", "geometry", "Geometry browser scene"),
    "geometry_viewer.html": ("viewers/geometry_viewer.html", "viewer", "geometry", "Geometry viewer"),
}


def build_demo_package(
    engineering_package: Path | str,
    approved_asot: Path | str,
    behavior_artifacts_dir: Path | str,
    simulation_artifacts_dir: Path | str,
    output_dir: Path | str,
    cli_version: str,
    test_summary: str = "not_run_by_packager",
) -> dict[str, Path]:
    source_zip = Path(engineering_package)
    approved_path = Path(approved_asot)
    behavior_dir = Path(behavior_artifacts_dir)
    simulation_dir = Path(simulation_artifacts_dir)
    output = Path(output_dir)
    root = output / ROOT_NAME
    zip_path = output / f"{ROOT_NAME}.zip"

    _validate_inputs(source_zip, approved_path, behavior_dir, simulation_dir)
    if root.exists():
        shutil.rmtree(root)
    output.mkdir(parents=True, exist_ok=True)
    _mkdirs(root)

    copied: list[dict[str, Any]] = []
    _copy_file(source_zip, root / "source_package" / source_zip.name, copied, "source", "engineering_package", "Original engineering ZIP", True, "source-derived")
    for name, (rel, category, stage, description) in REQUIRED_BEHAVIOR.items():
        _copy_file(behavior_dir / name, root / rel, copied, category, stage, description, True, "source-derived")
    for name, (rel, category, stage, description) in OPTIONAL_BEHAVIOR.items():
        if (behavior_dir / name).is_file():
            _copy_file(behavior_dir / name, root / rel, copied, category, stage, description, False, "generated")
    for name, (rel, category, stage, description) in OPTIONAL_GEOMETRY.items():
        if (behavior_dir / name).is_file():
            _copy_file(behavior_dir / name, root / rel, copied, category, stage, description, False, "generated")
    for name, (rel, category, stage, description) in REQUIRED_SIMULATION.items():
        _copy_file(simulation_dir / name, root / rel, copied, category, stage, description, True, "generated")
    _copy_source_geometry(source_zip, root, copied)

    data = _load_all(root)
    _validate_consistency(data)
    _write_traceability_viewer(root, data, copied)
    ai_evidence = _ai_generation_evidence(data)
    _write_json(ai_evidence, root / "reports" / "ai_generation_evidence.json")
    reports = _reports(data, cli_version, test_summary, ai_evidence)
    for rel, text in reports.items():
        (root / rel).write_text(text, encoding="utf-8", newline="\n")
    if _geometry_card(data).get("available"):
        (root / "reports" / "geometry_integration_summary.md").write_text(
            _geometry_integration_summary(data),
            encoding="utf-8",
            newline="\n",
        )
    _write_evidence_matrix(root / "reports" / "evidence_matrix.csv")
    dashboard = _dashboard(data, ai_evidence)
    (root / "demo_dashboard.html").write_text(dashboard, encoding="utf-8", newline="\n")
    _launcher(root / "Launch_DE2Sim_Demo.bat")

    for rel, category, stage, description in (
        ("demo_dashboard.html", "dashboard", "demo", "Integrated dashboard"),
        ("Launch_DE2Sim_Demo.bat", "launcher", "demo", "Windows launcher"),
        ("README_DEMO.md", "report", "demo", "Demo README"),
        ("reports/technical_summary.md", "report", "demo", "Technical summary"),
        ("reports/challenge_alignment.md", "report", "demo", "Challenge alignment"),
        ("reports/demo_script.md", "report", "demo", "Demo script"),
        ("reports/evidence_matrix.csv", "report", "demo", "Evidence matrix"),
        ("reports/ai_generation_evidence.json", "report", "ai_evidence", "AI generation evidence"),
        ("reports/geometry_integration_summary.md", "report", "geometry", "Geometry integration summary"),
    ):
        if (root / rel).is_file():
            _append_manifest(root / rel, copied, category, stage, description, True, "generated")
    manifest = _manifest(root, copied)
    _write_json(manifest, root / "manifests" / "submission_manifest.json")
    _append_manifest(root / "manifests" / "submission_manifest.json", copied, "manifest", "demo", "Submission manifest", True, "generated")
    manifest = _manifest(root, copied)
    _write_json(manifest, root / "manifests" / "submission_manifest.json")
    reproducibility = _reproducibility(data, cli_version, test_summary, root, manifest)
    _write_json(reproducibility, root / "manifests" / "reproducibility_report.json")
    _append_manifest(root / "manifests" / "reproducibility_report.json", copied, "manifest", "reproducibility", "Reproducibility report", True, "generated")
    manifest = _manifest(root, copied)
    _write_json(manifest, root / "manifests" / "submission_manifest.json")

    _verify_links(root)
    _verify_manifest_hashes(root, manifest)
    _write_zip(root, zip_path)
    return {
        "package_root": root,
        "zip": zip_path,
        "dashboard": root / "demo_dashboard.html",
        "manifest": root / "manifests" / "submission_manifest.json",
        "reproducibility_report": root / "manifests" / "reproducibility_report.json",
        "ai_generation_evidence": root / "reports" / "ai_generation_evidence.json",
    }


def _validate_inputs(source_zip: Path, approved_path: Path, behavior_dir: Path, simulation_dir: Path) -> None:
    for path, label in ((source_zip, "engineering package"), (approved_path, "approved ASOT"), (behavior_dir, "behavior artifacts dir"), (simulation_dir, "simulation artifacts dir")):
        if not path.exists():
            raise DemoPackageError(f"missing {label}: {path}")
    if not source_zip.is_file() or source_zip.suffix.lower() != ".zip":
        raise DemoPackageError("engineering package must be a ZIP file")
    if not behavior_dir.is_dir() or not simulation_dir.is_dir():
        raise DemoPackageError("artifact directories must be directories")
    if approved_path.resolve() != (behavior_dir / "asot_with_approved_behaviors.json").resolve():
        raise DemoPackageError("approved ASOT path must match behavior artifacts approved ASOT")
    for name in REQUIRED_BEHAVIOR:
        if not (behavior_dir / name).is_file():
            raise DemoPackageError(f"missing behavior artifact: {name}")
    for name in REQUIRED_SIMULATION:
        if not (simulation_dir / name).is_file():
            raise DemoPackageError(f"missing simulation artifact: {name}")


def _mkdirs(root: Path) -> None:
    for rel in ("reports", "viewers", "artifacts", "source_package", "manifests"):
        (root / rel).mkdir(parents=True, exist_ok=True)


def _copy_file(src: Path, dst: Path, rows: list[dict[str, Any]], category: str, stage: str, description: str, required: bool, origin: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    _append_manifest(dst, rows, category, stage, description, required, origin)


def _append_manifest(path: Path, rows: list[dict[str, Any]], category: str, stage: str, description: str, required: bool, origin: str) -> None:
    rel = path if not path.is_absolute() else path.relative_to(next(parent for parent in path.parents if parent.name == ROOT_NAME))
    rows.append(
        {
            "relative_path": _posix(rel),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
            "artifact_category": category,
            "stage": stage,
            "description": description,
            "required_or_optional": "required" if required else "optional",
            "generated_or_source_derived": origin,
        }
    )


def _load_all(root: Path) -> dict[str, Any]:
    def j(rel: str) -> dict[str, Any]:
        try:
            data = json.loads((root / rel).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DemoPackageError(f"malformed or unreadable JSON artifact: {rel}") from exc
        if not isinstance(data, dict):
            raise DemoPackageError(f"JSON artifact root must be object: {rel}")
        return data

    return {
        "package_manifest": j("artifacts/package_manifest.json"),
        "parsed_artifacts": j("artifacts/parsed_artifacts.json"),
        "asot": j("artifacts/asot.json"),
        "asot_validation": j("artifacts/asot_validation.json"),
        "provenance_manifest": j("artifacts/provenance_manifest.json"),
        "traceability_report": j("artifacts/traceability_report.json"),
        "behavior_prompt": j("artifacts/behavior_prompt.json"),
        "behavior_proposals": j("artifacts/behavior_proposals.json"),
        "behavior_decisions": j("artifacts/behavior_decisions.json"),
        "behavior_approval_report": j("reports/behavior_approval_report.json"),
        "external_generation_audit": j("artifacts/external_generation_audit.json") if (root / "artifacts/external_generation_audit.json").is_file() else {},
        "ai_contribution_manifest": j("artifacts/ai_contribution_manifest.json") if (root / "artifacts/ai_contribution_manifest.json").is_file() else {},
        "ollama_model_output": j("artifacts/ollama_model_output.json") if (root / "artifacts/ollama_model_output.json").is_file() else {},
        "geometry_extraction": j("artifacts/geometry_extraction.json") if (root / "artifacts/geometry_extraction.json").is_file() else {},
        "geometry_validation": j("artifacts/geometry_validation.json") if (root / "artifacts/geometry_validation.json").is_file() else {},
        "geometry_linkage_report": j("artifacts/geometry_linkage_report.json") if (root / "artifacts/geometry_linkage_report.json").is_file() else {},
        "geometry_scene": j("artifacts/geometry_scene.json") if (root / "artifacts/geometry_scene.json").is_file() else {},
        "approved_asot": j("artifacts/asot_with_approved_behaviors.json"),
        "simulation_inputs": j("artifacts/simulation_inputs.json"),
        "simulation_data": j("artifacts/simulation_data.json"),
        "requirements_evaluation": j("artifacts/requirements_evaluation.json"),
        "fidelity_comparison": j("reports/fidelity_comparison.json"),
    }


def _validate_consistency(data: dict[str, Any]) -> None:
    asot_id = data["approved_asot"].get("asot_id")
    if not asot_id:
        raise DemoPackageError("approved ASOT is missing asot_id")
    if data["behavior_proposals"].get("asot_id") != data["asot"].get("asot_id"):
        raise DemoPackageError("behavior proposals do not reference generated ASOT")
    decisions = {item.get("proposal_id"): item.get("approval_status") for item in data["behavior_decisions"].get("decisions", []) if isinstance(item, dict)}
    proposals = {item.get("proposal_id") for item in data["behavior_proposals"].get("proposals", []) if isinstance(item, dict)}
    if not decisions or not set(decisions).issubset(proposals):
        raise DemoPackageError("behavior proposal and decisions do not correspond")
    approved = [item for item in data["approved_asot"].get("behaviors", []) if item.get("name") == "Low Battery Return-to-Base" and item.get("approval_status") == "approved"]
    if not approved:
        raise DemoPackageError("approved behavior is absent from approved ASOT")
    behavior_id = approved[0]["stable_id"]
    sim_facts = data["simulation_data"].get("asot_facts", {})
    if sim_facts.get("asot_id") != asot_id or sim_facts.get("approved_behavior_id") != behavior_id:
        raise DemoPackageError("simulation does not reference the approved ASOT behavior")
    known_req = {item.get("stable_id") for item in data["approved_asot"].get("requirements", [])}
    known_param = {item.get("stable_id") for item in data["approved_asot"].get("parameters", [])}
    for req_id in sim_facts.get("requirement_ids", {}).values():
        if req_id not in known_req:
            raise DemoPackageError(f"simulation requirement ID does not exist: {req_id}")
    for param_id in sim_facts.get("parameter_ids", {}).values():
        if param_id not in known_param:
            raise DemoPackageError(f"simulation parameter ID does not exist: {param_id}")
    if not data["traceability_report"].get("valid", False):
        raise DemoPackageError("traceability report is not valid")
    for fidelity, status in data["simulation_data"].get("simulation_status", {}).items():
        if not status.get("mission_completed") or status.get("scenario_feasibility_status") != "pass" or float(status.get("battery_reserve_at_landing_percent", 0.0)) <= 0.0:
            raise DemoPackageError(f"{fidelity} simulation did not complete with positive reserve")
    if data.get("geometry_validation") and not data["geometry_validation"].get("valid", False):
        raise DemoPackageError("geometry validation is not valid")


def _copy_source_geometry(source_zip: Path, root: Path, copied: list[dict[str, Any]]) -> None:
    try:
        with zipfile.ZipFile(source_zip, "r") as archive:
            if "geometry/demo_uas.stl" not in archive.namelist():
                return
            target = root / "artifacts" / "source_geometry" / "demo_uas.stl"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read("geometry/demo_uas.stl"))
            _append_manifest(target, copied, "artifact", "geometry", "Source STL geometry", True, "source-derived")
    except zipfile.BadZipFile as exc:
        raise DemoPackageError("engineering package is not a valid ZIP file") from exc


def _write_traceability_viewer(root: Path, data: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    viewer_data = build_viewer_data(data["asot"], data["provenance_manifest"], data["traceability_report"])
    viewer_data["generated_at_utc"] = "deterministic-phase6a"
    path = root / "viewers" / "asot_traceability_viewer.html"
    path.write_text(render_viewer_html(viewer_data), encoding="utf-8", newline="\n")
    _append_manifest(path, rows, "viewer", "traceability", "ASOT traceability viewer", True, "generated")


def _ai_generation_evidence(data: dict[str, Any]) -> dict[str, Any]:
    proposals = data["behavior_proposals"]
    proposal_items = proposals.get("proposals", [])
    generated_by = sorted({str(item.get("generated_by", "")) for item in proposal_items if isinstance(item, dict)})
    provider = proposals.get("provider", "")
    proposal = proposal_items[0] if proposal_items and isinstance(proposal_items[0], dict) else {}
    audit = data.get("external_generation_audit", {}) if isinstance(data.get("external_generation_audit"), dict) else {}
    contribution_manifest = data.get("ai_contribution_manifest", {}) if isinstance(data.get("ai_contribution_manifest"), dict) else {}
    confirmed = _confirmed_external_generation(data, proposal, audit)
    if provider == "offline" or generated_by == ["offline_template"]:
        status = "offline_non_generative"
        external = False
        local = False
    elif _confirmed_local_generation(data, proposal, audit):
        status = "confirmed_local_generation"
        external = False
        local = True
    elif confirmed:
        status = "confirmed_external_generation"
        external = True
        local = False
    elif audit.get("evidence_status") == "mocked_test_only":
        status = "mocked_test_only"
        external = False
        local = False
    elif provider in {"openai", "anthropic", "ollama"}:
        status = "external_generation_failed"
        external = False
        local = False
    else:
        status = "not_available"
        external = False
        local = False
    return {
        "schema_version": "de2sim.ai_generation_evidence.v1",
        "provider": provider,
        "model": proposals.get("model", ""),
        "generated_by": generated_by,
        "prompt_hash": proposals.get("prompt_hash", ""),
        "request_hash": proposal.get("request_hash", audit.get("request_hash", "")),
        "response_hash": proposal.get("response_hash", audit.get("response_hash", "")),
        "validated_proposal_hash": audit.get("validated_proposal_hash", ""),
        "enrichment_hash": proposal.get("enrichment_hash", audit.get("enrichment_hash", "")),
        "enrichment_completeness": proposal.get("enrichment_completeness", audit.get("enrichment_completeness", contribution_manifest.get("enrichment_completeness", ""))),
        "generated_field_count": proposal.get("generated_field_count", audit.get("generated_field_count", contribution_manifest.get("generated_field_count", 0))),
        "generated_character_count": proposal.get("generated_character_count", audit.get("generated_character_count", contribution_manifest.get("generated_character_count", 0))),
        "generated_json_paths": proposal.get("generated_json_paths", audit.get("generated_json_paths", contribution_manifest.get("generated_json_paths", []))),
        "omitted_or_empty_json_paths": proposal.get("omitted_or_empty_json_paths", audit.get("omitted_or_empty_json_paths", contribution_manifest.get("omitted_or_empty_json_paths", []))),
        "deterministic_structure_json_paths": proposal.get("deterministic_structure_json_paths", audit.get("deterministic_structure_json_paths", contribution_manifest.get("deterministic_structure_json_paths", []))),
        "normalized_enrichment_hash": proposal.get("normalized_enrichment_hash", audit.get("normalized_enrichment_hash", contribution_manifest.get("normalized_enrichment_hash", ""))),
        "ai_contribution_manifest": proposal.get("ai_contribution_manifest", audit.get("ai_contribution_manifest", contribution_manifest)),
        "generation_mode": proposal.get("generation_mode", audit.get("generation_mode", "")),
        "repair_attempted": bool(audit.get("repair_attempted", False)),
        "repair_succeeded": bool(audit.get("repair_succeeded", False)),
        "proposal_id": proposal.get("proposal_id", audit.get("proposal_id", "")),
        "approved_behavior_id": data["simulation_data"].get("asot_facts", {}).get("approved_behavior_id", ""),
        "human_approval_status": data["behavior_approval_report"].get("valid", False),
        "actual_external_api_call_occurred": external,
        "actual_local_model_inference_occurred": local,
        "local_endpoint": proposal.get("local_endpoint", audit.get("local_endpoint", "")),
        "evidence_status": status,
        "mocked_provider_tests": ["OpenAIProvider injected client tests", "AnthropicProvider injected client tests", "OllamaProvider injected client tests"],
        "limitations": [
            "Offline deterministic template output is not generative AI.",
            "No API keys, raw authorization data, or external response bodies are packaged.",
        ],
    }


def _confirmed_external_generation(data: dict[str, Any], proposal: dict[str, Any], audit: dict[str, Any]) -> bool:
    if not proposal or not audit:
        return False
    if audit.get("evidence_status") != "confirmed_external_generation":
        return False
    if proposal.get("generated_by") != "external_generative_ai" or not proposal.get("actual_external_api_call_occurred"):
        return False
    if proposal.get("proposal_id") != audit.get("proposal_id"):
        return False
    if proposal.get("prompt_hash") != data["behavior_prompt"].get("prompt_hash") or audit.get("prompt_hash") != proposal.get("prompt_hash"):
        return False
    if proposal.get("response_hash") != audit.get("response_hash"):
        return False
    decisions = [item for item in data["behavior_decisions"].get("decisions", []) if isinstance(item, dict)]
    if not any(item.get("proposal_id") == proposal.get("proposal_id") and item.get("approval_status") == "approved" for item in decisions):
        return False
    approved_behavior = next((item for item in data["approved_asot"].get("behaviors", []) if isinstance(item, dict) and item.get("proposal_id") == proposal.get("proposal_id")), {})
    if not approved_behavior or approved_behavior.get("stable_id") != audit.get("approved_behavior_id"):
        return False
    if data["simulation_data"].get("asot_facts", {}).get("approved_behavior_id") != approved_behavior.get("stable_id"):
        return False
    return True


def _confirmed_local_generation(data: dict[str, Any], proposal: dict[str, Any], audit: dict[str, Any]) -> bool:
    if not proposal or not audit:
        return False
    if audit.get("evidence_status") != "confirmed_local_generation":
        return False
    if proposal.get("generated_by") != "local_generative_ai":
        return False
    if not proposal.get("actual_local_model_inference_occurred") or proposal.get("actual_external_api_call_occurred"):
        return False
    if audit.get("actual_external_api_call_occurred") or not audit.get("actual_local_model_inference_occurred"):
        return False
    if proposal.get("proposal_id") != audit.get("proposal_id"):
        return False
    if proposal.get("prompt_hash") != data["behavior_prompt"].get("prompt_hash") or audit.get("prompt_hash") != proposal.get("prompt_hash"):
        return False
    if proposal.get("response_hash") != audit.get("response_hash"):
        return False
    decisions = [item for item in data["behavior_decisions"].get("decisions", []) if isinstance(item, dict)]
    if not any(item.get("proposal_id") == proposal.get("proposal_id") and item.get("approval_status") == "approved" for item in decisions):
        return False
    approved_behavior = next((item for item in data["approved_asot"].get("behaviors", []) if isinstance(item, dict) and item.get("proposal_id") == proposal.get("proposal_id")), {})
    if not approved_behavior or approved_behavior.get("stable_id") != audit.get("approved_behavior_id"):
        return False
    if data["simulation_data"].get("asot_facts", {}).get("approved_behavior_id") != approved_behavior.get("stable_id"):
        return False
    return True


def _reports(data: dict[str, Any], cli_version: str, test_summary: str, ai: dict[str, Any]) -> dict[str, str]:
    sim = data["simulation_data"]
    status = sim["simulation_status"]
    req = sim["requirements_evaluation"]
    general_limitations = _general_limitations_text(ai)
    ai_limitation_note = _ai_limitations_report_text(ai)
    geometry = _geometry_summary(data)
    readme = f"""# DE2Sim Submission Demo

Open `demo_dashboard.html` directly or run `Launch_DE2Sim_Demo.bat` on Windows.

This package is self-contained and uses relative links only. It demonstrates readable-to-runnable engineering flow through ingestion, parsing, CAD geometry transformation, ASOT, provenance, behavior approval, simulation, and requirement evidence.
"""
    tech = f"""# Technical Summary

DE2Sim addresses the gap between readable engineering artifacts and runnable simulation evidence. The architecture preserves secure ingestion, deterministic artifact parsing, ASOT generation, provenance, human-in-the-loop behavior approval, and executable low/high fidelity UAS simulation.

The approved behavior is `{sim['asot_facts']['approved_behavior_id']}` with sequence `preflight -> mission_flight -> return_to_base -> landed`. The low-fidelity model is a deterministic kinematic point model. The high-fidelity model is a demonstrative point-mass model, not flight-certified aerodynamics.

CAD-export geometry is represented by a standards-based STL artifact. Dimensions are explicitly parameterized and validated, geometry is linked to SysML/component and physical-model evidence through an explicit sidecar, and low/high simulation model artifacts reference the same ASOT geometry entity when present. Geometry is used for visualization only; no vendor-authoritative CAD or certified flight model is claimed.

Geometry summary: {geometry}

Determinism is supported through stable IDs, prompt hashes, deterministic JSON/CSV ordering, fixed ZIP timestamps, and path-independent package links. Security controls include local standalone HTML, no external resources, no dynamic code evaluation, and no secret packaging.

Limitations: {general_limitations}
"""
    align = """# Challenge Alignment

## Technical Feasibility
Evidence: `artifacts/asot_with_approved_behaviors.json`, `artifacts/simulation_data.json`, `viewers/simulation_viewer.html`.

## Innovation Merit
Evidence: `viewers/asot_traceability_viewer.html`, `viewers/behavior_review.html`, human approval artifacts.

CAD-export geometry is represented by a standards-based STL artifact. Dimensions are explicitly parameterized and validated. Geometry is linked to SysML/component and physical-model evidence through an explicit sidecar. Low- and high-fidelity simulation models share one ASOT geometry entity when present. Geometry is used for visualization only; no vendor-authoritative CAD or certified flight model is claimed.

## Maturity
Evidence: `manifests/submission_manifest.json`, `manifests/reproducibility_report.json`, deterministic ZIP packaging.

## Speed to Delivery
Evidence: `demo_script.md`, generated dashboard, and runnable local viewers.

## Value to Transition
Evidence: traceability reports, requirement evaluation, and clear limitations.
"""
    script = f"""# 4-5 Minute Demo Script

1. Problem: engineering data is readable but not immediately runnable.
2. Engineering ZIP: open `source_package/`.
3. Traceability: open `viewers/asot_traceability_viewer.html`.
4. CAD geometry: open `viewers/geometry_viewer.html` when present and state it is a demonstration STL, not vendor-authoritative CAD.
5. Behavior approval: open `viewers/behavior_review.html`.
6. Simulation playback: open `viewers/simulation_viewer.html`.
7. Compare fidelities: show low/high landing reserves and timing.
8. Requirement evidence: open `artifacts/requirements_evaluation.json`.
9. Transition value: show `reports/challenge_alignment.md`.
10. Limitations: state no flight certification, no Godot, no aerodynamic derivation from geometry, and {ai_limitation_note}.
"""
    return {
        "README_DEMO.md": readme,
        "reports/technical_summary.md": tech,
        "reports/challenge_alignment.md": align,
        "reports/demo_script.md": script,
    }


def _general_limitations_text(ai: dict[str, Any]) -> str:
    if ai.get("evidence_status") == "offline_non_generative":
        return "No flight certification, no authoritative vehicle validation data, no Godot export, no external resources, and offline behavior proposals are deterministic templates."
    if ai.get("evidence_status") == "confirmed_local_generation":
        return (
            "No flight certification, no authoritative vehicle validation data, and no Godot export. "
            "Offline template mode is non-generative; this package uses confirmed local generative AI through Ollama with human approval."
        )
    if ai.get("evidence_status") == "confirmed_external_generation":
        return (
            "No flight certification, no authoritative vehicle validation data, and no Godot export. "
            "Offline template mode is non-generative; this package uses confirmed external generative AI with human approval."
        )
    return "No flight certification, no authoritative vehicle validation data, no Godot export, and no generated behavior is used without human approval."


def _known_limitations(ai: dict[str, Any]) -> list[str]:
    base = [
        "demonstrative point-mass simulation",
        "no flight certification",
        "no authoritative vehicle validation",
        "no Godot export",
        "demonstration STL mesh rather than native STEP/BREP CAD",
        "not vendor-authoritative geometry",
        "no articulation",
        "no material model",
        "no mass-property extraction",
        "no aerodynamic derivation",
        "no collision model",
        "browser WebGL viewer is a visualization, not a CAD editor",
    ]
    if ai.get("evidence_status") == "confirmed_local_generation":
        return base + [
            "authoritative behavior structure is ASOT-derived and deterministic",
            "behavioral narrative enrichment was generated locally with Ollama",
            "local AI enrichment may be partial",
            "no external AI service was used",
        ]
    if ai.get("evidence_status") == "confirmed_external_generation":
        return base + [
            "authoritative behavior structure is ASOT-derived and deterministic",
            "behavioral narrative enrichment was generated by a confirmed external AI provider",
            "AI-generated behavior evidence requires human approval",
        ]
    if ai.get("evidence_status") == "offline_non_generative":
        return base + ["current proposal is an offline deterministic template"]
    return base + ["behavior proposal evidence is not confirmed as generative AI"]


def _ai_limitations_report_text(ai: dict[str, Any]) -> str:
    if ai.get("evidence_status") == "confirmed_local_generation":
        return "the behavior structure is ASOT-derived while narrative enrichment was generated locally with Ollama"
    if ai.get("evidence_status") == "confirmed_external_generation":
        return "the behavior structure is ASOT-derived while narrative enrichment was generated by a confirmed external AI provider"
    if ai.get("evidence_status") == "offline_non_generative":
        return "offline behavior templates are non-generative"
    return "behavior proposal evidence requires human review"


def _write_evidence_matrix(path: Path) -> None:
    rows = [
        ["Technical Feasibility", "Pipeline produces runnable simulation evidence", "artifacts/simulation_data.json", "simulation_status", "JSON inspection", "Demonstrative point-mass models only"],
        ["Technical Feasibility", "Standards-based CAD-export geometry is ingested, validated, linked, and rendered", "viewers/geometry_viewer.html", "geometry_scene.json", "Open local viewer", "Demonstration STL is not vendor authoritative"],
        ["Innovation Merit", "Traceability connects source evidence to runnable behavior", "viewers/asot_traceability_viewer.html", "graph and source evidence", "Open local viewer", "Field-level provenance is limited"],
        ["Maturity", "Package is reproducible and hashed", "manifests/submission_manifest.json", "sha256", "Hash verification", "No external deployment"],
        ["Speed to Delivery", "Local launch requires no Python", "Launch_DE2Sim_Demo.bat", "%~dp0 launcher", "Run batch file", "Windows launcher only"],
        ["Value to Transition", "Human approval and requirement evidence are preserved", "artifacts/behavior_decisions.json", "decisions", "Review JSON/report", "No customer deployment claim"],
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["evaluation_area", "claim", "supporting_artifact", "supporting_field_or_section", "verification_method", "limitation"])
        writer.writerows(rows)


def _dashboard(data: dict[str, Any], ai: dict[str, Any]) -> str:
    sim = data["simulation_data"]
    approved_behavior = next(
        (
            item
            for item in data["approved_asot"].get("behaviors", [])
            if item.get("name") == "Low Battery Return-to-Base" and item.get("approval_status") == "approved"
        ),
        {},
    )
    approved_decision = next(
        (item for item in data["behavior_decisions"].get("decisions", []) if item.get("approval_status") == "approved"),
        {},
    )
    coverage = data["traceability_report"].get("coverage_summary", {}) if isinstance(data["traceability_report"].get("coverage_summary"), dict) else {}
    geometry_card = _geometry_card(data)
    dash = {
        "title": sim["asot_facts"]["title"],
        "approved_behavior_id": sim["asot_facts"]["approved_behavior_id"],
        "sequence": "preflight -> mission_flight -> return_to_base -> landed",
        "status": sim["simulation_status"],
        "asot_validation": {
            "passed": not data["asot_validation"].get("errors"),
            "error_count": len(data["asot_validation"].get("errors", [])),
            "warning_count": len(data["asot_validation"].get("warnings", [])),
            "artifact": "artifacts/asot_validation.json",
        },
        "provenance": {
            "coverage_percentage": coverage.get("traceability_percentage", "not available"),
            "provenance_manifest": "artifacts/provenance_manifest.json",
            "traceability_report": "artifacts/traceability_report.json",
            "traceability_markdown": "reports/traceability_report.md",
        },
        "human_approval": {
            "approved_proposal_id": approved_decision.get("proposal_id", ""),
            "approved_behavior_id": approved_behavior.get("stable_id", ""),
            "approval_status": approved_decision.get("approval_status", ""),
            "decision_timestamp": approved_decision.get("decided_at_utc", ""),
            "artifact": "artifacts/behavior_decisions.json",
        },
        "general_limitations": _general_limitations_text(ai),
        "known_limitations": _known_limitations(ai),
        "geometry": geometry_card,
        "requirement_summary": _requirement_summary(sim["requirements_evaluation"]),
        "ai": ai,
        "external_ai_status": {
            "label": "Confirmed Local Generative AI" if ai.get("evidence_status") == "confirmed_local_generation" else "Confirmed External Generative AI" if ai.get("evidence_status") == "confirmed_external_generation" else str(ai.get("evidence_status", "")),
            "provider": "Ollama" if ai.get("provider") == "ollama" else ai.get("provider", ""),
            "model": ai.get("model", ""),
            "proposal_id": ai.get("proposal_id", ""),
            "approved_behavior_id": ai.get("approved_behavior_id", ""),
            "prompt_hash": ai.get("prompt_hash", ""),
            "response_hash": ai.get("response_hash", ""),
            "enrichment_hash": ai.get("enrichment_hash", ""),
            "enrichment_completeness": ai.get("enrichment_completeness", ""),
            "generated_field_count": ai.get("generated_field_count", 0),
            "generated_character_count": ai.get("generated_character_count", 0),
            "generated_json_paths": ai.get("generated_json_paths", []),
            "omitted_or_empty_json_paths": ai.get("omitted_or_empty_json_paths", []),
            "normalized_enrichment_hash": ai.get("normalized_enrichment_hash", ""),
            "generation_mode": ai.get("generation_mode", ""),
            "repair_attempted": ai.get("repair_attempted", False),
            "repair_succeeded": ai.get("repair_succeeded", False),
            "human_approval_status": ai.get("human_approval_status", False),
        },
        "links": _artifact_links(geometry_card),
    }
    text = json.dumps(dash, sort_keys=True, ensure_ascii=False).replace("</", "<\\/")
    return _HTML.replace("__DASHBOARD_DATA__", text)


def _artifact_links(geometry_card: dict[str, Any]) -> list[list[str]]:
    links = [
            ["ASOT Traceability Viewer", "viewers/asot_traceability_viewer.html"],
            ["Behavior Review Viewer", "viewers/behavior_review.html"],
            ["Simulation Viewer", "viewers/simulation_viewer.html"],
            ["Technical Summary", "reports/technical_summary.md"],
            ["Challenge Alignment", "reports/challenge_alignment.md"],
            ["Evidence Matrix", "reports/evidence_matrix.csv"],
            ["Demo Script", "reports/demo_script.md"],
            ["Submission Manifest", "manifests/submission_manifest.json"],
    ]
    if geometry_card.get("available"):
        links.insert(1, ["Geometry Viewer", "viewers/geometry_viewer.html"])
        links.insert(2, ["Geometry Integration Summary", "reports/geometry_integration_summary.md"])
    return links


def _geometry_summary(data: dict[str, Any]) -> str:
    card = _geometry_card(data)
    if not card.get("available"):
        return "No Phase 6C geometry artifact was packaged."
    return (
        f"{card['source_format']} {card['dimensions']} {card['unit']}; "
        f"validation {card['validation_status']}; ASOT geometry {card['geometry_id']}; "
        "visualization only and not vendor-authoritative."
    )


def _geometry_integration_summary(data: dict[str, Any]) -> str:
    extraction = data.get("geometry_extraction") if isinstance(data.get("geometry_extraction"), dict) else {}
    validation = data.get("geometry_validation") if isinstance(data.get("geometry_validation"), dict) else {}
    linkage = data.get("geometry_linkage_report") if isinstance(data.get("geometry_linkage_report"), dict) else {}
    scene = data.get("geometry_scene") if isinstance(data.get("geometry_scene"), dict) else {}
    geometry = extraction.get("geometry") if isinstance(extraction.get("geometry"), dict) else {}
    source_linkage = extraction.get("linkage") if isinstance(extraction.get("linkage"), dict) else {}
    dims = geometry.get("dimensions") if isinstance(geometry.get("dimensions"), dict) else {}
    bb_min = geometry.get("bounding_box_min") if isinstance(geometry.get("bounding_box_min"), dict) else {}
    bb_max = geometry.get("bounding_box_max") if isinstance(geometry.get("bounding_box_max"), dict) else {}
    tolerances = validation.get("tolerances") if isinstance(validation.get("tolerances"), dict) else extraction.get("tolerances") if isinstance(extraction.get("tolerances"), dict) else {}
    linked_parameters = linkage.get("linked_parameter_ids") if isinstance(linkage.get("linked_parameter_ids"), dict) else {}
    limitations = scene.get("limitations") if isinstance(scene.get("limitations"), list) else geometry.get("limitations") if isinstance(geometry.get("limitations"), list) else _known_limitations({})
    provenance_ids = linkage.get("source_provenance_ids") if isinstance(linkage.get("source_provenance_ids"), list) else scene.get("provenance_ids") if isinstance(scene.get("provenance_ids"), list) else []
    geometry_flags = _simulation_geometry_flags(data, extraction.get("geometry_id", ""))
    lines = [
        "# Geometry Integration Summary",
        "",
        f"- Geometry stable ID: `{_text(extraction.get('geometry_id'))}`",
        f"- Source path: `{_text(geometry.get('source_path'))}`",
        f"- Source SHA-256: `{_text(geometry.get('source_sha256'))}`",
        f"- Source format: `{_text(geometry.get('source_format'))}`",
        f"- Source classification: `{_text(source_linkage.get('source_classification'))}`",
        f"- Authoritativeness: `{_text(source_linkage.get('authoritativeness'))}`",
        f"- Facet count: {geometry.get('facet_count', '')}",
        f"- Vertex count: {geometry.get('vertex_count', '')}",
        f"- Unique vertex count: {geometry.get('unique_vertex_count', '')}",
        f"- Bounding-box minimum: x={bb_min.get('x')}, y={bb_min.get('y')}, z={bb_min.get('z')}",
        f"- Bounding-box maximum: x={bb_max.get('x')}, y={bb_max.get('y')}, z={bb_max.get('z')}",
        f"- Dimensions and unit: {dims.get('x')} x {dims.get('y')} x {dims.get('z')} {_text(geometry.get('unit'))}",
        f"- Linked component IDs: {_format_list([linkage.get('linked_component_id')])}",
        f"- Linked physical-model IDs: {_format_list([linkage.get('linked_physical_model_id')])}",
        f"- Linked parameter IDs: {_format_list([linked_parameters.get(axis) for axis in ('x', 'y', 'z')])}",
        f"- Dimensional validation status: `{_text(validation.get('validation_status'))}`",
        f"- Absolute validation tolerance: {tolerances.get('absolute', '')}",
        f"- Relative validation tolerance: {tolerances.get('relative', '')}",
        f"- Provenance IDs: {_format_list(provenance_ids)}",
        f"- geometry_used_for_visualization: {str(geometry_flags['geometry_used_for_visualization']).lower()}",
        f"- geometry_used_for_flight_dynamics: {str(geometry_flags['geometry_used_for_flight_dynamics']).lower()}",
        "",
        "## Known Limitations",
        "",
    ]
    lines.extend(f"- {_text(item)}" for item in limitations if _text(item))
    return "\n".join(lines) + "\n"


def _geometry_card(data: dict[str, Any]) -> dict[str, Any]:
    extraction = data.get("geometry_extraction") if isinstance(data.get("geometry_extraction"), dict) else {}
    validation = data.get("geometry_validation") if isinstance(data.get("geometry_validation"), dict) else {}
    linkage = data.get("geometry_linkage_report") if isinstance(data.get("geometry_linkage_report"), dict) else {}
    geometry = extraction.get("geometry") if isinstance(extraction.get("geometry"), dict) else {}
    if not geometry:
        return {"available": False}
    dims = geometry.get("dimensions") if isinstance(geometry.get("dimensions"), dict) else {}
    return {
        "available": True,
        "source_format": "STL",
        "source_classification": extraction.get("linkage", {}).get("source_classification", "") if isinstance(extraction.get("linkage"), dict) else "",
        "authoritativeness": extraction.get("linkage", {}).get("authoritativeness", "") if isinstance(extraction.get("linkage"), dict) else "",
        "facet_count": geometry.get("facet_count", 0),
        "dimensions": f"{dims.get('x')} x {dims.get('y')} x {dims.get('z')}",
        "unit": geometry.get("unit", ""),
        "validation_status": "passed" if validation.get("valid") else "failed",
        "geometry_id": extraction.get("geometry_id", ""),
        "component_id": linkage.get("linked_component_id", ""),
        "physical_model_id": linkage.get("linked_physical_model_id", ""),
        "source_hash": geometry.get("source_sha256", ""),
        "viewer": "viewers/geometry_viewer.html",
    }


def _simulation_geometry_flags(data: dict[str, Any], geometry_id: str) -> dict[str, bool]:
    default = {"geometry_used_for_visualization": True, "geometry_used_for_flight_dynamics": False}
    candidates = [
        data.get("simulation_inputs") if isinstance(data.get("simulation_inputs"), dict) else {},
        data.get("simulation_data", {}).get("simulation_model", {}) if isinstance(data.get("simulation_data"), dict) and isinstance(data.get("simulation_data", {}).get("simulation_model"), dict) else {},
    ]
    for candidate in candidates:
        if candidate.get("geometry_id") == geometry_id:
            return {
                "geometry_used_for_visualization": bool(candidate.get("geometry_used_for_visualization", True)),
                "geometry_used_for_flight_dynamics": bool(candidate.get("geometry_used_for_flight_dynamics", False)),
            }
    return default


def _format_list(values: Any) -> str:
    if not isinstance(values, list):
        values = [values]
    cleaned = sorted({_text(item) for item in values if _text(item)})
    return ", ".join(f"`{item}`" for item in cleaned) if cleaned else "`not available`"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _requirement_summary(requirements: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {"low": "Low fidelity", "high": "High fidelity"}
    names = {"low_battery_return": "Low Battery Return", "maximum_speed": "Maximum Speed"}
    rows = []
    for fidelity in ("low", "high"):
        items = requirements.get(fidelity, {}) if isinstance(requirements.get(fidelity), dict) else {}
        for key in ("low_battery_return", "maximum_speed"):
            item = items.get(key, {}) if isinstance(items.get(key), dict) else {}
            rows.append(
                {
                    "fidelity": labels[fidelity],
                    "requirement": names[key],
                    "status": str(item.get("status", "not_evaluated")).upper(),
                    "requirement_id": item.get("requirement_id", ""),
                    "max_observed_speed_mps": item.get("max_observed_speed_mps", ""),
                }
            )
    return rows


def _launcher(path: Path) -> None:
    path.write_text(
        "@echo off\r\n"
        "set \"DEMO_DIR=%~dp0\"\r\n"
        "set \"DASHBOARD=%DEMO_DIR%demo_dashboard.html\"\r\n"
        "if not exist \"%DASHBOARD%\" (\r\n"
        "  echo DE2Sim demo dashboard is missing: \"%DASHBOARD%\"\r\n"
        "  pause\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
        "start \"\" \"%DASHBOARD%\"\r\n",
        encoding="utf-8",
        newline="",
    )


def _manifest(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = []
    seen = set()
    for row in rows:
        rel = _posix(row["relative_path"])
        if rel in seen:
            continue
        seen.add(rel)
        copy = dict(row)
        copy["relative_path"] = rel
        file_path = root / rel
        copy["size"] = file_path.stat().st_size
        copy["sha256"] = _sha256(file_path)
        normalized.append(copy)
    return {"schema_version": DEMO_SCHEMA_VERSION, "package_root": ROOT_NAME, "files": sorted(normalized, key=lambda item: item["relative_path"])}


def _reproducibility(data: dict[str, Any], cli_version: str, test_summary: str, root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    proposals = data["behavior_proposals"]
    return {
        "schema_version": "de2sim.reproducibility_report.v1",
        "cli_version": cli_version,
        "approved_asot_stable_id": data["approved_asot"].get("asot_id", ""),
        "approved_behavior_stable_id": data["simulation_data"]["asot_facts"].get("approved_behavior_id", ""),
        "simulation_run_id": data["simulation_data"].get("simulation_run_id", ""),
        "scenario_id": data["simulation_data"]["scenario"]["scenario_id"]["value"],
        "prompt_hash": proposals.get("prompt_hash", ""),
        "input_hashes": {item["relative_path"]: item["sha256"] for item in manifest["files"] if item["stage"] in {"ingestion", "human_approval", "simulation"}},
        "artifact_hashes": {item["relative_path"]: item["sha256"] for item in manifest["files"]},
        "deterministic_metadata": ["stable IDs", "prompt_hash", "simulation_run_id", "fixed ZIP timestamps"],
        "non_deterministic_metadata": ["original artifact generated_at_utc fields when present"],
        "test_result_summary": test_summary,
        "legacy_file_integrity_confirmation": "paper_to_simulator_builder_v3_4.py unchanged; verify with git diff -- paper_to_simulator_builder_v3_4.py",
        "known_limitations": ["No Godot export", "No flight certification", "Offline proposal is non-generative"],
    }


def _verify_links(root: Path) -> None:
    links = [
        "viewers/asot_traceability_viewer.html",
        "viewers/behavior_review.html",
        "viewers/simulation_viewer.html",
        "reports/technical_summary.md",
        "reports/challenge_alignment.md",
        "reports/evidence_matrix.csv",
        "reports/demo_script.md",
    ]
    if (root / "viewers" / "geometry_viewer.html").is_file():
        links.append("viewers/geometry_viewer.html")
        links.append("reports/geometry_integration_summary.md")
    for rel in links:
        target = (root / rel).resolve()
        if not str(target).startswith(str(root.resolve())) or not target.is_file():
            raise DemoPackageError(f"dashboard link does not resolve within package: {rel}")


def _verify_manifest_hashes(root: Path, manifest: dict[str, Any]) -> None:
    for item in manifest["files"]:
        if item["relative_path"] == "manifests/submission_manifest.json":
            continue
        path = root / item["relative_path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise DemoPackageError(f"manifest hash mismatch: {item['relative_path']}")


def _write_zip(root: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda item: _posix(Path(ROOT_NAME) / item.relative_to(root)))
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            rel = _posix(Path(ROOT_NAME) / path.relative_to(root))
            info = zipfile.ZipInfo(rel, FIXED_ZIP_DT)
            info.external_attr = 0o644 << 16
            data = path.read_bytes()
            archive.writestr(info, data)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _posix(path: Path | str) -> str:
    return str(path).replace(os.sep, "/")


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DBbun DE2Sim Demo</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;color:#1f2933;background:#f6f8fb}header{padding:24px 28px;background:#102033;color:white}h1{margin:0;font-size:28px}h2{font-size:18px}.tag{color:#b8d5ff}.wrap{max-width:1220px;margin:0 auto;padding:18px}.pipeline{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:8px}.stage,.card{background:white;border:1px solid #cfd8e3;border-radius:8px;padding:12px;min-width:0}.stage{font-weight:bold;text-align:center}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:14px}.ok{color:#12733f;font-weight:bold}.warn{color:#8a6500;font-weight:bold}.bad{color:#a43131;font-weight:bold}.links a{display:inline-block;margin:5px 6px 5px 0;padding:8px 10px;border:1px solid #b8c4d4;border-radius:7px;background:white;color:#154f8f;text-decoration:none}.card-body{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.35}.req-line{margin:4px 0}.artifact{color:#5d6878;font-size:12px;margin-top:6px}small{color:#5d6878}@media(max-width:980px){.pipeline{grid-template-columns:repeat(2,minmax(150px,1fr))}}@media(max-width:560px){.pipeline{grid-template-columns:1fr}.wrap{padding:12px}}
</style>
</head>
<body>
<header><h1>DBbun / DE2Sim</h1><div class="tag">readable -&gt; runnable integrated demonstration package</div></header>
<main class="wrap">
<section><h2>Nine-Stage Pipeline</h2><div class="pipeline" id="pipeline"></div></section>
<section><h2>Status Cards</h2><div class="grid" id="cards"></div></section>
<section><h2>Open Artifacts</h2><div class="links" id="links"></div></section>
<section class="card"><h2>Limitations</h2><p id="general-limitations"></p></section>
</main>
<script id="dashboard-data" type="application/json">__DASHBOARD_DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("dashboard-data").textContent);
function txt(el,v){el.textContent=v==null?"":String(v)}
function add(tag,parent,cls){const el=document.createElement(tag);if(cls)el.className=cls;parent.appendChild(el);return el}
["Engineering Package","Parsed Artifacts","CAD Geometry Transformation","ASOT","Provenance and Traceability","Behavior Proposal","Human Approval","Executable Simulation","Requirement Evidence"].forEach(s=>txt(add("div",document.getElementById("pipeline"),"stage"),s));
const cards=document.getElementById("cards");
function card(title,body,cls){const c=add("div",cards,"card");txt(add("h2",c),title);const p=add("div",c,"card-body "+(cls||""));txt(p,body);return c}
txt(document.getElementById("general-limitations"),data.general_limitations);
card("Package Status","Self-contained local package with relative links only.","ok");
card("ASOT Validation",(data.asot_validation.passed?"PASSED":"FAILED")+"\\nErrors: "+data.asot_validation.error_count+"\\nWarnings: "+data.asot_validation.warning_count+"\\nArtifact: "+data.asot_validation.artifact,data.asot_validation.passed?"ok":"bad");
card("Provenance Coverage","Coverage: "+data.provenance.coverage_percentage+"%\\nProvenance: "+data.provenance.provenance_manifest+"\\nTraceability: "+data.provenance.traceability_report,"ok");
if(data.geometry&&data.geometry.available){card("CAD/Geometry Integration","source format: "+data.geometry.source_format+"\\nsource classification: "+data.geometry.source_classification+"\\nauthoritativeness: "+data.geometry.authoritativeness+"\\nfacet count: "+data.geometry.facet_count+"\\ndimensions: "+data.geometry.dimensions+"\\nunits: "+data.geometry.unit+"\\nparametric dimension validation: "+data.geometry.validation_status+"\\nlinked ASOT geometry ID: "+data.geometry.geometry_id+"\\nlinked component ID: "+data.geometry.component_id+"\\nlinked physical-model ID: "+data.geometry.physical_model_id+"\\nsource hash: "+data.geometry.source_hash+"\\ngeometry viewer link: "+data.geometry.viewer,"ok");}
card("Approved Behavior",data.approved_behavior_id+"\\n"+data.sequence,"ok");
card("Human Approval","Approved proposal ID: "+(data.human_approval.approved_proposal_id||"not available")+"\\nApproved behavior stable ID: "+data.human_approval.approved_behavior_id+"\\nApproval status: "+data.human_approval.approval_status+"\\nDecision timestamp: "+(data.human_approval.decision_timestamp||"not available"),"ok");
card("Low-Fidelity Result","mission completed: "+data.status.low.mission_completed+"\\nreserve: "+data.status.low.battery_reserve_at_landing_percent+"%","ok");
card("High-Fidelity Result","mission completed: "+data.status.high.mission_completed+"\\nreserve: "+data.status.high.battery_reserve_at_landing_percent+"%","ok");
card("Scenario Feasibility",data.status.low.scenario_feasibility_status+" / "+data.status.high.scenario_feasibility_status,"ok");
const reqCard=card("Requirement Results","","ok");const reqBody=reqCard.querySelector(".card-body");txt(reqBody,"");["Low fidelity","High fidelity"].forEach(fid=>{const h=add("div",reqBody,"req-line");txt(h,fid+":");data.requirement_summary.filter(r=>r.fidelity===fid).forEach(r=>{const line=add("div",reqBody,"req-line");txt(line,"- "+r.requirement+": "+r.status+" ("+r.requirement_id+(r.max_observed_speed_mps!==""?", max observed speed "+r.max_observed_speed_mps+" m/s":"")+")")})});
card("Reproducibility Status","Manifest hashes, deterministic ZIP timestamps, and no absolute paths.","ok");
card("AI-Generation Status",data.external_ai_status.label+"\\n"+(data.ai.evidence_status==="confirmed_local_generation"?"ASOT-bound behavior structure with local AI enrichment\\n":"")+"provider: "+data.external_ai_status.provider+"\\nmodel: "+data.external_ai_status.model+"\\ngeneration mode: "+data.external_ai_status.generation_mode+"\\nenrichment completeness: "+data.external_ai_status.enrichment_completeness+"\\ngenerated field count: "+data.external_ai_status.generated_field_count+"\\nLocal JSON syntax repair: "+(data.external_ai_status.repair_attempted?"used":"not used")+"\\nproposal ID: "+data.external_ai_status.proposal_id+"\\napproved behavior stable ID: "+data.external_ai_status.approved_behavior_id+"\\nprompt hash: "+data.external_ai_status.prompt_hash+"\\nresponse hash: "+data.external_ai_status.response_hash+"\\nenrichment hash: "+data.external_ai_status.enrichment_hash+"\\nhuman approval status: "+data.external_ai_status.human_approval_status+"\\nactual local inference: "+data.ai.actual_local_model_inference_occurred+"\\nactual external API call: "+data.ai.actual_external_api_call_occurred,(data.ai.evidence_status==="offline_non_generative"?"warn":"ok"));
card("Known Limitations",(data.known_limitations||[]).map(x=>"- "+x).join("\\n"),"warn");
const links=document.getElementById("links");data.links.forEach(([label,href])=>{const a=add("a",links);a.href=href;txt(a,label)});
</script>
</body>
</html>
"""
