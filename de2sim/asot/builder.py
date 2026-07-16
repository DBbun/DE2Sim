"""Build a conservative ASOT from Phase 1 engineering-package outputs."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from de2sim.asot.io import write_asot_json
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
    utc_now,
)
from de2sim.asot.validators import validate_asot
from de2sim.provenance.trace import classify_locator


GENERATOR_NAME = "de2sim.asot.builder"
GENERATOR_VERSION = "phase2b"


class ASOTBuildError(Exception):
    """Controlled ASOT build failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path | str, label: str) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ASOTBuildError(f"malformed {label} JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except OSError as exc:
        raise ASOTBuildError(f"failed to read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ASOTBuildError(f"{label} root must be an object")
    return payload


def build_asot_from_files(manifest_path: Path | str, parsed_artifacts_path: Path | str) -> ASOTDocument:
    """Build an ASOT document from package_manifest.json and parsed_artifacts.json."""
    manifest_file = Path(manifest_path)
    parsed_file = Path(parsed_artifacts_path)
    manifest = load_json(manifest_file, "package_manifest")
    parsed = load_json(parsed_file, "parsed_artifacts")
    return build_asot(manifest, parsed, semantic_artifacts_sha256(parsed))


def build_asot(manifest: dict[str, Any], parsed: dict[str, Any], parsed_artifacts_sha256: str) -> ASOTDocument:
    """Build a normalized ASOT from already loaded Phase 1 outputs."""
    manifest = copy.deepcopy(manifest)
    parsed = copy.deepcopy(parsed)
    warnings: list[str] = []
    source_sha_by_path = {
        _text(item.get("relative_path")): _text(item.get("sha256"))
        for item in _items(manifest.get("files"))
        if _text(item.get("relative_path"))
    }
    title = _derive_title(manifest, parsed)
    source_package_filename = _text(manifest.get("package_filename") or parsed.get("package_filename"))
    source_package_sha256 = _text(manifest.get("package_sha256") or parsed.get("package_sha256"))

    provenance, provenance_by_key = _build_provenance(parsed, manifest, source_sha_by_path)
    requirements = _build_requirements(parsed, provenance_by_key)
    parameters = _build_parameters(parsed, provenance_by_key)
    components, source_to_component, name_to_component = _build_components(parsed, provenance_by_key)
    interfaces = _build_interfaces(parsed, provenance_by_key, source_to_component, name_to_component, warnings)
    physical_models = _build_physical_models(parsed, provenance_by_key, parameters, warnings)
    behaviors = _build_behaviors(parsed, provenance_by_key)
    geometry = _build_geometry(manifest, provenance_by_key)

    _apply_component_relationships(components, source_to_component, name_to_component, parsed, warnings)
    _attach_component_lists(components, interfaces, parameters, behaviors, geometry)
    _apply_requirement_relationships(requirements, components, behaviors, interfaces, parsed, warnings)
    _finalize_provenance_targets(provenance, components, requirements, interfaces, parameters, physical_models, behaviors, geometry)

    metadata = ASOTMetadata(
        title=title,
        created_at_utc=utc_now(),
        source_package_filename=source_package_filename,
        source_package_sha256=source_package_sha256,
        parsed_artifacts_sha256=parsed_artifacts_sha256,
        generator_name=GENERATOR_NAME,
        generator_version=GENERATOR_VERSION,
    )
    document = ASOTDocument(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        asot_id=stable_id(
            "asot",
            {
                "title": title,
                "source_package_filename": source_package_filename,
                "source_package_sha256": source_package_sha256,
                "parsed_artifacts_sha256": parsed_artifacts_sha256,
                "generator_name": GENERATOR_NAME,
                "generator_version": GENERATOR_VERSION,
            },
        ),
        metadata=metadata,
        components=components,
        requirements=requirements,
        interfaces=interfaces,
        parameters=parameters,
        physical_models=physical_models,
        behaviors=behaviors,
        geometry=geometry,
        provenance=provenance,
    )
    result = validate_asot(document)
    document.validation = ASOTValidationState(
        errors=result.errors,
        warnings=sorted(set(result.warnings + warnings + _parsed_warnings(parsed))),
    )
    return document


def write_asot_outputs(document: ASOTDocument, output_dir: Path | str, parsed: dict[str, Any] | None = None) -> dict[str, Path]:
    """Validate and write ASOT, validation report, and summary files."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    validation = validate_asot(document)
    warnings = sorted(set(validation.warnings + document.validation.warnings))
    errors = sorted(set(validation.errors + document.validation.errors))
    document.validation = ASOTValidationState(errors=errors, warnings=warnings)
    counts = asot_counts(document)
    validation_payload = {"valid": not errors, "errors": errors, "warnings": warnings, "counts": counts}

    validation_path = output / "asot_validation.json"
    _write_json(validation_payload, validation_path)
    asot_path = output / ("asot_invalid.json" if errors else "asot.json")
    write_asot_json(document, asot_path)
    summary_path = output / "asot_summary.md"
    write_summary(document, validation_payload, parsed or {}, summary_path)
    return {
        "asot": asot_path,
        "summary": summary_path,
        "validation": validation_path,
    }


def asot_counts(document: ASOTDocument) -> dict[str, int]:
    return {
        "components": len(document.components),
        "requirements": len(document.requirements),
        "interfaces": len(document.interfaces),
        "parameters": len(document.parameters),
        "physical_models": len(document.physical_models),
        "behaviors": len(document.behaviors),
        "geometry": len(document.geometry),
        "provenance": len(document.provenance),
    }


def write_summary(
    document: ASOTDocument,
    validation_payload: dict[str, Any],
    parsed: dict[str, Any],
    path: Path | str,
) -> Path:
    target = Path(path)
    counts = validation_payload.get("counts", asot_counts(document))
    deferred = _items(parsed.get("deferred_files")) if isinstance(parsed, dict) else []
    lines = [
        "# DE2Sim ASOT Summary",
        "",
        f"- ASOT ID: `{document.asot_id}`",
        f"- Source package: `{document.metadata.source_package_filename}`",
        f"- Schema version: `{document.schema_version}`",
        f"- Validation status: `{'valid' if validation_payload.get('valid') else 'invalid'}`",
        "",
        "## Counts",
        "",
    ]
    for label, key in (
        ("Components", "components"),
        ("Requirements", "requirements"),
        ("Interfaces", "interfaces"),
        ("Parameters", "parameters"),
        ("Physical models", "physical_models"),
        ("Behaviors", "behaviors"),
        ("Geometry records", "geometry"),
        ("Preliminary provenance records", "provenance"),
    ):
        lines.append(f"- {label}: {counts.get(key, 0)}")
    lines.extend(["", "## Validation Warnings", ""])
    warnings = validation_payload.get("warnings") or []
    lines.extend([f"- {warning}" for warning in warnings] or ["- None"])
    lines.extend(["", "## Deferred Source Files", ""])
    if deferred:
        for item in deferred:
            lines.append(f"- `{_text(item.get('source_relative_path'))}`: {_text(item.get('reason'))}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Explicit Limitations",
            "",
            "- Narrow SysML subset only.",
            "- Geometry is referenced but not parsed.",
            "- Preliminary provenance is file/locator level and is not field-complete or replayable.",
            "- No AI-generated behaviors yet.",
            "- No simulation generation yet.",
            "- No Godot export yet.",
        ]
    )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return target


def _build_provenance(
    parsed: dict[str, Any],
    manifest: dict[str, Any],
    source_sha_by_path: dict[str, str],
) -> tuple[list[ProvenanceRecord], dict[tuple[str, str, str], str]]:
    records: dict[tuple[str, str, str], ProvenanceRecord] = {}
    file_by_path = {
        _text(item.get("relative_path")): item
        for item in _items(manifest.get("files"))
        if _text(item.get("relative_path"))
    }
    for section in ("requirements", "parameters", "sysml_elements", "sysml_relationships", "physical_models"):
        for item in _items(parsed.get(section)):
            key = _source_key(item)
            if not key[0]:
                continue
            records.setdefault(key, _provenance_record(item, key, source_sha_by_path, file_by_path))
    for item in _items(manifest.get("files")):
        if _text(item.get("role")) == "geometry":
            rel = _text(item.get("relative_path"))
            key = (rel, "file", "package_reader.phase1a")
            records.setdefault(
                key,
                ProvenanceRecord(
                    provenance_id=stable_id("provenance", {"path": rel, "locator": "file", "parser": "package_reader.phase1a"}),
                    source_relative_path=rel,
                    source_sha256=_text(item.get("sha256")),
                    source_role=_text(item.get("role")),
                    parser_name="package_reader.phase1a",
                    parser_status=_text(item.get("parser_status")),
                    source_locator="file",
                    evidence_type=classify_locator("file", rel),
                    evidence_text=Path(rel).name,
                    confidence=1.0,
                    warnings=_warnings(item),
                ),
            )
    return sorted(records.values(), key=lambda item: item.provenance_id), {key: value.provenance_id for key, value in records.items()}


def _provenance_record(
    item: dict[str, Any],
    key: tuple[str, str, str],
    source_sha_by_path: dict[str, str],
    file_by_path: dict[str, dict[str, Any]],
) -> ProvenanceRecord:
    rel, locator, parser_name = key
    file_entry = file_by_path.get(rel, {})
    return ProvenanceRecord(
        provenance_id=stable_id("provenance", {"path": rel, "locator": locator, "parser": parser_name}),
        source_relative_path=rel,
        source_sha256=source_sha_by_path.get(rel, ""),
        source_role=_text(item.get("source_role") or file_entry.get("role")),
        parser_name=parser_name,
        parser_status=_text(file_entry.get("parser_status")),
        source_locator=locator,
        evidence_type=classify_locator(locator, rel),
        evidence_text=_evidence_text(item),
        confidence=1.0,
        warnings=_warnings(item),
    )


def _build_requirements(parsed: dict[str, Any], provenance_by_key: dict[tuple[str, str, str], str]) -> list[Requirement]:
    records: dict[str, Requirement] = {}
    for item in _items(parsed.get("requirements")):
        text = _text(item.get("text"))
        if not text:
            continue
        req_id = _text(item.get("requirement_id"))
        title = _text(item.get("title")) or req_id or text[:80]
        evidence = _dedup_evidence(
            item,
            {
                "requirement_id": req_id,
                "title": title,
                "text": text,
                "verification_method": _text(item.get("verification_method")),
                "priority": _text(item.get("priority")),
            },
        )
        sid = stable_id("requirement", evidence)
        records.setdefault(
            sid,
            Requirement(
                stable_id=sid,
                name=title,
                description=text,
                source_references=_source_refs(item, provenance_by_key),
                traceability_status=_traceability_status(_source_refs(item, provenance_by_key), "precise"),
                status="source-derived",
                warnings=_warnings(item),
                requirement_id=req_id,
                text=text,
                verification_method=_text(item.get("verification_method")),
                priority=_text(item.get("priority")),
            ),
        )
    return _sort_entities(records)


def _build_parameters(parsed: dict[str, Any], provenance_by_key: dict[tuple[str, str, str], str]) -> list[Parameter]:
    records: dict[str, Parameter] = {}
    for item in _items(parsed.get("parameters")):
        name = _text(item.get("name") or item.get("parameter_id"))
        if not name:
            continue
        value = item.get("value")
        symbolic_expression = "" if isinstance(value, (int, float)) or value is None else _text(value)
        normalized_value = value if isinstance(value, (int, float)) else None
        evidence = _dedup_evidence(
            item,
            {
                "parameter_id": _text(item.get("parameter_id")),
                "name": name,
                "value": value,
                "unit": _text(item.get("unit")),
                "minimum": item.get("minimum"),
                "maximum": item.get("maximum"),
                "description": _text(item.get("description")),
            },
        )
        sid = stable_id("parameter", evidence)
        records.setdefault(
            sid,
            Parameter(
                stable_id=sid,
                name=name,
                description=_text(item.get("description")),
                source_references=_source_refs(item, provenance_by_key),
                traceability_status=_traceability_status(_source_refs(item, provenance_by_key), "precise"),
                status="source-derived",
                warnings=_warnings(item),
                value=normalized_value,
                unit=_text(item.get("unit")),
                minimum=item.get("minimum"),
                maximum=item.get("maximum"),
                symbolic_expression=symbolic_expression,
            ),
        )
    return _sort_entities(records)


def _build_components(
    parsed: dict[str, Any],
    provenance_by_key: dict[tuple[str, str, str], str],
) -> tuple[list[Component], dict[str, str], dict[str, str]]:
    records: dict[str, Component] = {}
    source_to_component: dict[str, str] = {}
    name_to_component: dict[str, str] = {}
    for item in _items(parsed.get("sysml_elements")):
        kind = _kind(item)
        if kind not in {"part", "part def", "package"}:
            continue
        name = _text(item.get("name") or item.get("element_id"))
        if not name:
            continue
        evidence = _dedup_evidence(
            item,
            {"kind": kind, "element_id": _text(item.get("element_id")), "name": name, "owner": _text(item.get("owner"))},
        )
        sid = stable_id("component", evidence)
        component = records.setdefault(
            sid,
            Component(
                stable_id=sid,
                name=name,
                description=_text(item.get("description")),
                source_references=_source_refs(item, provenance_by_key),
                traceability_status=_traceability_status(_source_refs(item, provenance_by_key), "precise"),
                status="source-derived",
                warnings=_warnings(item),
                component_type=kind,
            ),
        )
        for token in (_text(item.get("stable_id")), _text(item.get("element_id")), name):
            if token:
                source_to_component[token] = component.stable_id
                name_to_component[token.lower()] = component.stable_id
    return _sort_entities(records), source_to_component, name_to_component


def _build_interfaces(
    parsed: dict[str, Any],
    provenance_by_key: dict[tuple[str, str, str], str],
    source_to_component: dict[str, str],
    name_to_component: dict[str, str],
    warnings: list[str],
) -> list[Interface]:
    records: dict[str, Interface] = {}
    for item in _items(parsed.get("sysml_elements")):
        kind = _kind(item)
        if kind not in {"port", "port def"}:
            continue
        name = _text(item.get("name") or item.get("element_id"))
        if not name:
            continue
        owner_id = _resolve_component(_text(item.get("owner")), source_to_component, name_to_component)
        evidence = _dedup_evidence(item, {"kind": kind, "element_id": _text(item.get("element_id")), "name": name})
        sid = stable_id("interface", evidence)
        records.setdefault(
            sid,
            Interface(
                stable_id=sid,
                name=name,
                description=_text(item.get("description")),
                source_references=_source_refs(item, provenance_by_key),
                traceability_status=_traceability_status(_source_refs(item, provenance_by_key), "precise"),
                status="source-derived",
                warnings=_warnings(item),
                interface_type=kind,
                source_component_id=owner_id,
                port_names=[name],
                direction=_text(item.get("direction")),
                exchanged_items=_list_text(item.get("exchanged_items")),
            ),
        )
    for item in _items(parsed.get("sysml_relationships")):
        if _kind(item) != "connect":
            continue
        source_text = _text(item.get("source"))
        target_text = _text(item.get("target"))
        source_id = _resolve_component(source_text, source_to_component, name_to_component)
        target_id = _resolve_component(target_text, source_to_component, name_to_component)
        rel_warnings = _warnings(item)
        if source_text and not source_id:
            rel_warnings.append(f"unresolved connect source: {source_text}")
            warnings.append(rel_warnings[-1])
        if target_text and not target_id:
            rel_warnings.append(f"unresolved connect target: {target_text}")
            warnings.append(rel_warnings[-1])
        evidence = _dedup_evidence(item, {"kind": "connect", "source": source_text, "target": target_text})
        sid = stable_id("interface", evidence)
        records.setdefault(
            sid,
            Interface(
                stable_id=sid,
                name=_text(item.get("name")) or _text(item.get("description")) or f"{source_text} to {target_text}".strip(),
                description=_text(item.get("description")),
                source_references=_source_refs(item, provenance_by_key),
                traceability_status=_traceability_status(_source_refs(item, provenance_by_key), "precise"),
                status="source-derived",
                warnings=rel_warnings,
                interface_type="connect",
                source_component_id=source_id,
                target_component_id=target_id,
            ),
        )
    return _sort_entities(records)


def _build_physical_models(
    parsed: dict[str, Any],
    provenance_by_key: dict[tuple[str, str, str], str],
    parameters: list[Parameter],
    warnings: list[str],
) -> list[PhysicalModel]:
    records: dict[str, PhysicalModel] = {}
    parameter_by_ref: dict[str, str] = {}
    for parameter in parameters:
        for token in (parameter.stable_id, parameter.name):
            if token:
                parameter_by_ref[token.lower()] = parameter.stable_id
    for item in _items(parsed.get("physical_models")):
        equation = _text(item.get("equation"))
        if not equation:
            continue
        name = _text(item.get("name") or item.get("model_id")) or equation[:80]
        parameter_ids: list[str] = []
        model_warnings = _warnings(item)
        for token in _list_text(item.get("parameters")):
            parameter_id = parameter_by_ref.get(token.lower(), "")
            if parameter_id:
                parameter_ids.append(parameter_id)
            else:
                warning = f"unresolved physical model parameter reference: {token}"
                model_warnings.append(warning)
                warnings.append(warning)
        evidence = _dedup_evidence(item, {"model_id": _text(item.get("model_id")), "name": name, "equation": equation})
        sid = stable_id("physicalmodel", evidence)
        records.setdefault(
            sid,
            PhysicalModel(
                stable_id=sid,
                name=name,
                description=_text(item.get("description")),
                source_references=_source_refs(item, provenance_by_key),
                traceability_status=_traceability_status(_source_refs(item, provenance_by_key), "precise"),
                status="source-derived",
                warnings=sorted(set(model_warnings)),
                equation=equation,
                variables=_list_text(item.get("variables")),
                parameter_ids=sorted(set(parameter_ids)),
                assumptions=_list_text(item.get("assumptions")),
            ),
        )
    return _sort_entities(records)


def _build_behaviors(parsed: dict[str, Any], provenance_by_key: dict[tuple[str, str, str], str]) -> list[Behavior]:
    records: dict[str, Behavior] = {}
    for item in _items(parsed.get("sysml_elements")):
        kind = _kind(item)
        if kind not in {"action", "action def"}:
            continue
        name = _text(item.get("name") or item.get("element_id"))
        if not name:
            continue
        evidence = _dedup_evidence(item, {"kind": kind, "element_id": _text(item.get("element_id")), "name": name})
        sid = stable_id("behavior", evidence)
        records.setdefault(
            sid,
            Behavior(
                stable_id=sid,
                name=name,
                description=_text(item.get("description")),
                source_references=_source_refs(item, provenance_by_key),
                traceability_status=_traceability_status(_source_refs(item, provenance_by_key), "precise"),
                status="source-derived",
                warnings=_warnings(item),
                behavior_type=kind,
                actions=[name],
                generated_by="source",
                approval_status="approved",
            ),
        )
    return _sort_entities(records)


def _build_geometry(manifest: dict[str, Any], provenance_by_key: dict[tuple[str, str, str], str]) -> list[GeometryRecord]:
    records: dict[str, GeometryRecord] = {}
    for item in _items(manifest.get("files")):
        if _text(item.get("role")) != "geometry":
            continue
        rel = _text(item.get("relative_path"))
        if not rel:
            continue
        evidence = {"source_relative_path": rel, "sha256": _text(item.get("sha256")), "format": _format(item)}
        sid = stable_id("geometry", evidence)
        key = (rel, "file", "package_reader.phase1a")
        records.setdefault(
            sid,
            GeometryRecord(
                stable_id=sid,
                name=Path(rel).name,
                description="Geometry file referenced by package manifest; not parsed as CAD.",
                source_references=[provenance_by_key[key]] if key in provenance_by_key else [],
                traceability_status=_traceability_status([provenance_by_key[key]] if key in provenance_by_key else [], "whole_file"),
                status="referenced",
                warnings=_warnings(item),
                source_relative_path=rel,
                geometry_format=_format(item),
                parser_status="referenced_not_parsed",
            ),
        )
    return _sort_entities(records)


def _apply_component_relationships(
    components: list[Component],
    source_to_component: dict[str, str],
    name_to_component: dict[str, str],
    parsed: dict[str, Any],
    warnings: list[str],
) -> None:
    by_id = {item.stable_id: item for item in components}
    for item in _items(parsed.get("sysml_elements")):
        if _kind(item) not in {"part", "part def", "package"}:
            continue
        child_id = source_to_component.get(_text(item.get("stable_id"))) or source_to_component.get(_text(item.get("element_id"))) or name_to_component.get(_text(item.get("name")).lower())
        owner_text = _text(item.get("owner"))
        parent_id = _resolve_component(owner_text, source_to_component, name_to_component)
        if owner_text and not parent_id:
            warnings.append(f"unresolved component owner for {_text(item.get('name') or item.get('element_id'))}: {owner_text}")
        if child_id and parent_id and child_id != parent_id:
            by_id[child_id].parent_component_id = parent_id
            by_id[parent_id].child_component_ids = sorted(set(by_id[parent_id].child_component_ids + [child_id]))


def _apply_requirement_relationships(
    requirements: list[Requirement],
    components: list[Component],
    behaviors: list[Behavior],
    interfaces: list[Interface],
    parsed: dict[str, Any],
    warnings: list[str],
) -> None:
    requirement_by_ref: dict[str, Requirement] = {}
    for req in requirements:
        for token in (req.stable_id, req.requirement_id, req.name):
            if token:
                requirement_by_ref[token.lower()] = req
    entity_by_ref: dict[str, str] = {}
    for entity in list(components) + list(behaviors) + list(interfaces):
        for token in (entity.stable_id, entity.name):
            if token:
                entity_by_ref[token.lower()] = entity.stable_id
    for item in _items(parsed.get("sysml_relationships")):
        kind = _kind(item)
        if kind not in {"satisfy", "verify"}:
            continue
        req = _resolve_requirement(_text(item.get("target")), requirement_by_ref) or _resolve_requirement(
            _text(item.get("source")), requirement_by_ref
        )
        entity_id = _resolve_entity(_text(item.get("source")), entity_by_ref)
        if req and entity_id:
            if kind == "satisfy":
                req.satisfied_by_ids = sorted(set(req.satisfied_by_ids + [entity_id]))
            else:
                req.verified_by_ids = sorted(set(req.verified_by_ids + [entity_id]))
        else:
            warnings.append(f"unresolved {kind} relationship: {_text(item.get('description'))}")


def _attach_component_lists(
    components: list[Component],
    interfaces: list[Interface],
    parameters: list[Parameter],
    behaviors: list[Behavior],
    geometry: list[GeometryRecord],
) -> None:
    by_id = {item.stable_id: item for item in components}
    for interface in interfaces:
        for component_id in (interface.source_component_id, interface.target_component_id):
            if component_id in by_id:
                by_id[component_id].interface_ids = sorted(set(by_id[component_id].interface_ids + [interface.stable_id]))
    for parameter in parameters:
        if parameter.owning_component_id in by_id:
            by_id[parameter.owning_component_id].parameter_ids = sorted(set(by_id[parameter.owning_component_id].parameter_ids + [parameter.stable_id]))
    for behavior in behaviors:
        if behavior.owning_component_id in by_id:
            by_id[behavior.owning_component_id].behavior_ids = sorted(set(by_id[behavior.owning_component_id].behavior_ids + [behavior.stable_id]))
    for record in geometry:
        if record.owning_component_id in by_id:
            by_id[record.owning_component_id].geometry_ids = sorted(set(by_id[record.owning_component_id].geometry_ids + [record.stable_id]))


def _derive_title(manifest: dict[str, Any], parsed: dict[str, Any]) -> str:
    metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    title = _text(metadata.get("title") or manifest.get("title") or manifest.get("package_title"))
    if title:
        return title
    filename = _text(manifest.get("package_filename") or parsed.get("package_filename"))
    return Path(filename).stem if filename else "asot"


def _source_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (_text(item.get("source_relative_path")), _text(item.get("source_locator")), _text(item.get("parser_name")))


def _source_refs(item: dict[str, Any], provenance_by_key: dict[tuple[str, str, str], str]) -> list[str]:
    provenance_id = provenance_by_key.get(_source_key(item))
    return [provenance_id] if provenance_id else []


def _dedup_evidence(item: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_relative_path": _text(item.get("source_relative_path")),
        "source_locator": _text(item.get("source_locator")),
        "parser_name": _text(item.get("parser_name")),
        "payload": payload,
    }


def _resolve_component(value: str, source_to_component: dict[str, str], name_to_component: dict[str, str]) -> str:
    if not value:
        return ""
    return source_to_component.get(value) or name_to_component.get(value.lower()) or ""


def _resolve_requirement(value: str, requirement_by_ref: dict[str, Requirement]) -> Requirement | None:
    return requirement_by_ref.get(value.lower()) if value else None


def _resolve_entity(value: str, entity_by_ref: dict[str, str]) -> str:
    return entity_by_ref.get(value.lower(), "") if value else ""


def _sort_entities(records: dict[str, Any]) -> list[Any]:
    return [records[key] for key in sorted(records)]


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _kind(item: dict[str, Any]) -> str:
    return " ".join(_text(item.get("kind")).lower().split())


def _warnings(item: dict[str, Any]) -> list[str]:
    return sorted({_text(warning) for warning in item.get("warnings", []) if _text(warning)}) if isinstance(item.get("warnings"), list) else []


def _parsed_warnings(parsed: dict[str, Any]) -> list[str]:
    return sorted({_text(warning) for warning in parsed.get("warnings", []) if _text(warning)}) if isinstance(parsed.get("warnings"), list) else []


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({_text(item) for item in value if _text(item)})
    if _text(value):
        return [_text(value)]
    return []


def _format(item: dict[str, Any]) -> str:
    return _text(item.get("extension")).lstrip(".").lower()


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def semantic_artifacts_sha256(payload: dict[str, Any]) -> str:
    """Hash parsed-artifact content without runtime metadata."""
    encoded = json.dumps(_stable_hash_payload(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_hash_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable_hash_payload(value[key])
            for key in sorted(value)
            if str(key) not in {"generated_at_utc", "package_manifest_sha256"}
        }
    if isinstance(value, list):
        return [_stable_hash_payload(item) for item in value]
    return value


def _traceability_status(source_references: list[str], provided_status: str) -> str:
    return provided_status if source_references else "not_provided"


def _evidence_text(item: dict[str, Any]) -> str:
    for key in ("text", "equation", "description", "name", "element_id", "requirement_id", "parameter_id"):
        value = _text(item.get(key))
        if value:
            return value
    return ""


def _finalize_provenance_targets(provenance: list[ProvenanceRecord], *entity_groups: list[Any]) -> None:
    by_id = {record.provenance_id: record for record in provenance}
    for group in entity_groups:
        for entity in group:
            for provenance_id in getattr(entity, "source_references", []):
                if provenance_id in by_id:
                    by_id[provenance_id].target_entity_ids = sorted(
                        set(by_id[provenance_id].target_entity_ids + [entity.stable_id])
                    )
