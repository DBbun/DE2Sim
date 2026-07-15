"""Phase 0 Challenge II pipeline scaffold.

This module intentionally does not ingest engineering packages yet. It exists
to provide a stable import path and a controlled CLI surface for later phases.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from de2sim import __version__


_PHASE0_MESSAGE = (
    "DE2Sim Phase 0 scaffold is installed, but engineering-package ingestion "
    "is not implemented yet."
)


def build_parser() -> argparse.ArgumentParser:
    """Create the Phase 0 command-line parser."""
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
        help="Path to an engineering package. Ingestion is not implemented in Phase 0.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Output path reserved for later phases. Phase 0 does not write pipeline files.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Phase 0 CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"DE2Sim scaffold v{__version__}")
        return 0

    if not args.engineering_package:
        parser.exit(
            2,
            "error: --engineering-package is required for the Challenge II pipeline "
            "scaffold. Use --version to inspect the installed scaffold.\n",
        )

    package_path = Path(args.engineering_package)
    if not package_path.is_file():
        parser.exit(
            2,
            f"error: engineering package does not exist or is not a file: {package_path}\n",
        )

    if args.output:
        print(f"Requested output path: {Path(args.output)}")
    print(_PHASE0_MESSAGE)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
