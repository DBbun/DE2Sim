"""Standalone ASOT traceability viewer generation for DE2Sim Phase 3C."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from de2sim.provenance.trace import provenance_precision


VIEWER_SCHEMA_VERSION = "de2sim.traceability_viewer.v1"
EVIDENCE_TEXT_MAX_CHARS = 1200
PRECISION_VALUES = ("precise", "whole_file", "unresolved", "not_provided", "deferred", "unsupported")
ENTITY_SECTIONS = (
    ("components", "component"),
    ("requirements", "requirement"),
    ("interfaces", "interface"),
    ("parameters", "parameter"),
    ("physical_models", "physical_model"),
    ("behaviors", "behavior"),
    ("geometry", "geometry"),
)
LIMITATIONS = [
    "narrow SysML subset",
    "geometry referenced but not parsed",
    "no AI-generated behaviors yet",
    "no simulation generated yet",
    "no Godot export yet",
    "whole-file provenance is not field-level provenance",
    "no exact replayability claim",
]


class TraceabilityViewerError(Exception):
    """Controlled traceability viewer generation failure."""


def build_viewer_data(
    asot: dict[str, Any],
    provenance_manifest: dict[str, Any],
    traceability_report: dict[str, Any],
) -> dict[str, Any]:
    """Normalize ASOT and provenance data for the standalone viewer."""
    provenance_records = _provenance_records(provenance_manifest)
    provenance_by_id = {record["provenance_id"]: record for record in provenance_records}
    source_files = _source_files(provenance_manifest)
    source_by_path = {item["source_relative_path"]: item for item in source_files}
    nodes = []
    entity_node_by_id: dict[str, str] = {}
    provenance_node_by_id: dict[str, str] = {}
    source_node_by_path: dict[str, str] = {}

    for section, entity_type in ENTITY_SECTIONS:
        for entity in _items(asot.get(section)):
            entity_id = _text(entity.get("stable_id"))
            if not entity_id:
                continue
            node = _entity_node(section, entity_type, entity, provenance_by_id)
            entity_node_by_id[entity_id] = node["node_id"]
            nodes.append(node)

    for record in provenance_records:
        node = _provenance_node(record)
        provenance_node_by_id[record["provenance_id"]] = node["node_id"]
        nodes.append(node)

    for source_file in source_files:
        node = _source_node(source_file)
        source_node_by_path[source_file["source_relative_path"]] = node["node_id"]
        nodes.append(node)

    edges = _relationship_edges(asot, entity_node_by_id)
    edges.extend(_provenance_edges(provenance_records, entity_node_by_id, provenance_node_by_id))
    edges.extend(_source_edges(provenance_records, provenance_node_by_id, source_node_by_path))
    edges = sorted(_dedupe_edges(edges), key=lambda item: item["edge_id"])
    nodes = _with_connected_ids(nodes, edges)
    nodes = _with_layout(sorted(nodes, key=lambda item: item["node_id"]))
    metrics = _metrics(asot, provenance_records, traceability_report)
    return {
        "schema_version": VIEWER_SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "metadata": {
            "title": _text((asot.get("metadata") or {}).get("title")) if isinstance(asot.get("metadata"), dict) else "",
            "source_package_filename": _text((asot.get("metadata") or {}).get("source_package_filename")) if isinstance(asot.get("metadata"), dict) else "",
            "asot_id": _text(asot.get("asot_id")),
            "asot_schema_version": _text(asot.get("schema_version")),
            "provenance_schema_version": _text(provenance_manifest.get("schema_version")),
            "evidence_text_max_chars": EVIDENCE_TEXT_MAX_CHARS,
        },
        "metrics": metrics,
        "nodes": nodes,
        "edges": edges,
        "source_files": source_files,
        "traceability_gaps": _traceability_gaps(traceability_report),
        "validation": _validation(asot, provenance_manifest, traceability_report),
        "limitations": list(LIMITATIONS),
    }


def write_viewer_outputs(
    asot: dict[str, Any],
    provenance_manifest: dict[str, Any],
    traceability_report: dict[str, Any],
    output_dir: Path | str,
) -> dict[str, Path]:
    """Write viewer_data.json and asot_traceability_viewer.html."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = build_viewer_data(asot, provenance_manifest, traceability_report)
    data_path = output / "viewer_data.json"
    html_path = output / "asot_traceability_viewer.html"
    _write_json(data, data_path)
    html_path.write_text(render_viewer_html(data), encoding="utf-8", newline="\n")
    return {"viewer_html": html_path, "viewer_data": data_path}


def render_viewer_html(data: dict[str, Any]) -> str:
    """Return a deterministic standalone HTML page with embedded viewer data."""
    data_text = json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False).replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__VIEWER_DATA_JSON__", data_text)


def _entity_node(
    section: str,
    entity_type: str,
    entity: dict[str, Any],
    provenance_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    entity_id = _text(entity.get("stable_id"))
    provenance_ids = sorted(_list_text(entity.get("source_references")))
    precisions = sorted(
        {provenance_precision(provenance_by_id[item]) for item in provenance_ids if item in provenance_by_id}
    )
    precision = precisions[0] if len(precisions) == 1 else ("precise" if "precise" in precisions else "not_provided")
    if not provenance_ids:
        precision = _normalize_precision(_text(entity.get("traceability_status")) or "not_provided")
    return {
        "node_id": f"{entity_type}:{entity_id}",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "label": _text(entity.get("name") or entity_id),
        "description": _text(entity.get("description") or entity.get("text")),
        "status": _text(entity.get("status")),
        "warnings": sorted(_list_text(entity.get("warnings"))),
        "fields": _entity_fields(section, entity),
        "connected_entity_ids": [],
        "provenance_ids": provenance_ids,
        "provenance_precision": precision,
    }


def _provenance_node(record: dict[str, Any]) -> dict[str, Any]:
    provenance_id = record["provenance_id"]
    return {
        "node_id": f"provenance:{provenance_id}",
        "entity_type": "provenance",
        "entity_id": provenance_id,
        "label": provenance_id,
        "description": record.get("evidence_text", ""),
        "status": record.get("parser_status", ""),
        "warnings": sorted(_list_text(record.get("warnings"))),
        "fields": {
            "source_relative_path": record.get("source_relative_path", ""),
            "source_role": record.get("source_role", ""),
            "source_sha256": record.get("source_sha256", ""),
            "parser_name": record.get("parser_name", ""),
            "parser_status": record.get("parser_status", ""),
            "evidence_type": record.get("evidence_type", ""),
            "source_locator": record.get("source_locator", ""),
            "evidence_text": record.get("evidence_text", ""),
            "evidence_text_truncated": record.get("evidence_text_truncated", False),
            "confidence": record.get("confidence"),
        },
        "connected_entity_ids": sorted(_list_text(record.get("target_entity_ids"))),
        "provenance_ids": [provenance_id],
        "provenance_precision": provenance_precision(record),
    }


def _source_node(source_file: dict[str, Any]) -> dict[str, Any]:
    rel = source_file["source_relative_path"]
    return {
        "node_id": f"source_file:{rel}",
        "entity_type": "source_file",
        "entity_id": rel,
        "label": rel,
        "description": "",
        "status": source_file.get("parser_status", ""),
        "warnings": sorted(_list_text(source_file.get("warnings"))),
        "fields": dict(source_file),
        "connected_entity_ids": sorted(_list_text(source_file.get("referenced_entity_ids"))),
        "provenance_ids": [],
        "provenance_precision": "not_provided",
    }


def _entity_fields(section: str, entity: dict[str, Any]) -> dict[str, Any]:
    excluded = {"stable_id", "name", "description", "source_references", "traceability_status", "status", "warnings"}
    fields = {key: _clean_field(value) for key, value in entity.items() if key not in excluded}
    fields["asot_section"] = section
    fields["traceability_status"] = _text(entity.get("traceability_status"))
    return {key: fields[key] for key in sorted(fields)}


def _relationship_edges(asot: dict[str, Any], node_by_id: dict[str, str]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    components_by_id = {
        _text(component.get("stable_id")): component
        for component in _items(asot.get("components"))
        if _text(component.get("stable_id"))
    }
    for component in _items(asot.get("components")):
        source = _text(component.get("stable_id"))
        parent_id = _text(component.get("parent_component_id"))
        parent = components_by_id.get(parent_id, {})
        if source and parent_id and source not in _list_text(parent.get("child_component_ids")):
            _add_entity_edge(edges, node_by_id, parent_id, source, "component-child", "")
        for key, rel_type in (
            ("child_component_ids", "component-child"),
            ("interface_ids", "component-interface"),
            ("parameter_ids", "component-parameter"),
            ("behavior_ids", "component-behavior"),
            ("geometry_ids", "component-geometry"),
        ):
            for target in _list_text(component.get(key)):
                _add_entity_edge(edges, node_by_id, source, target, rel_type, "")
    for requirement in _items(asot.get("requirements")):
        source = _text(requirement.get("stable_id"))
        for target in _list_text(requirement.get("satisfied_by_ids")):
            _add_entity_edge(edges, node_by_id, source, target, "requirement-satisfied-by", "")
        for target in _list_text(requirement.get("verified_by_ids")):
            _add_entity_edge(edges, node_by_id, source, target, "requirement-verified-by", "")
    for interface in _items(asot.get("interfaces")):
        source = _text(interface.get("stable_id"))
        for key, rel_type in (("source_component_id", "interface-source-component"), ("target_component_id", "interface-target-component")):
            _add_entity_edge(edges, node_by_id, source, _text(interface.get(key)), rel_type, "")
    for parameter in _items(asot.get("parameters")):
        _add_entity_edge(edges, node_by_id, _text(parameter.get("owning_component_id")), _text(parameter.get("stable_id")), "component-parameter", "")
    for behavior in _items(asot.get("behaviors")):
        _add_entity_edge(edges, node_by_id, _text(behavior.get("owning_component_id")), _text(behavior.get("stable_id")), "component-behavior", "")
    for geometry in _items(asot.get("geometry")):
        _add_entity_edge(edges, node_by_id, _text(geometry.get("owning_component_id")), _text(geometry.get("stable_id")), "component-geometry", "")
    for model in _items(asot.get("physical_models")):
        source = _text(model.get("stable_id"))
        for parameter_id in _list_text(model.get("parameter_ids")):
            _add_entity_edge(edges, node_by_id, source, parameter_id, "physical-model-parameter", "")
        for component_id in _list_text(model.get("owning_component_ids")):
            _add_entity_edge(edges, node_by_id, component_id, source, "component-physical-model", "")
    return edges


def _provenance_edges(
    records: list[dict[str, Any]],
    entity_node_by_id: dict[str, str],
    provenance_node_by_id: dict[str, str],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for record in records:
        provenance_node = provenance_node_by_id.get(record["provenance_id"], "")
        for entity_id in _list_text(record.get("target_entity_ids")):
            entity_node = entity_node_by_id.get(entity_id, "")
            if entity_node and provenance_node:
                edges.append(_edge(entity_node, provenance_node, "entity-provenance", record["source_locator"], record.get("warnings", [])))
    return edges


def _source_edges(
    records: list[dict[str, Any]],
    provenance_node_by_id: dict[str, str],
    source_node_by_path: dict[str, str],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for record in records:
        provenance_node = provenance_node_by_id.get(record["provenance_id"], "")
        source_node = source_node_by_path.get(record["source_relative_path"], "")
        if provenance_node and source_node:
            edges.append(_edge(provenance_node, source_node, "provenance-source-file", record["source_locator"], record.get("warnings", [])))
    return edges


def _add_entity_edge(
    edges: list[dict[str, Any]],
    node_by_id: dict[str, str],
    source_id: str,
    target_id: str,
    relationship_type: str,
    evidence: str,
) -> None:
    if source_id and target_id and source_id in node_by_id and target_id in node_by_id and source_id != target_id:
        edges.append(_edge(node_by_id[source_id], node_by_id[target_id], relationship_type, evidence, []))


def _edge(source_node_id: str, target_node_id: str, relationship_type: str, evidence: str, warnings: Any) -> dict[str, Any]:
    edge_id = f"{relationship_type}:{source_node_id}->{target_node_id}"
    return {
        "edge_id": edge_id,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "relationship_type": relationship_type,
        "source_evidence": _text(evidence),
        "warnings": sorted(_list_text(warnings)),
    }


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for edge in edges:
        deduped.setdefault(edge["edge_id"], edge)
    return list(deduped.values())


def _with_layout(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layer_groups = (
        ("source", ("source_file",)),
        ("provenance", ("provenance",)),
        ("components", ("component",)),
        ("interfaces_behaviors", ("interface", "behavior")),
        ("derived_engineering", ("parameter", "requirement", "physical_model", "geometry")),
    )
    active_layers = [
        layer
        for layer in layer_groups
        if any(node["entity_type"] in layer[1] for node in nodes)
    ]
    layer_index = {
        entity_type: index
        for index, (_layer_name, entity_types) in enumerate(active_layers)
        for entity_type in entity_types
    }
    active_count = max(len(active_layers), 1)
    x_gap = 320 if active_count > 1 else 0
    top = 120
    column_span = 620
    grouped: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        grouped.setdefault(node["entity_type"], []).append(node)
    laid_out = []
    for node in nodes:
        entity_type = node["entity_type"]
        copy = dict(node)
        siblings = grouped.get(entity_type, [])
        index = siblings.index(node)
        count = max(len(siblings), 1)
        lane_offset = _layer_lane_offset(entity_type)
        y_step = 0 if count == 1 else column_span / (count - 1)
        copy["layout"] = {
            "x": 150 + layer_index.get(entity_type, active_count) * x_gap + lane_offset,
            "y": top + index * y_step + _type_y_offset(entity_type),
            "layer": layer_index.get(entity_type, active_count) + 1,
            "shape": _node_shape(entity_type),
            "width": _node_width(entity_type),
            "height": _node_height(entity_type),
            "label_max_chars": 36 if entity_type not in {"provenance", "source_file"} else 30,
        }
        laid_out.append(copy)
    return laid_out


def _layer_lane_offset(entity_type: str) -> int:
    return {
        "behavior": 92,
        "requirement": -74,
        "physical_model": 74,
        "geometry": 148,
    }.get(entity_type, 0)


def _type_y_offset(entity_type: str) -> int:
    return {
        "behavior": 42,
        "requirement": -42,
        "physical_model": 42,
        "geometry": 84,
    }.get(entity_type, 0)


def _node_shape(entity_type: str) -> str:
    return {
        "component": "rounded-rect",
        "requirement": "rect",
        "interface": "round",
        "parameter": "capsule",
        "physical_model": "document",
        "behavior": "hex",
        "geometry": "diamond",
        "provenance": "circle",
        "source_file": "folder",
    }.get(entity_type, "rounded-rect")


def _node_width(entity_type: str) -> int:
    return 96 if entity_type == "provenance" else 206 if entity_type == "source_file" else 190


def _node_height(entity_type: str) -> int:
    return 52 if entity_type == "provenance" else 74


def _with_connected_ids(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_node_id = {node["node_id"]: node for node in nodes}
    connected: dict[str, set[str]] = {node["node_id"]: set(node.get("connected_entity_ids", [])) for node in nodes}
    for edge in edges:
        source = by_node_id.get(edge["source_node_id"])
        target = by_node_id.get(edge["target_node_id"])
        if source and target:
            connected[source["node_id"]].add(target["entity_id"])
            connected[target["node_id"]].add(source["entity_id"])
    normalized = []
    for node in nodes:
        copy = dict(node)
        copy["connected_entity_ids"] = sorted(connected[node["node_id"]])
        normalized.append(copy)
    return normalized


def _metrics(asot: dict[str, Any], records: list[dict[str, Any]], traceability_report: dict[str, Any]) -> dict[str, Any]:
    coverage = traceability_report.get("coverage_summary", {}) if isinstance(traceability_report.get("coverage_summary"), dict) else {}
    precision_counts = {key: 0 for key in PRECISION_VALUES}
    for record in records:
        precision_counts[provenance_precision(record)] += 1
    for _section, _entity_type in ENTITY_SECTIONS:
        for entity in _items(asot.get(_section)):
            status = _normalize_precision(_text(entity.get("traceability_status")))
            if status in {"not_provided", "deferred", "unsupported"}:
                precision_counts[status] += 1
    return {
        "traceability_percentage": coverage.get("traceability_percentage", 100.0),
        "precise_provenance_count": precision_counts["precise"],
        "whole_file_provenance_count": precision_counts["whole_file"],
        "unresolved_count": precision_counts["unresolved"],
        "not_provided_count": precision_counts["not_provided"],
        "deferred_count": precision_counts["deferred"],
        "unsupported_count": precision_counts["unsupported"],
        "broken_reference_count": len(traceability_report.get("broken_provenance_references", []) or []),
        "checksum_mismatch_count": len(traceability_report.get("checksum_mismatches", []) or []),
        "components": len(_items(asot.get("components"))),
        "requirements": len(_items(asot.get("requirements"))),
        "interfaces": len(_items(asot.get("interfaces"))),
        "parameters": len(_items(asot.get("parameters"))),
        "physical_models": len(_items(asot.get("physical_models"))),
        "behaviors": len(_items(asot.get("behaviors"))),
        "geometry": len(_items(asot.get("geometry"))),
        "provenance_records": len(records),
    }


def _traceability_gaps(traceability_report: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = []
    for key, label in (
        ("entities_without_provenance", "entity-without-provenance"),
        ("entities_with_whole_file_only_provenance", "whole-file-only-provenance"),
        ("broken_provenance_references", "broken-reference"),
        ("missing_source_files", "missing-source-file"),
    ):
        for value in sorted(_list_text(traceability_report.get(key))):
            gaps.append({"gap_type": label, "entity_id": value, "description": value})
    for item in traceability_report.get("checksum_mismatches", []) or []:
        if isinstance(item, dict):
            gaps.append(
                {
                    "gap_type": "checksum-mismatch",
                    "entity_id": _text(item.get("source_relative_path")),
                    "description": _text(item.get("source_relative_path")),
                    "expected_sha256": _text(item.get("expected_sha256")),
                    "actual_sha256": _text(item.get("actual_sha256")),
                }
            )
    return sorted(gaps, key=lambda item: (item.get("gap_type", ""), item.get("entity_id", "")))


def _validation(asot: dict[str, Any], provenance_manifest: dict[str, Any], traceability_report: dict[str, Any]) -> dict[str, Any]:
    asot_validation = asot.get("validation", {}) if isinstance(asot.get("validation"), dict) else {}
    errors = sorted(set(_list_text(asot_validation.get("errors")) + _list_text(traceability_report.get("errors"))))
    warnings = sorted(
        set(
            _list_text(asot_validation.get("warnings"))
            + _list_text(provenance_manifest.get("warnings"))
            + _list_text(traceability_report.get("warnings"))
        )
    )
    return {
        "valid": not errors and bool(traceability_report.get("valid", True)),
        "errors": errors,
        "warnings": warnings,
        "asot_valid": not _list_text(asot_validation.get("errors")),
        "traceability_valid": bool(traceability_report.get("valid", True)),
    }


def _provenance_records(provenance_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for record in _items(provenance_manifest.get("provenance_records")):
        evidence = _text(record.get("evidence_text"))
        truncated = len(evidence) > EVIDENCE_TEXT_MAX_CHARS
        if truncated:
            evidence = evidence[:EVIDENCE_TEXT_MAX_CHARS] + "\n[truncated]"
        normalized = {
            "provenance_id": _text(record.get("provenance_id")),
            "source_relative_path": _safe_relative_path(record.get("source_relative_path")),
            "source_sha256": _text(record.get("source_sha256")),
            "source_role": _text(record.get("source_role")),
            "parser_name": _text(record.get("parser_name")),
            "parser_status": _text(record.get("parser_status")),
            "source_locator": _text(record.get("source_locator")),
            "evidence_type": _text(record.get("evidence_type")),
            "evidence_text": evidence,
            "evidence_text_truncated": truncated,
            "confidence": record.get("confidence"),
            "target_entity_ids": sorted(_list_text(record.get("target_entity_ids"))),
            "warnings": sorted(_list_text(record.get("warnings"))),
        }
        if normalized["provenance_id"]:
            records.append(normalized)
    return sorted(records, key=lambda item: item["provenance_id"])


def _source_files(provenance_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    source_files = []
    for item in _items(provenance_manifest.get("source_files")):
        rel = _safe_relative_path(item.get("source_relative_path"))
        if not rel:
            continue
        source_files.append(
            {
                "source_relative_path": rel,
                "role": _text(item.get("role")),
                "size_bytes": item.get("size_bytes", 0),
                "sha256": _text(item.get("sha256")),
                "parser_status": _text(item.get("parser_status")),
                "referenced_entity_ids": sorted(_list_text(item.get("referenced_entity_ids"))),
                "warnings": sorted(_list_text(item.get("warnings"))),
            }
        )
    return sorted(source_files, key=lambda item: item["source_relative_path"])


def _safe_relative_path(value: Any) -> str:
    text = _text(value).replace("\\", "/")
    parts = [part for part in text.split("/") if part and part not in {".", ".."}]
    if ":" in (parts[0] if parts else ""):
        parts = parts[1:]
    return "/".join(parts)


def _normalize_precision(value: str) -> str:
    normalized = value.replace("-", "_")
    if normalized == "whole_file":
        return "whole_file"
    if normalized in PRECISION_VALUES:
        return normalized
    return "unresolved" if normalized else "not_provided"


def _clean_field(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _clean_field(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_clean_field(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({_text(item) for item in value if _text(item)})
    if _text(value):
        return [_text(value)]
    return []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DE2Sim ASOT Traceability Viewer</title>
<style>
:root{color-scheme:light;--ink:#17202a;--muted:#5d6a75;--line:#d7dde3;--panel:#f7f9fb;--canvas:#fbfcfd;--blue:#2563eb;--green:#14843b;--amber:#a16207;--red:#b42318;--violet:#6d28d9;--teal:#0f766e;--rose:#be185d;--slate:#475569;--source:#334155;--edge:#778391}
*{box-sizing:border-box}body{margin:0;height:100vh;display:flex;flex-direction:column;font:14px/1.45 system-ui,-apple-system,Segoe UI,Arial,sans-serif;color:var(--ink);background:#fff;overflow:hidden}
header{flex:0 0 auto;padding:14px 18px;border-bottom:1px solid var(--line);background:#fcfdff}h1{font-size:20px;margin:0 0 6px}.meta{color:var(--muted);display:flex;gap:14px;flex-wrap:wrap}.metrics{display:grid;grid-template-columns:repeat(8,minmax(88px,1fr));gap:7px;margin-top:10px}.metric{border:1px solid var(--line);padding:7px 8px;background:#fff}.metric b{display:block;font-size:18px}
.app{display:grid;grid-template-columns:minmax(190px,15%) minmax(640px,60%) minmax(320px,25%);flex:1 1 auto;min-height:0;min-width:1180px}nav,.details{min-height:0;overflow:auto;border-right:1px solid var(--line);background:var(--panel);padding:12px}.details{border-left:1px solid var(--line);border-right:0;background:#fff}
main{display:flex;flex-direction:column;min-width:0;min-height:0}.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px;border-bottom:1px solid var(--line);background:#fff}input,select,button{font:inherit;border:1px solid var(--line);background:#fff;color:var(--ink);padding:6px 8px}button{cursor:pointer;border-radius:4px}button.active,.navitem.active{background:var(--blue);color:#fff}.navitem{width:100%;display:flex;justify-content:space-between;margin-bottom:5px;text-align:left}.filters{display:flex;gap:6px;flex-wrap:wrap}.chip{display:inline-flex;gap:5px;align-items:center;border:1px solid var(--line);padding:4px 6px;background:#fff;border-radius:4px;white-space:nowrap}.mode-button{font-weight:700}
#graphWrap{position:relative;flex:1;min-height:0;overflow:hidden;background:var(--canvas);cursor:grab}#graphWrap.panning{cursor:grabbing}svg{display:block;width:100%;height:100%;min-height:0;touch-action:none}.edge{stroke:var(--edge);stroke-width:2.1;fill:none;marker-end:url(#arrow-default)}.edge-label{font-size:11px;fill:#42505d;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}.edge-rel-entity-provenance,.edge-rel-provenance-source-file{stroke-dasharray:7 5}.edge-rel-requirement-satisfied-by{stroke:var(--green)}.edge-rel-requirement-verified-by{stroke:var(--teal)}.edge-rel-component-child{stroke:var(--blue)}.edge-rel-component-parameter{stroke:var(--amber)}.edge-rel-component-behavior{stroke:var(--rose)}.edge-rel-component-geometry{stroke:var(--slate)}.edge-rel-physical-model-parameter{stroke:var(--violet)}.edge.is-faded,.node.is-faded{opacity:.16}.edge.is-highlighted{stroke:var(--blue);stroke-width:4;marker-end:url(#arrow-highlight)}.node-shape{stroke:#fff;stroke-width:2.5;filter:drop-shadow(0 1px 1px rgba(23,32,42,.18))}.node text{font-size:15px;font-weight:700;pointer-events:none;fill:#fff}.node-type-provenance text{font-size:12px}.node.selected .node-shape,.node.hovered .node-shape{stroke:#111;stroke-width:4}.node.hovered{transform-box:fill-box;transform-origin:center}
.node-type-component .node-shape,.legend-component{fill:var(--blue)}.node-type-requirement .node-shape,.legend-requirement{fill:var(--green)}.node-type-interface .node-shape,.legend-interface{fill:var(--teal)}.node-type-parameter .node-shape,.legend-parameter{fill:var(--amber)}.node-type-physical-model .node-shape,.legend-physical-model{fill:var(--violet)}.node-type-behavior .node-shape,.legend-behavior{fill:var(--rose)}.node-type-geometry .node-shape,.legend-geometry{fill:var(--slate)}.node-type-provenance .node-shape,.legend-provenance{fill:#9333ea}.node-type-source-file .node-shape,.legend-source-file{fill:var(--source)}
.legend{position:absolute;left:12px;bottom:12px;display:grid;grid-template-columns:repeat(2,max-content);gap:4px 12px;padding:8px;border:1px solid var(--line);background:rgba(255,255,255,.94);font-size:12px}.legend-item{display:flex;gap:6px;align-items:center}.legend-swatch{width:14px;height:14px;border-radius:3px}.tooltip{position:absolute;z-index:5;max-width:320px;padding:8px;border:1px solid var(--line);background:#fff;color:var(--ink);box-shadow:0 4px 14px rgba(23,32,42,.18);pointer-events:none}.tooltip b{display:block}.tooltip div{word-break:break-word}
h2{font-size:15px;margin:14px 0 8px}.notice{font-size:12px;color:var(--muted);margin:6px 0}.compact-list{margin:0;padding-left:18px}.compact-list li{margin:2px 0}.section-title{position:sticky;top:-12px;background:inherit;padding:7px 0;border-bottom:1px solid var(--line);z-index:1}dl{margin:0}.kv{display:grid;grid-template-columns:minmax(96px,32%) minmax(0,1fr);column-gap:14px;row-gap:4px;align-items:start;padding:7px 0;border-bottom:1px solid #eef1f4}.kv>*{min-width:0}dt{font-weight:700;overflow-wrap:anywhere;word-break:break-word}dd{margin:0;color:var(--muted);overflow-wrap:anywhere;word-break:break-word;white-space:pre-wrap}.wrap-anywhere{overflow-wrap:anywhere;word-break:break-word}details{border:1px solid var(--line);background:#fff;margin:8px 0;padding:7px}summary{cursor:pointer;font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;background:var(--panel);border:1px solid var(--line);padding:8px;max-height:220px;overflow:auto}.warn{color:var(--red)}.ok{color:var(--green)}.trace-heading{font-size:12px;font-weight:700;color:var(--muted);margin:0 0 6px}.summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.pill{padding:6px;border-left:4px solid var(--line);background:#fff;overflow-wrap:anywhere}.precise{border-color:var(--green)}.whole{border-color:var(--amber)}.bad{border-color:var(--red)}
@media(max-width:1279px){body{overflow:auto}.app{min-width:0;grid-template-columns:minmax(170px,15%) minmax(520px,60%) minmax(280px,25%)}}@media(max-width:1000px){body{overflow:auto}.app{height:auto;display:block}.details,nav{max-height:360px;border:0;border-bottom:1px solid var(--line)}svg{height:620px}.metrics{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <div class="meta" id="headerMeta"></div>
  <div class="metrics" id="headerMetrics"></div>
</header>
<div class="app">
  <nav>
    <h2>Categories</h2>
    <div id="categories"></div>
    <h2>Traceability</h2>
    <div class="trace-heading" id="traceHeading"></div>
    <div class="summary" id="traceSummary"></div>
    <h2>Limitations</h2>
    <ul id="limitations"></ul>
  </nav>
  <main>
    <div class="toolbar">
      <input id="search" type="search" placeholder="Search ID, name, text, source path" size="34">
      <select id="precision"><option value="">All precision</option><option>precise</option><option>whole_file</option><option>unresolved</option><option>not_provided</option><option>deferred</option><option>unsupported</option></select>
      <label class="chip"><input id="warnOnly" type="checkbox"> warnings</label>
      <button id="engineeringOnly" class="mode-button" type="button">Show engineering only</button>
      <button id="showTraceability" class="mode-button active" type="button">Show traceability</button>
      <button id="zoomIn" type="button">Zoom in</button><button id="zoomOut" type="button">Zoom out</button><button id="reset" type="button">Reset</button><button id="fitGraph" type="button">Fit graph</button>
      <div class="filters" id="typeFilters"></div>
    </div>
    <div id="graphWrap"><svg id="graph" role="img" aria-label="ASOT traceability graph"></svg><div id="legend" class="legend" aria-label="Graph legend"></div><div id="tooltip" class="tooltip" hidden></div></div>
  </main>
  <aside class="details">
    <section><h2 class="section-title">Entity Details</h2><div id="details"></div></section>
    <section><h2 class="section-title">Source Evidence</h2><div id="evidence"></div></section>
    <section><h2 class="section-title">Traceability Gaps</h2><div id="gaps"></div></section>
  </aside>
</div>
<script id="viewer-data" type="application/json">__VIEWER_DATA_JSON__</script>
<script>
"use strict";
const data = JSON.parse(document.getElementById("viewer-data").textContent);
const state = {selected:null,hovered:null,category:"System Overview",types:new Set(),precision:"",warnOnly:false,traceability:true,query:"",viewBox:null,drag:null};
const svg = document.getElementById("graph");
const wrap = document.getElementById("graphWrap");
const tooltip = document.getElementById("tooltip");
const ns = "http://www.w3.org/2000/svg";
const typeNames = [...new Set(data.nodes.map(n=>n.entity_type))].sort();
typeNames.forEach(t=>state.types.add(t));
function txt(el,value){el.textContent = value == null ? "" : String(value);}
function child(tag,parent,attrs){const svgTags=new Set(["svg","g","line","circle","text","rect","path","polygon","defs","marker","title"]);const el = svgTags.has(tag) ? document.createElementNS(ns,tag) : document.createElement(tag);for(const k in attrs||{})el.setAttribute(k,attrs[k]);parent.appendChild(el);return el;}
function clear(el){while(el.firstChild)el.removeChild(el.firstChild);}
function classType(t){return t.replaceAll("_","-");}
function edgeClass(t){return t.replaceAll("_","-").replaceAll(" ","-");}
function matches(node){if(!state.traceability && (node.entity_type==="provenance"||node.entity_type==="source_file"))return false;if(!state.types.has(node.entity_type))return false;if(state.precision && node.provenance_precision!==state.precision)return false;if(state.warnOnly && (!node.warnings||node.warnings.length===0))return false;if(state.category!=="System Overview"){const map={"Components":"component","Requirements":"requirement","Interfaces":"interface","Parameters":"parameter","Physical Models":"physical_model","Behaviors":"behavior","Geometry":"geometry","Source Files":"source_file"};if(map[state.category]&&node.entity_type!==map[state.category])return false;if(state.category==="Traceability Gaps")return false}if(state.query){const hay=JSON.stringify(node).toLowerCase();if(!hay.includes(state.query.toLowerCase()))return false}return true}
function renderHeader(){txt(document.getElementById("title"), data.metadata.title || data.metadata.source_package_filename || "ASOT Traceability Viewer");const meta=document.getElementById("headerMeta");clear(meta);["ASOT "+data.metadata.asot_id,"schema "+data.metadata.asot_schema_version,"coverage "+data.metrics.traceability_percentage+"%","validation "+(data.validation.valid?"valid":"invalid")].forEach(v=>{const s=document.createElement("span");txt(s,v);meta.appendChild(s)});const hm=document.getElementById("headerMetrics");clear(hm);[["Components",data.metrics.components],["Requirements",data.metrics.requirements],["Interfaces",data.metrics.interfaces],["Parameters",data.metrics.parameters],["Physical models",data.metrics.physical_models],["Behaviors",data.metrics.behaviors],["Geometry",data.metrics.geometry],["Provenance",data.metrics.provenance_records]].forEach(([k,v])=>{const d=document.createElement("div");d.className="metric";const b=document.createElement("b");txt(b,v);d.appendChild(b);d.appendChild(document.createTextNode(k));hm.appendChild(d)})}
function renderNav(){const cats=[["System Overview",data.nodes.length],["Components",data.metrics.components],["Requirements",data.metrics.requirements],["Interfaces",data.metrics.interfaces],["Parameters",data.metrics.parameters],["Physical Models",data.metrics.physical_models],["Behaviors",data.metrics.behaviors],["Geometry",data.metrics.geometry],["Source Files",data.source_files.length],["Traceability Gaps",data.traceability_gaps.length]];const c=document.getElementById("categories");clear(c);cats.forEach(([name,count])=>{const b=document.createElement("button");b.className="navitem"+(state.category===name?" active":"");b.type="button";b.addEventListener("click",()=>{state.category=name;if(name==="System Overview"){typeNames.forEach(t=>state.types.add(t));renderFilters()}state.selected=null;renderAll(true)});const l=document.createElement("span");const r=document.createElement("span");txt(l,name);txt(r,count);b.appendChild(l);b.appendChild(r);c.appendChild(b)});txt(document.getElementById("traceHeading"),"Traceability coverage for this processed package");const ts=document.getElementById("traceSummary");clear(ts);[["Coverage",data.metrics.traceability_percentage+"%","precise"],["Precise",data.metrics.precise_provenance_count,"precise"],["Whole-file",data.metrics.whole_file_provenance_count,"whole"],["Unresolved",data.metrics.unresolved_count,"bad"],["Not provided",data.metrics.not_provided_count,"bad"]].forEach(([k,v,cls])=>{const p=document.createElement("div");p.className="pill "+cls;txt(p,k+": "+v);ts.appendChild(p)});const lim=document.getElementById("limitations");clear(lim);lim.className="compact-list";data.limitations.forEach(x=>{const li=document.createElement("li");txt(li,x);lim.appendChild(li)})}
function renderFilters(){const f=document.getElementById("typeFilters");clear(f);typeNames.forEach(t=>{const label=document.createElement("label");label.className="chip";const box=document.createElement("input");box.type="checkbox";box.checked=state.types.has(t);box.addEventListener("change",()=>{box.checked?state.types.add(t):state.types.delete(t);state.selected=null;renderAll(true)});label.appendChild(box);label.appendChild(document.createTextNode(t));f.appendChild(label)})}
function visibleGraph(){const nodes=data.nodes.filter(matches);const nodeIds=new Set(nodes.map(n=>n.node_id));const edges=data.edges.filter(e=>nodeIds.has(e.source_node_id)&&nodeIds.has(e.target_node_id));return {nodes,edges,nodeIds};}
function selectedNode(graph){const visible=graph||visibleGraph();return visible.nodes.find(n=>n.node_id===state.selected)||visible.nodes[0]||null}
function connectedIds(id){const ids=new Set([id]);data.edges.forEach(e=>{if(e.source_node_id===id)ids.add(e.target_node_id);if(e.target_node_id===id)ids.add(e.source_node_id)});return ids}
function connectedEdges(id){const ids=new Set();data.edges.forEach(e=>{if(e.source_node_id===id||e.target_node_id===id)ids.add(e.edge_id)});return ids}
function nodeBounds(node){const w=node.layout.width||170,h=node.layout.height||64;return {minX:node.layout.x-w/2,minY:node.layout.y-h/2,maxX:node.layout.x+w/2,maxY:node.layout.y+h/2};}
function graphBounds(nodes){if(nodes.length===0)return {minX:0,minY:0,maxX:900,maxY:620,width:900,height:620};let b={minX:Infinity,minY:Infinity,maxX:-Infinity,maxY:-Infinity};nodes.forEach(n=>{const nb=nodeBounds(n);b.minX=Math.min(b.minX,nb.minX);b.minY=Math.min(b.minY,nb.minY);b.maxX=Math.max(b.maxX,nb.maxX);b.maxY=Math.max(b.maxY,nb.maxY)});b.width=Math.max(1,b.maxX-b.minX);b.height=Math.max(1,b.maxY-b.minY);return b;}
function setViewBox(v){state.viewBox=v;svg.setAttribute("viewBox",[v.x,v.y,v.w,v.h].join(" "));}
function fitGraph(){const graph=visibleGraph();const b=graphBounds(graph.nodes);const pad=90;const ratio=Math.max(1,svg.clientWidth)/Math.max(1,svg.clientHeight);let w=b.width+pad*2,h=b.height+pad*2;if(w/h<ratio)w=h*ratio;else h=w/ratio;setViewBox({x:(b.minX+b.maxX-w)/2,y:(b.minY+b.maxY-h)/2,w:w,h:h});}
function keepGraphReachable(){if(!state.viewBox)return;const b=graphBounds(visibleGraph().nodes);const limitX=Math.max(b.width,state.viewBox.w)*1.2;const limitY=Math.max(b.height,state.viewBox.h)*1.2;const cx=Math.min(Math.max(state.viewBox.x+state.viewBox.w/2,b.minX-limitX),b.maxX+limitX);const cy=Math.min(Math.max(state.viewBox.y+state.viewBox.h/2,b.minY-limitY),b.maxY+limitY);setViewBox({x:cx-state.viewBox.w/2,y:cy-state.viewBox.h/2,w:state.viewBox.w,h:state.viewBox.h});}
function clientPoint(evt){const r=svg.getBoundingClientRect();return {x:state.viewBox.x+(evt.clientX-r.left)/Math.max(1,r.width)*state.viewBox.w,y:state.viewBox.y+(evt.clientY-r.top)/Math.max(1,r.height)*state.viewBox.h};}
function zoomAt(factor,evt){if(!state.viewBox)fitGraph();const p=evt?clientPoint(evt):{x:state.viewBox.x+state.viewBox.w/2,y:state.viewBox.y+state.viewBox.h/2};const nw=Math.min(5000,Math.max(120,state.viewBox.w*factor));const nh=Math.min(5000,Math.max(90,state.viewBox.h*factor));const rx=(p.x-state.viewBox.x)/state.viewBox.w;const ry=(p.y-state.viewBox.y)/state.viewBox.h;setViewBox({x:p.x-rx*nw,y:p.y-ry*nh,w:nw,h:nh});keepGraphReachable();}
function truncated(node){const label=String(node.label||node.entity_id||node.node_id);const max=node.layout.label_max_chars||34;return label.length>max?label.slice(0,max-1)+"...":label;}
function addShape(group,node){const w=node.layout.width||170,h=node.layout.height||64,shape=node.layout.shape;const attrs={class:"node-shape"};if(shape==="circle")return child("circle",group,{...attrs,r:24});if(shape==="diamond")return child("polygon",group,{...attrs,points:"0 "+(-h/2)+" "+(w/2)+" 0 0 "+(h/2)+" "+(-w/2)+" 0"});if(shape==="hex")return child("polygon",group,{...attrs,points:(-w/2+20)+" "+(-h/2)+" "+(w/2-20)+" "+(-h/2)+" "+(w/2)+" 0 "+(w/2-20)+" "+(h/2)+" "+(-w/2+20)+" "+(h/2)+" "+(-w/2)+" 0"});if(shape==="document")return child("path",group,{...attrs,d:"M"+(-w/2)+" "+(-h/2)+" H"+(w/2-22)+" L"+(w/2)+" "+(-h/2+22)+" V"+(h/2)+" H"+(-w/2)+" Z"});if(shape==="folder")return child("path",group,{...attrs,d:"M"+(-w/2)+" "+(-h/2+12)+" H"+(-w/2+62)+" L"+(-w/2+78)+" "+(-h/2)+" H"+(w/2)+" V"+(h/2)+" H"+(-w/2)+" Z"});const rx=shape==="capsule"?h/2:shape==="rounded-rect"?10:0;return child("rect",group,{...attrs,x:-w/2,y:-h/2,width:w,height:h,rx:rx,ry:rx});}
function showTooltip(evt,node){clear(tooltip);const b=document.createElement("b");txt(b,node.entity_type);tooltip.appendChild(b);[node.label,node.entity_id,node.node_id].forEach(v=>{const d=document.createElement("div");txt(d,v);tooltip.appendChild(d)});tooltip.hidden=false;const r=wrap.getBoundingClientRect();tooltip.style.left=Math.min(r.width-340,Math.max(8,evt.clientX-r.left+14))+"px";tooltip.style.top=Math.max(8,evt.clientY-r.top+14)+"px";}
function hideTooltip(){tooltip.hidden=true;}
function renderDefs(){const defs=child("defs",svg,{});const m=child("marker",defs,{id:"arrow-default",viewBox:"0 0 10 10",refX:"9",refY:"5",markerWidth:"7",markerHeight:"7",orient:"auto-start-reverse"});child("path",m,{d:"M 0 0 L 10 5 L 0 10 z",fill:"var(--edge)"});const h=child("marker",defs,{id:"arrow-highlight",viewBox:"0 0 10 10",refX:"9",refY:"5",markerWidth:"8",markerHeight:"8",orient:"auto-start-reverse"});child("path",h,{d:"M 0 0 L 10 5 L 0 10 z",fill:"var(--blue)"});}
function renderGraph(shouldFit){clear(svg);renderDefs();const graph=visibleGraph();const selectedDetails=selectedNode(graph);const selectedNodeId=selectedDetails?selectedDetails.node_id:null;const focus=state.hovered||selectedNodeId;const selected=focus?connectedIds(focus):null;const selectedEdges=focus?connectedEdges(focus):new Set();const g=child("g",svg,{});graph.edges.forEach(e=>{const a=data.nodes.find(n=>n.node_id===e.source_node_id),b=data.nodes.find(n=>n.node_id===e.target_node_id);if(!a||!b)return;const isLinked=selectedEdges.has(e.edge_id);const faded=selected&&!isLinked;const cls="edge edge-rel-"+edgeClass(e.relationship_type)+(faded?" is-faded":"")+(isLinked?" is-highlighted":"");child("line",g,{x1:a.layout.x,y1:a.layout.y,x2:b.layout.x,y2:b.layout.y,class:cls});const dx=b.layout.x-a.layout.x,dy=b.layout.y-a.layout.y;if(Math.sqrt(dx*dx+dy*dy)>150){const label=child("text",g,{x:(a.layout.x+b.layout.x)/2,y:(a.layout.y+b.layout.y)/2-6,class:"edge-label"+(faded?" is-faded":"")});txt(label,e.relationship_type)}});graph.nodes.forEach(n=>{const isConnected=selected&&selected.has(n.node_id);const faded=selected&&!isConnected;const group=child("g",g,{class:"node node-type-"+classType(n.entity_type)+(n.node_id===selectedNodeId?" selected":"")+(n.node_id===state.hovered?" hovered":"")+(faded?" is-faded":""),transform:"translate("+n.layout.x+" "+n.layout.y+")"});group.addEventListener("click",evt=>{evt.stopPropagation();state.selected=n.node_id;renderGraph(false);renderDetails()});group.addEventListener("mousemove",evt=>showTooltip(evt,n));group.addEventListener("mouseenter",()=>{state.hovered=n.node_id;renderGraph(false)});group.addEventListener("mouseleave",()=>{state.hovered=null;hideTooltip();renderGraph(false)});addShape(group,n);const title=child("title",group,{});txt(title,n.entity_type+": "+n.label+" ("+n.node_id+")");const label=child("text",group,{x:0,y:5,"text-anchor":"middle"});txt(label,truncated(n))});if(shouldFit||!state.viewBox)fitGraph();else setViewBox(state.viewBox);}
function renderDetails(){const node=selectedNode();const d=document.getElementById("details");clear(d);if(!node){txt(d,"No matching node.");renderEvidence(null);return}function row(parent,k,v){const div=document.createElement("div");div.className="kv";const dt=document.createElement("dt"),dd=document.createElement("dd");dd.className="wrap-anywhere";txt(dt,k);txt(dd,Array.isArray(v)?v.join(", ")||"None":typeof v==="object"?JSON.stringify(v,null,2):v||"None");div.appendChild(dt);div.appendChild(dd);parent.appendChild(div)}const dl=document.createElement("dl");d.appendChild(dl);row(dl,"entity type",node.entity_type);row(dl,"stable ID",node.entity_id);row(dl,"full label",node.label);row(dl,"description",node.description);row(dl,"status",node.status);row(dl,"warnings",(node.warnings||[]).join("; "));row(dl,"connected IDs",node.connected_entity_ids||[]);row(dl,"precision",node.provenance_precision);row(dl,"provenance IDs",node.provenance_ids||[]);const raw=document.createElement("details");const summary=document.createElement("summary");txt(summary,"Raw fields");raw.appendChild(summary);const rawPre=document.createElement("pre");txt(rawPre,JSON.stringify(node.fields||{},null,2));raw.appendChild(rawPre);d.appendChild(raw);const prov=document.createElement("details");const ps=document.createElement("summary");txt(ps,"Provenance records");prov.appendChild(ps);const pp=document.createElement("pre");const records=data.nodes.filter(n=>n.entity_type==="provenance"&&(node.provenance_ids||[]).includes(n.entity_id));txt(pp,records.length?JSON.stringify(records.map(r=>r.fields),null,2):"No source evidence available");prov.appendChild(pp);d.appendChild(prov);renderEvidence(node)}
function renderEvidence(node){const e=document.getElementById("evidence");clear(e);if(!node){txt(e,"No source evidence available");return}const records=data.nodes.filter(n=>n.entity_type==="provenance"&&(node.provenance_ids||[]).includes(n.entity_id));if(node.entity_type==="provenance")records.push(node);if(records.length===0){txt(e,"No source evidence available");return}records.forEach(r=>{const dl=document.createElement("dl");e.appendChild(dl);["source_relative_path","source_role","source_sha256","parser_name","parser_status","evidence_type","source_locator","confidence"].forEach(k=>{const div=document.createElement("div");div.className="kv";const dt=document.createElement("dt"),dd=document.createElement("dd");dd.className="wrap-anywhere";txt(dt,k);txt(dd,r.fields[k]);div.appendChild(dt);div.appendChild(dd);dl.appendChild(div)});const pre=document.createElement("pre");txt(pre,r.fields.evidence_text_truncated?r.fields.evidence_text+"\\n(truncated to "+data.metadata.evidence_text_max_chars+" chars)":r.fields.evidence_text);e.appendChild(pre);if(r.warnings&&r.warnings.length){const w=document.createElement("div");w.className="warn";txt(w,r.warnings.join("; "));e.appendChild(w)}})}
function renderGaps(){const g=document.getElementById("gaps");clear(g);if(data.traceability_gaps.length===0){const ok=document.createElement("div");ok.className="ok";txt(ok,"No traceability gaps reported.");g.appendChild(ok);return}data.traceability_gaps.forEach(x=>{const p=document.createElement("div");p.className="pill bad";txt(p,x.gap_type+": "+x.description);g.appendChild(p)})}
function renderLegend(){const legend=document.getElementById("legend");clear(legend);typeNames.forEach(t=>{const item=document.createElement("div");item.className="legend-item";const sw=document.createElement("span");sw.className="legend-swatch legend-"+classType(t);const label=document.createElement("span");txt(label,t.replaceAll("_"," "));item.appendChild(sw);item.appendChild(label);legend.appendChild(item)})}
function renderModes(){document.getElementById("engineeringOnly").classList.toggle("active",!state.traceability);document.getElementById("showTraceability").classList.toggle("active",state.traceability);}
function renderAll(shouldFit){renderHeader();renderNav();renderModes();renderGraph(shouldFit);renderDetails();renderGaps();renderLegend()}
document.getElementById("search").addEventListener("input",e=>{state.query=e.target.value;state.selected=null;renderAll(true)});
document.getElementById("precision").addEventListener("change",e=>{state.precision=e.target.value;state.selected=null;renderAll(true)});
document.getElementById("warnOnly").addEventListener("change",e=>{state.warnOnly=e.target.checked;state.selected=null;renderAll(true)});
document.getElementById("engineeringOnly").addEventListener("click",()=>{state.traceability=false;state.selected=null;renderAll(true)});
document.getElementById("showTraceability").addEventListener("click",()=>{state.traceability=true;state.selected=null;renderAll(true)});
document.getElementById("zoomIn").addEventListener("click",()=>zoomAt(.82));
document.getElementById("zoomOut").addEventListener("click",()=>zoomAt(1.22));
document.getElementById("reset").addEventListener("click",()=>{state.selected=null;state.hovered=null;fitGraph();renderAll(false)});
document.getElementById("fitGraph").addEventListener("click",()=>fitGraph());
svg.addEventListener("wheel",evt=>{evt.preventDefault();zoomAt(evt.deltaY < 0 ? 0.86 : 1.16,evt)},{passive:false});
svg.addEventListener("pointerdown",evt=>{if(evt.button!==0)return;wrap.classList.add("panning");state.drag={x:evt.clientX,y:evt.clientY,box:{...state.viewBox}};svg.setPointerCapture(evt.pointerId)});
svg.addEventListener("pointermove",evt=>{if(!state.drag)return;const r=svg.getBoundingClientRect();const dx=(evt.clientX-state.drag.x)/Math.max(1,r.width)*state.drag.box.w;const dy=(evt.clientY-state.drag.y)/Math.max(1,r.height)*state.drag.box.h;setViewBox({x:state.drag.box.x-dx,y:state.drag.box.y-dy,w:state.drag.box.w,h:state.drag.box.h});keepGraphReachable()});
svg.addEventListener("pointerup",evt=>{state.drag=null;wrap.classList.remove("panning");try{svg.releasePointerCapture(evt.pointerId)}catch(_err){}});
svg.addEventListener("click",()=>{state.selected=null;renderGraph(false);renderDetails()});
window.addEventListener("resize",()=>fitGraph());
renderFilters();renderAll();
</script>
</body>
</html>
"""
