"""Formal provenance and traceability support for DE2Sim."""

from de2sim.provenance.hashing import HashingError, sha256_bytes, sha256_file, sha256_normalized_json
from de2sim.provenance.manifest import (
    ProvenanceManifestError,
    build_provenance_manifest,
    traceability_markdown,
    write_provenance_outputs,
)
from de2sim.provenance.trace import (
    TraceabilityValidationResult,
    calculate_coverage_summary,
    classify_locator,
    validate_traceability,
)

__all__ = [
    "HashingError",
    "ProvenanceManifestError",
    "TraceabilityValidationResult",
    "build_provenance_manifest",
    "calculate_coverage_summary",
    "classify_locator",
    "sha256_bytes",
    "sha256_file",
    "sha256_normalized_json",
    "traceability_markdown",
    "validate_traceability",
    "write_provenance_outputs",
]
