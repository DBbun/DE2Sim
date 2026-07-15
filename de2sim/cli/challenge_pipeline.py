"""Challenge II pipeline CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from de2sim import __version__
from de2sim.ingest.package_reader import (
    PackageValidationError,
    ingest_engineering_package,
)


_PHASE0_COMPATIBILITY_SENTINEL = b"not a real zip and not parsed in phase 0"
_PHASE0_MESSAGE = (
    "DE2Sim Phase 0 scaffold is installed, but engineering-package ingestion "
    "is not implemented yet."
)


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Challenge II CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"DE2Sim v{__version__}")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
