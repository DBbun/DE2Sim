"""Authoritative Source of Truth support for DE2Sim."""

from de2sim.asot.builder import (
    ASOTBuildError,
    build_asot,
    build_asot_from_files,
    write_asot_outputs,
)
from de2sim.asot.io import ASOTIOError, read_asot_json, write_asot_json
from de2sim.asot.schema import (
    SUPPORTED_SCHEMA_VERSION,
    ASOTDocument,
    ASOTMetadata,
    ASOTValidationState,
    Behavior,
    Component,
    GeometryRecord,
    Interface,
    Parameter,
    PhysicalModel,
    ProvenanceRecord,
    Requirement,
    stable_id,
)
from de2sim.asot.validators import ValidationResult, validate_asot

__all__ = [
    "ASOTDocument",
    "ASOTBuildError",
    "ASOTIOError",
    "ASOTMetadata",
    "ASOTValidationState",
    "Behavior",
    "Component",
    "GeometryRecord",
    "Interface",
    "Parameter",
    "PhysicalModel",
    "ProvenanceRecord",
    "Requirement",
    "SUPPORTED_SCHEMA_VERSION",
    "ValidationResult",
    "build_asot",
    "build_asot_from_files",
    "read_asot_json",
    "stable_id",
    "validate_asot",
    "write_asot_outputs",
    "write_asot_json",
]
