"""Versioned ASOT schema dataclasses for DE2Sim Phase 2A."""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime as _dt
import hashlib
import json
from typing import Any


SUPPORTED_SCHEMA_VERSION = "de2sim.asot.v1"
ENTITY_COLLECTIONS = (
    "components",
    "requirements",
    "interfaces",
    "parameters",
    "physical_models",
    "behaviors",
    "geometry",
    "provenance",
)
DOCUMENT_FIELDS = (
    "schema_version",
    "asot_id",
    "metadata",
    "components",
    "requirements",
    "interfaces",
    "parameters",
    "physical_models",
    "behaviors",
    "geometry",
    "provenance",
    "validation",
)


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _sorted_texts(values: list[str] | tuple[str, ...] | None) -> list[str]:
    return sorted({_clean_text(value) for value in values or [] if _clean_text(value)})


def _canonical_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical_payload(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_payload(item) for item in value]
    return value


def stable_id(entity_type: str, normalized_content: Any) -> str:
    """Return a deterministic stable ID from an entity type and normalized content."""
    payload = {
        "entity_type": _clean_text(entity_type).lower(),
        "content": _canonical_payload(normalized_content),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return f"{payload['entity_type']}-{digest}"


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class EngineeringEntity:
    stable_id: str
    name: str
    description: str = ""
    source_references: list[str] = field(default_factory=list)
    traceability_status: str = "not_provided"
    status: str = "draft"
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def make_stable_id(cls, name: str, description: str = "", extra: dict[str, Any] | None = None) -> str:
        payload = {"name": _clean_text(name), "description": _clean_text(description)}
        if extra:
            payload.update(extra)
        return stable_id(cls.__name__.lower(), payload)

    def _base_dict(self) -> dict[str, Any]:
        return {
            "stable_id": self.stable_id,
            "name": self.name,
            "description": self.description,
            "source_references": _sorted_texts(self.source_references),
            "traceability_status": self.traceability_status,
            "status": self.status,
            "warnings": _sorted_texts(self.warnings),
        }

    @classmethod
    def _base_kwargs(cls, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "stable_id": str(data.get("stable_id", "")),
            "name": str(data.get("name", "")),
            "description": str(data.get("description", "")),
            "source_references": [str(item) for item in data.get("source_references", [])],
            "traceability_status": str(data.get("traceability_status", "not_provided")),
            "status": str(data.get("status", "")),
            "warnings": [str(item) for item in data.get("warnings", [])],
        }


@dataclass
class ASOTMetadata:
    title: str
    created_at_utc: str
    source_package_filename: str
    source_package_sha256: str
    parsed_artifacts_sha256: str
    generator_name: str
    generator_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "created_at_utc": self.created_at_utc,
            "source_package_filename": self.source_package_filename,
            "source_package_sha256": self.source_package_sha256,
            "parsed_artifacts_sha256": self.parsed_artifacts_sha256,
            "generator_name": self.generator_name,
            "generator_version": self.generator_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ASOTMetadata":
        return cls(
            title=str(data.get("title", "")),
            created_at_utc=str(data.get("created_at_utc", "")),
            source_package_filename=str(data.get("source_package_filename", "")),
            source_package_sha256=str(data.get("source_package_sha256", "")),
            parsed_artifacts_sha256=str(data.get("parsed_artifacts_sha256", "")),
            generator_name=str(data.get("generator_name", "")),
            generator_version=str(data.get("generator_version", "")),
        )


@dataclass
class Component(EngineeringEntity):
    component_type: str = "unknown"
    parent_component_id: str = ""
    child_component_ids: list[str] = field(default_factory=list)
    interface_ids: list[str] = field(default_factory=list)
    parameter_ids: list[str] = field(default_factory=list)
    behavior_ids: list[str] = field(default_factory=list)
    geometry_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = self._base_dict()
        data.update(
            {
                "component_type": self.component_type,
                "parent_component_id": self.parent_component_id,
                "child_component_ids": _sorted_texts(self.child_component_ids),
                "interface_ids": _sorted_texts(self.interface_ids),
                "parameter_ids": _sorted_texts(self.parameter_ids),
                "behavior_ids": _sorted_texts(self.behavior_ids),
                "geometry_ids": _sorted_texts(self.geometry_ids),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Component":
        return cls(
            **cls._base_kwargs(data),
            component_type=str(data.get("component_type", "")),
            parent_component_id=str(data.get("parent_component_id", "")),
            child_component_ids=[str(item) for item in data.get("child_component_ids", [])],
            interface_ids=[str(item) for item in data.get("interface_ids", [])],
            parameter_ids=[str(item) for item in data.get("parameter_ids", [])],
            behavior_ids=[str(item) for item in data.get("behavior_ids", [])],
            geometry_ids=[str(item) for item in data.get("geometry_ids", [])],
        )


@dataclass
class Requirement(EngineeringEntity):
    requirement_id: str = ""
    text: str = ""
    verification_method: str = ""
    priority: str = ""
    satisfied_by_ids: list[str] = field(default_factory=list)
    verified_by_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = self._base_dict()
        data.update(
            {
                "requirement_id": self.requirement_id,
                "text": self.text,
                "verification_method": self.verification_method,
                "priority": self.priority,
                "satisfied_by_ids": _sorted_texts(self.satisfied_by_ids),
                "verified_by_ids": _sorted_texts(self.verified_by_ids),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Requirement":
        return cls(
            **cls._base_kwargs(data),
            requirement_id=str(data.get("requirement_id", "")),
            text=str(data.get("text", "")),
            verification_method=str(data.get("verification_method", "")),
            priority=str(data.get("priority", "")),
            satisfied_by_ids=[str(item) for item in data.get("satisfied_by_ids", [])],
            verified_by_ids=[str(item) for item in data.get("verified_by_ids", [])],
        )


@dataclass
class Interface(EngineeringEntity):
    interface_type: str = "unknown"
    source_component_id: str = ""
    target_component_id: str = ""
    port_names: list[str] = field(default_factory=list)
    direction: str = ""
    exchanged_items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = self._base_dict()
        data.update(
            {
                "interface_type": self.interface_type,
                "source_component_id": self.source_component_id,
                "target_component_id": self.target_component_id,
                "port_names": _sorted_texts(self.port_names),
                "direction": self.direction,
                "exchanged_items": _sorted_texts(self.exchanged_items),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Interface":
        return cls(
            **cls._base_kwargs(data),
            interface_type=str(data.get("interface_type", "")),
            source_component_id=str(data.get("source_component_id", "")),
            target_component_id=str(data.get("target_component_id", "")),
            port_names=[str(item) for item in data.get("port_names", [])],
            direction=str(data.get("direction", "")),
            exchanged_items=[str(item) for item in data.get("exchanged_items", [])],
        )


@dataclass
class Parameter(EngineeringEntity):
    value: Any = None
    unit: str = ""
    minimum: Any = None
    maximum: Any = None
    symbolic_expression: str = ""
    owning_component_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = self._base_dict()
        data.update(
            {
                "value": self.value,
                "unit": self.unit,
                "minimum": self.minimum,
                "maximum": self.maximum,
                "symbolic_expression": self.symbolic_expression,
                "owning_component_id": self.owning_component_id,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Parameter":
        return cls(
            **cls._base_kwargs(data),
            value=data.get("value"),
            unit=str(data.get("unit", "")),
            minimum=data.get("minimum"),
            maximum=data.get("maximum"),
            symbolic_expression=str(data.get("symbolic_expression", "")),
            owning_component_id=str(data.get("owning_component_id", "")),
        )


@dataclass
class PhysicalModel(EngineeringEntity):
    equation: str = ""
    variables: list[str] = field(default_factory=list)
    parameter_ids: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    owning_component_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = self._base_dict()
        data.update(
            {
                "equation": self.equation,
                "variables": _sorted_texts(self.variables),
                "parameter_ids": _sorted_texts(self.parameter_ids),
                "assumptions": _sorted_texts(self.assumptions),
                "owning_component_ids": _sorted_texts(self.owning_component_ids),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhysicalModel":
        return cls(
            **cls._base_kwargs(data),
            equation=str(data.get("equation", "")),
            variables=[str(item) for item in data.get("variables", [])],
            parameter_ids=[str(item) for item in data.get("parameter_ids", [])],
            assumptions=[str(item) for item in data.get("assumptions", [])],
            owning_component_ids=[str(item) for item in data.get("owning_component_ids", [])],
        )


@dataclass
class Behavior(EngineeringEntity):
    behavior_type: str = "unknown"
    states: list[str] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    guards: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    owning_component_id: str = ""
    generated_by: str = "human"
    approval_status: str = "not_required"
    provider: str = ""
    model: str = ""
    prompt_hash: str = ""
    response_hash: str = ""
    request_hash: str = ""
    actual_external_api_call_occurred: bool = False
    actual_local_model_inference_occurred: bool = False
    evidence_status: str = ""
    local_endpoint: str = ""
    generation_mode: str = ""
    enrichment_hash: str = ""
    enrichment_completeness: str = ""
    generated_field_count: int = 0
    generated_character_count: int = 0
    generated_json_paths: list[str] = field(default_factory=list)
    omitted_or_empty_json_paths: list[str] = field(default_factory=list)
    deterministic_structure_json_paths: list[str] = field(default_factory=list)
    normalized_enrichment_hash: str = ""
    ai_contribution_manifest: dict[str, Any] = field(default_factory=dict)
    validated_proposal_hash: str = ""
    local_ai_enrichment: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    proposal_id: str = ""
    referenced_requirement_ids: list[str] = field(default_factory=list)
    referenced_parameter_ids: list[str] = field(default_factory=list)
    referenced_physical_model_ids: list[str] = field(default_factory=list)
    source_provenance_ids: list[str] = field(default_factory=list)
    approval_decision: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = self._base_dict()
        data.update(
            {
                "behavior_type": self.behavior_type,
                "states": _sorted_texts(self.states),
                "transitions": _sort_dicts([_canonical_payload(item) for item in self.transitions if isinstance(item, dict)], "from"),
                "triggers": _sorted_texts(self.triggers),
                "guards": _sorted_texts(self.guards),
                "actions": _sorted_texts(self.actions),
                "owning_component_id": self.owning_component_id,
                "generated_by": self.generated_by,
                "approval_status": self.approval_status,
                "provider": self.provider,
                "model": self.model,
                "prompt_hash": self.prompt_hash,
                "response_hash": self.response_hash,
                "request_hash": self.request_hash,
                "actual_external_api_call_occurred": self.actual_external_api_call_occurred,
                "actual_local_model_inference_occurred": self.actual_local_model_inference_occurred,
                "evidence_status": self.evidence_status,
                "local_endpoint": self.local_endpoint,
                "generation_mode": self.generation_mode,
                "enrichment_hash": self.enrichment_hash,
                "enrichment_completeness": self.enrichment_completeness,
                "generated_field_count": self.generated_field_count,
                "generated_character_count": self.generated_character_count,
                "generated_json_paths": _sorted_texts(self.generated_json_paths),
                "omitted_or_empty_json_paths": _sorted_texts(self.omitted_or_empty_json_paths),
                "deterministic_structure_json_paths": _sorted_texts(self.deterministic_structure_json_paths),
                "normalized_enrichment_hash": self.normalized_enrichment_hash,
                "ai_contribution_manifest": _canonical_payload(self.ai_contribution_manifest),
                "validated_proposal_hash": self.validated_proposal_hash,
                "local_ai_enrichment": _canonical_payload(self.local_ai_enrichment),
                "limitations": _sorted_texts(self.limitations),
                "proposal_id": self.proposal_id,
                "referenced_requirement_ids": _sorted_texts(self.referenced_requirement_ids),
                "referenced_parameter_ids": _sorted_texts(self.referenced_parameter_ids),
                "referenced_physical_model_ids": _sorted_texts(self.referenced_physical_model_ids),
                "source_provenance_ids": _sorted_texts(self.source_provenance_ids),
                "approval_decision": _canonical_payload(self.approval_decision),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Behavior":
        return cls(
            **cls._base_kwargs(data),
            behavior_type=str(data.get("behavior_type", "")),
            states=[str(item) for item in data.get("states", [])],
            transitions=[dict(item) for item in data.get("transitions", []) if isinstance(item, dict)],
            triggers=[str(item) for item in data.get("triggers", [])],
            guards=[str(item) for item in data.get("guards", [])],
            actions=[str(item) for item in data.get("actions", [])],
            owning_component_id=str(data.get("owning_component_id", "")),
            generated_by=str(data.get("generated_by", "")),
            approval_status=str(data.get("approval_status", "")),
            provider=str(data.get("provider", "")),
            model=str(data.get("model", "")),
            prompt_hash=str(data.get("prompt_hash", "")),
            response_hash=str(data.get("response_hash", "")),
            request_hash=str(data.get("request_hash", "")),
            actual_external_api_call_occurred=bool(data.get("actual_external_api_call_occurred", False)),
            actual_local_model_inference_occurred=bool(data.get("actual_local_model_inference_occurred", False)),
            evidence_status=str(data.get("evidence_status", "")),
            local_endpoint=str(data.get("local_endpoint", "")),
            generation_mode=str(data.get("generation_mode", "")),
            enrichment_hash=str(data.get("enrichment_hash", "")),
            enrichment_completeness=str(data.get("enrichment_completeness", "")),
            generated_field_count=int(data.get("generated_field_count", 0) or 0),
            generated_character_count=int(data.get("generated_character_count", 0) or 0),
            generated_json_paths=[str(item) for item in data.get("generated_json_paths", [])],
            omitted_or_empty_json_paths=[str(item) for item in data.get("omitted_or_empty_json_paths", [])],
            deterministic_structure_json_paths=[str(item) for item in data.get("deterministic_structure_json_paths", [])],
            normalized_enrichment_hash=str(data.get("normalized_enrichment_hash", "")),
            ai_contribution_manifest=dict(data.get("ai_contribution_manifest", {})) if isinstance(data.get("ai_contribution_manifest"), dict) else {},
            validated_proposal_hash=str(data.get("validated_proposal_hash", "")),
            local_ai_enrichment=dict(data.get("local_ai_enrichment", {})) if isinstance(data.get("local_ai_enrichment"), dict) else {},
            limitations=[str(item) for item in data.get("limitations", [])],
            proposal_id=str(data.get("proposal_id", "")),
            referenced_requirement_ids=[str(item) for item in data.get("referenced_requirement_ids", [])],
            referenced_parameter_ids=[str(item) for item in data.get("referenced_parameter_ids", [])],
            referenced_physical_model_ids=[str(item) for item in data.get("referenced_physical_model_ids", [])],
            source_provenance_ids=[str(item) for item in data.get("source_provenance_ids", [])],
            approval_decision=dict(data.get("approval_decision", {})) if isinstance(data.get("approval_decision"), dict) else {},
        )


@dataclass
class GeometryRecord(EngineeringEntity):
    source_relative_path: str = ""
    geometry_format: str = ""
    owning_component_id: str = ""
    parser_status: str = "referenced_not_parsed"
    coordinate_system: str = ""
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = self._base_dict()
        data.update(
            {
                "source_relative_path": self.source_relative_path,
                "geometry_format": self.geometry_format,
                "owning_component_id": self.owning_component_id,
                "parser_status": self.parser_status,
                "coordinate_system": self.coordinate_system,
                "unit": self.unit,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeometryRecord":
        return cls(
            **cls._base_kwargs(data),
            source_relative_path=str(data.get("source_relative_path", "")),
            geometry_format=str(data.get("geometry_format", "")),
            owning_component_id=str(data.get("owning_component_id", "")),
            parser_status=str(data.get("parser_status", "")),
            coordinate_system=str(data.get("coordinate_system", "")),
            unit=str(data.get("unit", "")),
        )


@dataclass
class ProvenanceRecord:
    provenance_id: str
    source_relative_path: str
    source_sha256: str
    source_role: str = ""
    parser_name: str = ""
    parser_status: str = ""
    source_locator: str = "file"
    evidence_type: str = "whole_file"
    evidence_text: str = ""
    confidence: float | None = None
    target_entity_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provenance_id": self.provenance_id,
            "source_relative_path": self.source_relative_path,
            "source_sha256": self.source_sha256,
            "source_role": self.source_role,
            "parser_name": self.parser_name,
            "parser_status": self.parser_status,
            "source_locator": self.source_locator,
            "evidence_type": self.evidence_type,
            "evidence_text": self.evidence_text,
            "confidence": self.confidence,
            "target_entity_ids": _sorted_texts(self.target_entity_ids),
            "warnings": _sorted_texts(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProvenanceRecord":
        return cls(
            provenance_id=str(data.get("provenance_id", "")),
            source_relative_path=str(data.get("source_relative_path", "")),
            source_sha256=str(data.get("source_sha256", "")),
            source_role=str(data.get("source_role", "")),
            parser_name=str(data.get("parser_name", "")),
            parser_status=str(data.get("parser_status", "")),
            source_locator=str(data.get("source_locator", "")),
            evidence_type=str(data.get("evidence_type", "whole_file")),
            evidence_text=str(data.get("evidence_text", "")),
            confidence=data.get("confidence"),
            target_entity_ids=[str(item) for item in data.get("target_entity_ids", [])],
            warnings=[str(item) for item in data.get("warnings", [])],
        )


@dataclass
class ASOTValidationState:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"errors": _sorted_texts(self.errors), "warnings": _sorted_texts(self.warnings)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ASOTValidationState":
        return cls(
            errors=[str(item) for item in data.get("errors", [])],
            warnings=[str(item) for item in data.get("warnings", [])],
        )


@dataclass
class ASOTDocument:
    schema_version: str
    asot_id: str
    metadata: ASOTMetadata
    components: list[Component] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    interfaces: list[Interface] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    physical_models: list[PhysicalModel] = field(default_factory=list)
    behaviors: list[Behavior] = field(default_factory=list)
    geometry: list[GeometryRecord] = field(default_factory=list)
    provenance: list[ProvenanceRecord] = field(default_factory=list)
    validation: ASOTValidationState = field(default_factory=ASOTValidationState)

    @classmethod
    def minimal(cls, title: str, source_package_filename: str = "") -> "ASOTDocument":
        metadata = ASOTMetadata(
            title=title,
            created_at_utc=utc_now(),
            source_package_filename=source_package_filename,
            source_package_sha256="",
            parsed_artifacts_sha256="",
            generator_name="de2sim",
            generator_version="phase2a",
        )
        return cls(
            schema_version=SUPPORTED_SCHEMA_VERSION,
            asot_id=stable_id("asot", {"title": title, "source_package_filename": source_package_filename}),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "asot_id": self.asot_id,
            "metadata": self.metadata.to_dict(),
            "components": _sort_dicts([item.to_dict() for item in self.components], "stable_id"),
            "requirements": _sort_dicts([item.to_dict() for item in self.requirements], "stable_id"),
            "interfaces": _sort_dicts([item.to_dict() for item in self.interfaces], "stable_id"),
            "parameters": _sort_dicts([item.to_dict() for item in self.parameters], "stable_id"),
            "physical_models": _sort_dicts([item.to_dict() for item in self.physical_models], "stable_id"),
            "behaviors": _sort_dicts([item.to_dict() for item in self.behaviors], "stable_id"),
            "geometry": _sort_dicts([item.to_dict() for item in self.geometry], "stable_id"),
            "provenance": _sort_dicts([item.to_dict() for item in self.provenance], "provenance_id"),
            "validation": self.validation.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ASOTDocument":
        return cls(
            schema_version=str(data.get("schema_version", "")),
            asot_id=str(data.get("asot_id", "")),
            metadata=ASOTMetadata.from_dict(data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}),
            components=[Component.from_dict(item) for item in _dict_items(data.get("components", []))],
            requirements=[Requirement.from_dict(item) for item in _dict_items(data.get("requirements", []))],
            interfaces=[Interface.from_dict(item) for item in _dict_items(data.get("interfaces", []))],
            parameters=[Parameter.from_dict(item) for item in _dict_items(data.get("parameters", []))],
            physical_models=[PhysicalModel.from_dict(item) for item in _dict_items(data.get("physical_models", []))],
            behaviors=[Behavior.from_dict(item) for item in _dict_items(data.get("behaviors", []))],
            geometry=[GeometryRecord.from_dict(item) for item in _dict_items(data.get("geometry", []))],
            provenance=[ProvenanceRecord.from_dict(item) for item in _dict_items(data.get("provenance", []))],
            validation=ASOTValidationState.from_dict(
                data.get("validation", {}) if isinstance(data.get("validation"), dict) else {}
            ),
        )


def _sort_dicts(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get(key, "")))


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def normalize_asot_dict(data: dict[str, Any]) -> dict[str, Any]:
    return ASOTDocument.from_dict(data).to_dict()
