"""Traceability classification and validation for DE2Sim provenance."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
from typing import Any

from de2sim.provenance.hashing import HashingError, sha256_file


ALLOWED_EVIDENCE_TYPES = {
    "csv_row",
    "text_line",
    "text_line_range",
    "json_pointer",
    "yaml_key_path",
    "sysml_element",
    "sysml_line",
    "whole_file",
    "geometry_file",
}
TRACEABLE_SECTIONS = (
    "components",
    "requirements",
    "interfaces",
    "parameters",
    "physical_models",
    "behaviors",
    "geometry",
)
PRECISE_EVIDENCE_TYPES = ALLOWED_EVIDENCE_TYPES - {"whole_file", "geometry_file"}


@dataclass
class TraceabilityValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    broken_provenance_references: list[str] = field(default_factory=list)
    missing_source_files: list[str] = field(default_factory=list)
    checksum_mismatches: list[dict[str, str]] = field(default_factory=list)
    entities_without_provenance: list[str] = field(default_factory=list)
    entities_with_whole_file_only_provenance: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": sorted(set(self.errors)),
            "warnings": sorted(set(self.warnings)),
            "coverage_summary": self.coverage_summary,
            "broken_provenance_references": sorted(set(self.broken_provenance_references)),
            "missing_source_files": sorted(set(self.missing_source_files)),
            "checksum_mismatches": sorted(self.checksum_mismatches, key=lambda item: item.get("source_relative_path", "")),
            "entities_without_provenance": sorted(set(self.entities_without_provenance)),
            "entities_with_whole_file_only_provenance": sorted(set(self.entities_with_whole_file_only_provenance)),
        }


def classify_locator(source_locator: str, source_relative_path: str = "") -> str:
    """Classify a source locator into a supported evidence type."""
    locator = str(source_locator or "").strip()
    path = str(source_relative_path or "").lower()
    if locator == "file":
        if path.endswith((".glb", ".gltf", ".obj", ".stl")):
            return "geometry_file"
        return "whole_file"
    if re.fullmatch(r"row:\d+", locator):
        return "csv_row"
    if re.fullmatch(r"line:\d+", locator):
        if path.endswith(".sysml"):
            return "sysml_line"
        return "text_line"
    if re.fullmatch(r"line:\d+-\d+", locator):
        return "text_line_range"
    if locator.startswith("json:"):
        return "json_pointer"
    if locator.startswith("yaml:"):
        return "yaml_key_path"
    if locator.startswith("sysml:"):
        return "sysml_element"
    return "unsupported"


def provenance_precision(record: dict[str, Any]) -> str:
    evidence_type = str(record.get("evidence_type", ""))
    if evidence_type in PRECISE_EVIDENCE_TYPES:
        return "precise"
    if evidence_type in {"whole_file", "geometry_file"}:
        return "whole_file"
    return "unresolved"


def engineering_entities(asot: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    records: list[tuple[str, str, dict[str, Any]]] = []
    for section in TRACEABLE_SECTIONS:
        value = asot.get(section, [])
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    records.append((section, str(item.get("stable_id", "")), item))
    return records


def calculate_coverage_summary(asot: dict[str, Any], provenance_manifest: dict[str, Any]) -> dict[str, Any]:
    records = {
        str(item.get("provenance_id", "")): item
        for item in provenance_manifest.get("provenance_records", [])
        if isinstance(item, dict)
    }
    entities = engineering_entities(asot)
    total = len(entities)
    precise = 0
    whole_file = 0
    unresolved = 0
    not_provided = 0
    traceable = 0
    for _section, _entity_id, entity in entities:
        refs = [str(ref) for ref in entity.get("source_references", []) if str(ref)]
        valid_refs = [records[ref] for ref in refs if ref in records]
        status = str(entity.get("traceability_status", ""))
        if valid_refs:
            traceable += 1
            if any(provenance_precision(record) == "precise" for record in valid_refs):
                precise += 1
            elif all(provenance_precision(record) == "whole_file" for record in valid_refs):
                whole_file += 1
            else:
                unresolved += 1
        elif status == "not_provided":
            not_provided += 1
        else:
            unresolved += 1
    percentage = round((traceable / total) * 100.0, 2) if total else 100.0
    return {
        "total_asot_entities": total,
        "entities_with_precise_provenance": precise,
        "entities_with_whole_file_provenance": whole_file,
        "entities_with_unresolved_provenance": unresolved,
        "entities_marked_not_provided": not_provided,
        "traceability_percentage": percentage,
    }


def validate_traceability(
    asot: dict[str, Any],
    provenance_manifest: dict[str, Any],
    extraction_root: Path | str | None = None,
) -> TraceabilityValidationResult:
    """Validate provenance and ASOT trace links without mutating inputs."""
    asot_copy = deepcopy(asot)
    manifest_copy = deepcopy(provenance_manifest)
    errors: list[str] = []
    warnings: list[str] = []
    broken_refs: list[str] = []
    missing_files: list[str] = []
    mismatches: list[dict[str, str]] = []
    without_prov: list[str] = []
    whole_file_only: list[str] = []

    source_files = {
        str(item.get("source_relative_path", "")): item
        for item in manifest_copy.get("source_files", [])
        if isinstance(item, dict)
    }
    records: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    target_entity_ids = {entity_id for _section, entity_id, _entity in engineering_entities(asot_copy) if entity_id}

    for record in manifest_copy.get("provenance_records", []):
        if not isinstance(record, dict):
            errors.append("provenance record must be an object")
            continue
        provenance_id = str(record.get("provenance_id", ""))
        if not provenance_id:
            errors.append("provenance record is missing provenance_id")
        elif provenance_id in seen:
            errors.append(f"duplicate provenance ID: {provenance_id}")
        seen.add(provenance_id)
        records[provenance_id] = record
        evidence_type = str(record.get("evidence_type", ""))
        if evidence_type not in ALLOWED_EVIDENCE_TYPES:
            errors.append(f"unsupported evidence_type for {provenance_id}: {evidence_type}")
        confidence = record.get("confidence")
        if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
            errors.append(f"invalid confidence for {provenance_id}: {confidence}")
        rel = str(record.get("source_relative_path", ""))
        if rel and rel not in source_files:
            missing_files.append(rel)
            errors.append(f"provenance record {provenance_id} references missing source file: {rel}")
        for target_id in record.get("target_entity_ids", []):
            target = str(target_id)
            if target and target not in target_entity_ids:
                broken_refs.append(f"{provenance_id}->{target}")
                errors.append(f"provenance record {provenance_id} references nonexistent ASOT entity: {target}")

    for section, entity_id, entity in engineering_entities(asot_copy):
        refs = [str(ref) for ref in entity.get("source_references", []) if str(ref)]
        missing_refs = [ref for ref in refs if ref not in records]
        for ref in missing_refs:
            broken_refs.append(f"{entity_id}->{ref}")
            errors.append(f"ASOT {section} entity {entity_id} source_references nonexistent provenance record: {ref}")
        valid = [records[ref] for ref in refs if ref in records]
        if not valid:
            without_prov.append(entity_id)
        elif all(provenance_precision(record) == "whole_file" for record in valid):
            whole_file_only.append(entity_id)
            warnings.append(f"ASOT {section} entity {entity_id} has only whole-file provenance")

    for rel, source_file in source_files.items():
        if not rel:
            continue
        if extraction_root is not None:
            source_path = _safe_extracted_path(Path(extraction_root), rel)
            try:
                actual = sha256_file(source_path)
            except HashingError:
                missing_files.append(rel)
                errors.append(f"source file is missing or unreadable: {rel}")
                continue
            expected = str(source_file.get("sha256", ""))
            if expected and actual != expected:
                mismatches.append({"source_relative_path": rel, "expected_sha256": expected, "actual_sha256": actual})
                errors.append(f"checksum mismatch for source file: {rel}")

    coverage = calculate_coverage_summary(asot_copy, manifest_copy)
    return TraceabilityValidationResult(
        valid=not errors,
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
        coverage_summary=coverage,
        broken_provenance_references=broken_refs,
        missing_source_files=missing_files,
        checksum_mismatches=mismatches,
        entities_without_provenance=without_prov,
        entities_with_whole_file_only_provenance=whole_file_only,
    )


def _safe_extracted_path(extraction_root: Path, relative_path: str) -> Path:
    source = (extraction_root / Path(*PurePosixPath(relative_path).parts)).resolve()
    root = extraction_root.resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise HashingError(f"source file path escapes extraction root: {relative_path}") from exc
    return source
