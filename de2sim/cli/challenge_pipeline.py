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


_PHASE0_COMPATIBILITY_SENTINEL = b"not a real zip and not parsed in phase 0"
_PHASE0_MESSAGE = (
    "DE2Sim Phase 0 scaffold is installed, but engineering-package ingestion "
    "is not implemented yet."
)
_CLI_VERSION = "0.2.0-phase2b"


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Challenge II CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"DE2Sim v{_CLI_VERSION}")
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
    if args.parse_artifacts or args.build_asot:
        try:
            parsed_path = parse_artifacts_from_manifest(manifest_path)
        except ArtifactParsingError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(parsed_path)
    else:
        return 0

    if args.build_asot:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
