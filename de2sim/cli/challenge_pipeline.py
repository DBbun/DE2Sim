"""Challenge II pipeline CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from de2sim.asot.builder import ASOTBuildError, build_asot_from_files, load_json, write_asot_outputs
from de2sim.ingest.artifact_parser import ArtifactParsingError, parse_artifacts_from_manifest
from de2sim.ingest.package_reader import (
    PackageValidationError,
    ingest_engineering_package,
)
from de2sim.provenance.manifest import ProvenanceManifestError, write_provenance_outputs
from de2sim.provenance.trace import validate_traceability
from de2sim.visualization.traceability_viewer import TraceabilityViewerError, write_viewer_outputs


_PHASE0_COMPATIBILITY_SENTINEL = b"not a real zip and not parsed in phase 0"
_PHASE0_MESSAGE = (
    "DE2Sim Phase 0 scaffold is installed, but engineering-package ingestion "
    "is not implemented yet."
)
_CLI_VERSION = "0.3.2-phase3c"


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Challenge II CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"DE2Sim v{_CLI_VERSION} (supersedes DE2Sim v0.3.1-phase3b; supersedes DE2Sim v0.3.0-phase3a; supersedes DE2Sim v0.2.0-phase2b)")
        return 0

    if not args.engineering_package:
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
    if args.parse_artifacts or args.build_asot or args.build_provenance or args.build_viewer:
        try:
            parsed_path = parse_artifacts_from_manifest(manifest_path)
        except ArtifactParsingError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(parsed_path)
    else:
        return 0

    if args.build_asot or args.build_provenance or args.build_viewer:
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
        if args.build_provenance or args.build_viewer:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
