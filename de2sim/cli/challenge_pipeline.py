"""Challenge II pipeline CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from de2sim.asot.builder import ASOTBuildError, build_asot_from_files, load_json, write_asot_outputs
from de2sim.behaviors.approval import BehaviorApprovalError, load_decisions, write_behavior_approval_outputs
from de2sim.behaviors.proposal_generator import BehaviorProposalError, build_external_generation_audit, load_behavior_proposals, write_behavior_generation_outputs
from de2sim.demo import DemoPackageError, build_demo_package
from de2sim.geometry.pipeline import GeometryError, validate_geometry_extraction, write_geometry_outputs
from de2sim.ingest.artifact_parser import ArtifactParsingError, parse_artifacts_from_manifest
from de2sim.ingest.package_reader import (
    PackageValidationError,
    ingest_engineering_package,
)
from de2sim.provenance.manifest import ProvenanceManifestError, write_provenance_outputs
from de2sim.provenance.trace import validate_traceability
from de2sim.simulation.runner import SimulationError, run_simulation_build
from de2sim.visualization.traceability_viewer import TraceabilityViewerError, write_viewer_outputs


_PHASE0_COMPATIBILITY_SENTINEL = b"not a real zip and not parsed in phase 0"
_PHASE0_MESSAGE = (
    "DE2Sim Phase 0 scaffold is installed, but engineering-package ingestion "
    "is not implemented yet."
)
_CLI_VERSION = "0.7.0-phase6c-geometry"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="python -m de2sim.cli.challenge_pipeline",
        description="DE2Sim Challenge II pipeline scaffold.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the DE2Sim scaffold version and exit.",
    )
    parser.add_argument(
        "--engineering-package",
        metavar="PATH",
        help="Path to a ZIP engineering package.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Output directory for Phase 1A package ingestion artifacts.",
    )
    parser.add_argument(
        "--parse-artifacts",
        action="store_true",
        help="After Phase 1A ingestion, parse supported structured artifacts and write parsed_artifacts.json.",
    )
    parser.add_argument(
        "--build-asot",
        action="store_true",
        help="Run ingestion, artifact parsing, ASOT construction, and ASOT validation.",
    )
    parser.add_argument(
        "--build-provenance",
        action="store_true",
        help="Run ingestion, artifact parsing, ASOT construction, ASOT validation, provenance construction, and traceability validation.",
    )
    parser.add_argument(
        "--build-viewer",
        action="store_true",
        help="Run all prior stages and generate the standalone ASOT traceability viewer.",
    )
    parser.add_argument(
        "--extract-geometry",
        action="store_true",
        help="Run ingestion, parsing, ASOT construction, and Phase 6C STL geometry extraction/validation.",
    )
    parser.add_argument(
        "--build-geometry-viewer",
        action="store_true",
        help="Run Phase 6C geometry extraction/validation and generate the standalone geometry viewer.",
    )
    parser.add_argument(
        "--propose-behaviors",
        action="store_true",
        help="Run all prior stages and generate Phase 4A behavior proposals for human review.",
    )
    parser.add_argument(
        "--ai-provider",
        choices=("offline", "openai", "anthropic", "ollama"),
        default="offline",
        help="Behavior proposal provider. Defaults to offline deterministic templates.",
    )
    parser.add_argument(
        "--ai-model",
        metavar="MODEL",
        default="",
        help="Explicit OpenAI or Anthropic model for external behavior generation. May also use DE2SIM_OPENAI_MODEL or DE2SIM_ANTHROPIC_MODEL.",
    )
    parser.add_argument(
        "--ollama-base-url",
        metavar="URL",
        default="http://localhost:11434",
        help="Loopback-only Ollama base URL. DE2Sim appends /api/generate.",
    )
    parser.add_argument(
        "--provider-timeout-seconds",
        metavar="N",
        type=float,
        default=30.0,
        help="External provider timeout in seconds.",
    )
    parser.add_argument(
        "--provider-max-attempts",
        metavar="N",
        type=int,
        default=1,
        help="Maximum external provider attempts.",
    )
    parser.add_argument(
        "--external-generation-purpose",
        metavar="TEXT",
        default="",
        help="Purpose string embedded in the external-generation prompt.",
    )
    parser.add_argument(
        "--apply-behavior-decisions",
        metavar="PATH_TO_JSON",
        help="Apply explicit review decisions to behavior_proposals.json and write a new approved-behavior ASOT.",
    )
    parser.add_argument(
        "--build-simulation",
        action="store_true",
        help="Build deterministic Phase 5A low/high fidelity simulation artifacts from an approved ASOT.",
    )
    parser.add_argument(
        "--build-demo-package",
        action="store_true",
        help="Build the Phase 6A reproducible submission demonstration package.",
    )
    parser.add_argument(
        "--approved-asot",
        metavar="PATH",
        help="Approved ASOT path for --build-simulation.",
    )
    parser.add_argument(
        "--scenario",
        metavar="PATH",
        help="Optional explicit simulation scenario JSON for --build-simulation.",
    )
    parser.add_argument(
        "--behavior-artifacts-dir",
        metavar="PATH",
        help="Behavior artifacts directory for --build-demo-package.",
    )
    parser.add_argument(
        "--simulation-artifacts-dir",
        metavar="PATH",
        help="Simulation artifacts directory for --build-demo-package.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Challenge II CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"DE2Sim v{_CLI_VERSION} (supersedes DE2Sim v0.6.5-phase6b-local; supersedes DE2Sim v0.6.4-phase6b-local; supersedes DE2Sim v0.6.3-phase6b-local; supersedes DE2Sim v0.6.2-phase6b-local; supersedes DE2Sim v0.6.1-phase6b; supersedes DE2Sim v0.6.0-phase6a; supersedes DE2Sim v0.5.0-phase5a; supersedes DE2Sim v0.4.1-phase4b; supersedes DE2Sim v0.3.2-phase3c; supersedes DE2Sim v0.3.1-phase3b; supersedes DE2Sim v0.3.0-phase3a; supersedes DE2Sim v0.2.0-phase2b)")
        return 0

    if args.build_demo_package:
        required = {
            "--engineering-package": args.engineering_package,
            "--approved-asot": args.approved_asot,
            "--behavior-artifacts-dir": args.behavior_artifacts_dir,
            "--simulation-artifacts-dir": args.simulation_artifacts_dir,
            "--output": args.output,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            parser.exit(2, "error: " + ", ".join(missing) + " required with --build-demo-package.\n")
        try:
            demo_outputs = build_demo_package(
                args.engineering_package,
                args.approved_asot,
                args.behavior_artifacts_dir,
                args.simulation_artifacts_dir,
                args.output,
                f"DE2Sim v{_CLI_VERSION}",
            )
        except DemoPackageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for key in ("package_root", "dashboard", "manifest", "reproducibility_report", "ai_generation_evidence", "zip"):
            print(demo_outputs[key])
        return 0

    if args.build_simulation:
        if not args.approved_asot:
            parser.exit(2, "error: --approved-asot is required with --build-simulation.\n")
        if not args.output:
            parser.exit(2, "error: --output is required with --build-simulation.\n")
        try:
            simulation_outputs = run_simulation_build(args.approved_asot, args.output, args.scenario)
        except SimulationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for key in (
            "simulation_inputs",
            "simulation_model",
            "telemetry_low",
            "telemetry_high",
            "simulation_events",
            "requirements_evaluation",
            "fidelity_comparison",
            "simulation_summary",
            "simulation_data",
            "simulation_viewer",
        ):
            print(simulation_outputs[key])
        return 0

    if not args.engineering_package and not args.apply_behavior_decisions:
        parser.exit(
            2,
            "error: --engineering-package is required for the Challenge II pipeline "
            "scaffold. Use --version to inspect the installed scaffold.\n",
        )

    if not args.output:
        parser.exit(
            2,
            "error: --output is required for engineering-package ingestion.\n",
        )

    if args.apply_behavior_decisions and not args.engineering_package:
        try:
            output = Path(args.output)
            asot_payload = load_json(output / "asot.json", "asot")
            proposals_payload = load_behavior_proposals(output / "behavior_proposals.json")
            decisions_payload = load_decisions(args.apply_behavior_decisions)
            approval_outputs = write_behavior_approval_outputs(asot_payload, proposals_payload, decisions_payload, output)
            approved_payload = load_json(approval_outputs["asot_with_approved_behaviors"], "asot_with_approved_behaviors")
            prompt_payload = load_json(output / "behavior_prompt.json", "behavior_prompt")
            audit = build_external_generation_audit(asot_payload, prompt_payload, proposals_payload, load_json(approval_outputs["behavior_decisions"], "behavior_decisions"), approved_payload)
            (output / "external_generation_audit.json").write_text(json.dumps(audit, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        except (ASOTBuildError, BehaviorApprovalError, BehaviorProposalError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(approval_outputs["behavior_decisions"])
        print(approval_outputs["asot_with_approved_behaviors"])
        print(approval_outputs["behavior_approval_report"])
        return 4 if load_json(approval_outputs["behavior_approval_report"], "behavior_approval_report").get("valid") is False else 0

    package_path = Path(args.engineering_package)
    try:
        if package_path.read_bytes() == _PHASE0_COMPATIBILITY_SENTINEL:
            print(f"Requested output path: {Path(args.output)}")
            print(_PHASE0_MESSAGE)
            return 3
    except OSError:
        pass

    try:
        manifest_path = ingest_engineering_package(
            package_path,
            Path(args.output),
        )
    except PackageValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(manifest_path)
    if args.parse_artifacts or args.build_asot or args.build_provenance or args.build_viewer or args.extract_geometry or args.build_geometry_viewer or args.propose_behaviors or args.apply_behavior_decisions:
        try:
            parsed_path = parse_artifacts_from_manifest(manifest_path)
        except ArtifactParsingError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(parsed_path)
    else:
        return 0

    if args.build_asot or args.build_provenance or args.build_viewer or args.extract_geometry or args.build_geometry_viewer or args.propose_behaviors or args.apply_behavior_decisions:
        try:
            parsed = load_json(parsed_path, "parsed_artifacts")
            document = build_asot_from_files(manifest_path, parsed_path)
            outputs = write_asot_outputs(document, Path(args.output), parsed)
        except ASOTBuildError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(outputs["asot"])
        print(outputs["summary"])
        print(outputs["validation"])
        if outputs["asot"].name == "asot_invalid.json":
            return 4
        if args.extract_geometry or args.build_geometry_viewer:
            try:
                parsed_payload = load_json(parsed_path, "parsed_artifacts")
                extractions = parsed_payload.get("geometry_extractions", [])
                if not isinstance(extractions, list) or not extractions:
                    print("error: supported STL geometry and geometry_linkage.json are required", file=sys.stderr)
                    return 2
                asot_payload = load_json(outputs["asot"], "asot")
                validation, linkage_report = validate_geometry_extraction(extractions[0], asot_payload)
                geometry_outputs = write_geometry_outputs(extractions[0], validation, linkage_report, Path(args.output))
            except (ASOTBuildError, GeometryError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(geometry_outputs["geometry_extraction"])
            print(geometry_outputs["geometry_validation"])
            print(geometry_outputs["geometry_linkage_report"])
            print(geometry_outputs["geometry_scene"])
            if args.build_geometry_viewer:
                print(geometry_outputs["geometry_viewer"])
            if not validation.get("valid", False):
                print("error: geometry validation failed", file=sys.stderr)
                return 4
        if args.build_provenance or args.build_viewer or args.propose_behaviors:
            try:
                package_manifest = load_json(manifest_path, "package_manifest")
                asot_payload = load_json(outputs["asot"], "asot")
                provenance_outputs = write_provenance_outputs(
                    asot_payload,
                    package_manifest,
                    parsed,
                    Path(args.output),
                    manifest_path,
                    parsed_path,
                    outputs["asot"],
                )
                provenance_manifest = load_json(provenance_outputs["provenance_manifest"], "provenance_manifest")
                traceability = load_json(provenance_outputs["traceability_report_json"], "traceability_report")
            except (ASOTBuildError, ProvenanceManifestError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(provenance_outputs["provenance_manifest"])
            print(provenance_outputs["traceability_report_json"])
            print(provenance_outputs["traceability_report_md"])
            if not traceability.get("valid", False):
                print("error: traceability validation failed", file=sys.stderr)
                return 5
            if args.build_viewer:
                try:
                    viewer_outputs = write_viewer_outputs(
                        asot_payload,
                        provenance_manifest,
                        traceability,
                        Path(args.output),
                    )
                except TraceabilityViewerError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return 2
                print(viewer_outputs["viewer_html"])
                print(viewer_outputs["viewer_data"])
            if args.propose_behaviors:
                try:
                    behavior_outputs = write_behavior_generation_outputs(
                        asot_payload,
                        Path(args.output),
                        args.ai_provider,
                        model=args.ai_model,
                        timeout_seconds=args.provider_timeout_seconds,
                        max_attempts=args.provider_max_attempts,
                        external_generation_purpose=args.external_generation_purpose,
                        ollama_base_url=args.ollama_base_url,
                    )
                except BehaviorProposalError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return 2
                print(behavior_outputs["behavior_prompt"])
                print(behavior_outputs["behavior_proposals"])
                print(behavior_outputs["behavior_review"])
                print(behavior_outputs["behavior_generation_report"])
                print(behavior_outputs["external_generation_audit"])
                print(behavior_outputs["external_generation_summary"])
        if args.apply_behavior_decisions:
            try:
                asot_payload = load_json(outputs["asot"], "asot")
                proposals_payload = load_behavior_proposals(Path(args.output) / "behavior_proposals.json")
                decisions_payload = load_decisions(args.apply_behavior_decisions)
                approval_outputs = write_behavior_approval_outputs(asot_payload, proposals_payload, decisions_payload, Path(args.output))
                report = load_json(approval_outputs["behavior_approval_report"], "behavior_approval_report")
                approved_payload = load_json(approval_outputs["asot_with_approved_behaviors"], "asot_with_approved_behaviors")
                prompt_payload = load_json(Path(args.output) / "behavior_prompt.json", "behavior_prompt")
                audit = build_external_generation_audit(asot_payload, prompt_payload, proposals_payload, load_json(approval_outputs["behavior_decisions"], "behavior_decisions"), approved_payload)
                (Path(args.output) / "external_generation_audit.json").write_text(json.dumps(audit, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            except (ASOTBuildError, BehaviorApprovalError, BehaviorProposalError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(approval_outputs["behavior_decisions"])
            print(approval_outputs["asot_with_approved_behaviors"])
            print(approval_outputs["behavior_approval_report"])
            if not report.get("valid", False):
                print("error: ASOT validation failed after behavior approval", file=sys.stderr)
                return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
