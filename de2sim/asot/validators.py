"""Structural ASOT validation for DE2Sim Phase 2A."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from de2sim.asot.schema import (
    DOCUMENT_FIELDS,
    ENTITY_COLLECTIONS,
    SUPPORTED_SCHEMA_VERSION,
    ASOTDocument,
    EngineeringEntity,
)
from de2sim.provenance.trace import ALLOWED_EVIDENCE_TYPES


ALLOWED_APPROVAL_STATUSES = {"not_required", "pending", "approved", "rejected"}


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, list[str]]:
        return {"errors": sorted(self.errors), "warnings": sorted(self.warnings)}


def validate_asot(asot: ASOTDocument | dict[str, Any]) -> ValidationResult:
    """Validate ASOT structure without mutating the supplied ASOT."""
    errors: list[str] = []
    warnings: list[str] = []

    if isinstance(asot, dict):
        _validate_top_level_dict(asot, errors)
        document = ASOTDocument.from_dict(asot)
    elif isinstance(asot, ASOTDocument):
        document = asot
    else:
        return ValidationResult(errors=["ASOT must be an ASOTDocument or dictionary"], warnings=[])

    if document.schema_version != SUPPORTED_SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {document.schema_version}")

    _validate_required_metadata(document, errors)
    all_entities = _collect_entities(document)
    known_ids = set(all_entities)
    component_ids = {item.stable_id for item in document.components}
    interface_ids = {item.stable_id for item in document.interfaces}
    parameter_ids = {item.stable_id for item in document.parameters}
    behavior_ids = {item.stable_id for item in document.behaviors}
    geometry_ids = {item.stable_id for item in document.geometry}

    _detect_duplicate_ids(document, errors)
    _validate_provenance_records(document, known_ids, errors)
    _validate_source_references(document, known_ids, warnings)
    _validate_component_hierarchy(document, component_ids, errors)
    _validate_interfaces(document, component_ids, errors)
    _validate_component_relationship_lists(
        document,
        interface_ids,
        parameter_ids,
        behavior_ids,
        geometry_ids,
        errors,
    )
    _validate_owned_records(document, component_ids, parameter_ids, errors)
    _validate_geometry_records(document, component_ids, parameter_ids, errors)
    _validate_requirements(document, known_ids, errors)
    _validate_approval_status(document, errors)

    return ValidationResult(errors=sorted(set(errors)), warnings=sorted(set(warnings)))


def _validate_top_level_dict(data: dict[str, Any], errors: list[str]) -> None:
    for field_name in DOCUMENT_FIELDS:
        if field_name not in data:
            errors.append(f"missing required top-level field: {field_name}")
    for section in ENTITY_COLLECTIONS:
        if section in data and not isinstance(data[section], list):
            errors.append(f"top-level field must be a list: {section}")
    if "metadata" in data and not isinstance(data["metadata"], dict):
        errors.append("top-level field must be an object: metadata")
    if "validation" in data and not isinstance(data["validation"], dict):
        errors.append("top-level field must be an object: validation")


def _validate_required_metadata(document: ASOTDocument, errors: list[str]) -> None:
    metadata = document.metadata
    required = {
        "title": metadata.title,
        "created_at_utc": metadata.created_at_utc,
        "source_package_filename": metadata.source_package_filename,
        "source_package_sha256": metadata.source_package_sha256,
        "parsed_artifacts_sha256": metadata.parsed_artifacts_sha256,
        "generator_name": metadata.generator_name,
        "generator_version": metadata.generator_version,
    }
    for name, value in required.items():
        if value is None:
            errors.append(f"missing required metadata field: {name}")


def _collect_entities(document: ASOTDocument) -> dict[str, str]:
    entities: dict[str, str] = {}
    for section in ("components", "requirements", "interfaces", "parameters", "physical_models", "behaviors", "geometry"):
        for item in getattr(document, section):
            if isinstance(item, EngineeringEntity):
                entities[item.stable_id] = section
    for item in document.provenance:
        entities[item.provenance_id] = "provenance"
    return entities


def _all_engineering_entities(document: ASOTDocument) -> list[EngineeringEntity]:
    records: list[EngineeringEntity] = []
    for section in ("components", "requirements", "interfaces", "parameters", "physical_models", "behaviors", "geometry"):
        records.extend(getattr(document, section))
    return records


def _detect_duplicate_ids(document: ASOTDocument, errors: list[str]) -> None:
    seen: set[str] = set()
    for item in _all_engineering_entities(document):
        if not item.stable_id:
            errors.append(f"{item.name or item.__class__.__name__} is missing stable_id")
        elif item.stable_id in seen:
            errors.append(f"duplicate stable ID: {item.stable_id}")
        seen.add(item.stable_id)
    for item in document.provenance:
        if not item.provenance_id:
            errors.append("provenance record is missing provenance_id")
        elif item.provenance_id in seen:
            errors.append(f"duplicate provenance ID: {item.provenance_id}")
        seen.add(item.provenance_id)


def _validate_provenance_records(document: ASOTDocument, known_ids: set[str], errors: list[str]) -> None:
    for item in document.provenance:
        if item.evidence_type and item.evidence_type not in ALLOWED_EVIDENCE_TYPES:
            errors.append(f"provenance {item.provenance_id} has unsupported evidence_type: {item.evidence_type}")
        if item.confidence is not None:
            if not isinstance(item.confidence, (int, float)) or item.confidence < 0.0 or item.confidence > 1.0:
                errors.append(f"provenance {item.provenance_id} has invalid confidence: {item.confidence}")
        for target_id in item.target_entity_ids:
            if target_id not in known_ids:
                errors.append(f"provenance {item.provenance_id} references nonexistent ASOT entity: {target_id}")


def _validate_source_references(document: ASOTDocument, known_ids: set[str], warnings: list[str]) -> None:
    for item in _all_engineering_entities(document):
        for reference in item.source_references:
            if reference and reference not in known_ids:
                warnings.append(f"{item.stable_id} source reference does not match known provenance/entity ID: {reference}")


def _validate_component_hierarchy(document: ASOTDocument, component_ids: set[str], errors: list[str]) -> None:
    parent_by_child: dict[str, str] = {}
    components_by_id = {item.stable_id: item for item in document.components}
    child_ids_by_parent = {item.stable_id: set(item.child_component_ids) for item in document.components}
    for component in document.components:
        parent_id = component.parent_component_id
        if parent_id:
            if parent_id not in component_ids:
                errors.append(f"component {component.stable_id} has nonexistent parent_component_id: {parent_id}")
            elif component.stable_id not in child_ids_by_parent.get(parent_id, set()):
                errors.append(
                    f"component {component.stable_id} parent_component_id is not mirrored by parent child_component_ids"
                )
            parent_by_child[component.stable_id] = parent_id
        for child_id in component.child_component_ids:
            if child_id not in component_ids:
                errors.append(f"component {component.stable_id} references nonexistent child_component_id: {child_id}")
            if child_id == component.stable_id:
                errors.append(f"component {component.stable_id} cannot be its own child")
            child_parent = components_by_id.get(child_id).parent_component_id if child_id in components_by_id else ""
            if child_parent != component.stable_id:
                errors.append(
                    f"component {component.stable_id} child_component_id is not mirrored by child parent_component_id: {child_id}"
                )
            previous_parent = parent_by_child.get(child_id)
            if previous_parent and previous_parent != component.stable_id:
                errors.append(f"component {child_id} has conflicting parent relationships")
    for component in document.components:
        visited: set[str] = set()
        current = component.stable_id
        while current:
            if current in visited:
                errors.append(f"component hierarchy contains a cycle at {current}")
                break
            visited.add(current)
            next_parent = ""
            for candidate in document.components:
                if candidate.stable_id == current:
                    next_parent = candidate.parent_component_id
                    break
            current = next_parent


def _validate_interfaces(document: ASOTDocument, component_ids: set[str], errors: list[str]) -> None:
    for interface in document.interfaces:
        if interface.source_component_id and interface.source_component_id not in component_ids:
            errors.append(f"interface {interface.stable_id} has nonexistent source_component_id: {interface.source_component_id}")
        if interface.target_component_id and interface.target_component_id not in component_ids:
            errors.append(f"interface {interface.stable_id} has nonexistent target_component_id: {interface.target_component_id}")


def _validate_component_relationship_lists(
    document: ASOTDocument,
    interface_ids: set[str],
    parameter_ids: set[str],
    behavior_ids: set[str],
    geometry_ids: set[str],
    errors: list[str],
) -> None:
    checks = (
        ("interface_ids", interface_ids),
        ("parameter_ids", parameter_ids),
        ("behavior_ids", behavior_ids),
        ("geometry_ids", geometry_ids),
    )
    for component in document.components:
        for field_name, known_ids in checks:
            for referenced_id in getattr(component, field_name):
                if referenced_id not in known_ids:
                    errors.append(f"component {component.stable_id} references nonexistent {field_name}: {referenced_id}")


def _validate_owned_records(
    document: ASOTDocument,
    component_ids: set[str],
    parameter_ids: set[str],
    errors: list[str],
) -> None:
    for parameter in document.parameters:
        if parameter.owning_component_id and parameter.owning_component_id not in component_ids:
            errors.append(f"parameter {parameter.stable_id} has nonexistent owning_component_id: {parameter.owning_component_id}")
    for behavior in document.behaviors:
        if behavior.owning_component_id and behavior.owning_component_id not in component_ids:
            errors.append(f"behavior {behavior.stable_id} has nonexistent owning_component_id: {behavior.owning_component_id}")
    for geometry in document.geometry:
        if geometry.owning_component_id and geometry.owning_component_id not in component_ids:
            errors.append(f"geometry {geometry.stable_id} has nonexistent owning_component_id: {geometry.owning_component_id}")
    for model in document.physical_models:
        for component_id in model.owning_component_ids:
            if component_id not in component_ids:
                errors.append(f"physical model {model.stable_id} has nonexistent owning_component_id: {component_id}")
        for parameter_id in model.parameter_ids:
            if parameter_id not in parameter_ids:
                errors.append(f"physical model {model.stable_id} references nonexistent parameter_id: {parameter_id}")


def _validate_geometry_records(
    document: ASOTDocument,
    component_ids: set[str],
    parameter_ids: set[str],
    errors: list[str],
) -> None:
    physical_model_ids = {item.stable_id for item in document.physical_models}
    for geometry in document.geometry:
        if geometry.parser_status != "parsed":
            continue
        if geometry.unit and geometry.unit not in {"m"}:
            errors.append(f"geometry {geometry.stable_id} has invalid unit: {geometry.unit}")
        if geometry.authoritativeness and geometry.authoritativeness not in {"not_vendor_authoritative"}:
            errors.append(f"geometry {geometry.stable_id} has invalid authoritativeness value: {geometry.authoritativeness}")
        if not geometry.source_sha256:
            errors.append(f"geometry {geometry.stable_id} is missing source hash")
        if geometry.facet_count <= 0 or geometry.vertex_count <= 0 or geometry.unique_vertex_count <= 0:
            errors.append(f"geometry {geometry.stable_id} has invalid dimensions or facet counts")
        for field_name in ("bounding_box_min", "bounding_box_max", "dimensions", "center"):
            value = getattr(geometry, field_name)
            if not isinstance(value, dict) or any(axis not in value for axis in ("x", "y", "z")):
                errors.append(f"geometry {geometry.stable_id} has invalid {field_name}")
        for dimension in geometry.dimensions.values():
            if not isinstance(dimension, (int, float)) or dimension <= 0:
                errors.append(f"geometry {geometry.stable_id} has invalid dimensions")
        for component_id in geometry.linked_component_ids:
            if component_id not in component_ids:
                errors.append(f"geometry {geometry.stable_id} references nonexistent linked_component_id: {component_id}")
        for model_id in geometry.linked_physical_model_ids:
            if model_id not in physical_model_ids:
                errors.append(f"geometry {geometry.stable_id} references nonexistent linked_physical_model_id: {model_id}")
        for parameter_id in geometry.linked_parameter_ids:
            if parameter_id not in parameter_ids:
                errors.append(f"geometry {geometry.stable_id} references nonexistent linked_parameter_id: {parameter_id}")


def _validate_requirements(document: ASOTDocument, known_ids: set[str], errors: list[str]) -> None:
    for requirement in document.requirements:
        for referenced_id in requirement.satisfied_by_ids:
            if referenced_id not in known_ids:
                errors.append(f"requirement {requirement.stable_id} references nonexistent satisfied_by_id: {referenced_id}")
        for referenced_id in requirement.verified_by_ids:
            if referenced_id not in known_ids:
                errors.append(f"requirement {requirement.stable_id} references nonexistent verified_by_id: {referenced_id}")


def _validate_approval_status(document: ASOTDocument, errors: list[str]) -> None:
    for behavior in document.behaviors:
        if behavior.approval_status not in ALLOWED_APPROVAL_STATUSES:
            errors.append(f"behavior {behavior.stable_id} has invalid approval_status: {behavior.approval_status}")
