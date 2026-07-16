"""Standalone ASOT traceability viewer generation for DE2Sim Phase 3B."""

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
    lanes = {
        "requirement": 0,
        "component": 1,
        "interface": 2,
        "parameter": 3,
        "physical_model": 4,
        "behavior": 5,
        "geometry": 6,
        "provenance": 7,
        "source_file": 8,
    }
    counters: dict[str, int] = {}
    laid_out = []
    for node in nodes:
        entity_type = node["entity_type"]
        index = counters.get(entity_type, 0)
        counters[entity_type] = index + 1
        copy = dict(node)
        copy["layout"] = {"x": 120 + lanes.get(entity_type, 9) * 190, "y": 90 + index * 86}
        laid_out.append(copy)
    return laid_out


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
:root{color-scheme:light;--ink:#17202a;--muted:#5d6a75;--line:#d7dde3;--panel:#f7f9fb;--blue:#2563eb;--green:#14843b;--amber:#a16207;--red:#b42318;--violet:#6d28d9;--teal:#0f766e}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,-apple-system,Segoe UI,Arial,sans-serif;color:var(--ink);background:#fff}
header{padding:16px 20px;border-bottom:1px solid var(--line);background:#fcfdff}h1{font-size:20px;margin:0 0 6px}.meta{color:var(--muted);display:flex;gap:14px;flex-wrap:wrap}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:12px}.metric{border:1px solid var(--line);padding:8px;background:#fff}.metric b{display:block;font-size:18px}
.app{display:grid;grid-template-columns:230px minmax(420px,1fr) 360px;min-height:calc(100vh - 138px)}nav,.details{border-right:1px solid var(--line);background:var(--panel);padding:12px;overflow:auto}.details{border-left:1px solid var(--line);border-right:0;background:#fff}
main{display:flex;flex-direction:column;min-width:0}.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px;border-bottom:1px solid var(--line)}input,select,button{font:inherit;border:1px solid var(--line);background:#fff;color:var(--ink);padding:6px 8px}button{cursor:pointer}button.active{background:var(--blue);color:#fff}.navitem{width:100%;display:flex;justify-content:space-between;margin-bottom:5px;text-align:left}.filters{display:flex;gap:6px;flex-wrap:wrap}.chip{display:inline-flex;gap:4px;align-items:center;border:1px solid var(--line);padding:4px 6px;background:#fff}
#graphWrap{position:relative;flex:1;overflow:hidden;background:#fbfcfd}svg{width:100%;height:100%;min-height:560px}.edge{stroke:#8a97a3;stroke-width:1.4}.edge.dim,.node.dim{opacity:.15}.edge.highlight{stroke:var(--blue);stroke-width:3}.node circle{stroke:#fff;stroke-width:2}.node text{font-size:12px;pointer-events:none}.node.selected circle{stroke:#111;stroke-width:3}
.type-component{fill:var(--blue)}.type-requirement{fill:var(--green)}.type-interface{fill:var(--teal)}.type-parameter{fill:var(--amber)}.type-physical_model{fill:var(--violet)}.type-behavior{fill:#db2777}.type-geometry{fill:#64748b}.type-provenance{fill:#9333ea}.type-source_file{fill:#334155}
h2{font-size:15px;margin:14px 0 8px}dl{margin:0}dt{font-weight:700;margin-top:8px}dd{margin:2px 0 0;color:var(--muted);word-break:break-word}pre{white-space:pre-wrap;word-break:break-word;background:var(--panel);border:1px solid var(--line);padding:8px;max-height:220px;overflow:auto}.warn{color:var(--red)}.ok{color:var(--green)}.summary{display:grid;grid-template-columns:repeat(2,1fr);gap:6px}.pill{padding:6px;border-left:4px solid var(--line);background:var(--panel)}.precise{border-color:var(--green)}.whole{border-color:var(--amber)}.bad{border-color:var(--red)}
@media(max-width:1000px){.app{grid-template-columns:1fr}.details,nav{border:0;border-bottom:1px solid var(--line)}}
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
    <div class="summary" id="traceSummary"></div>
    <h2>Limitations</h2>
    <ul id="limitations"></ul>
  </nav>
  <main>
    <div class="toolbar">
      <input id="search" type="search" placeholder="Search ID, name, text, source path" size="34">
      <select id="precision"><option value="">All precision</option><option>precise</option><option>whole_file</option><option>unresolved</option><option>not_provided</option><option>deferred</option><option>unsupported</option></select>
      <label class="chip"><input id="warnOnly" type="checkbox"> warnings</label>
      <label class="chip"><input id="hideProv" type="checkbox"> hide provenance/source</label>
      <button id="zoomIn">+</button><button id="zoomOut">-</button><button id="reset">Reset</button>
      <div class="filters" id="typeFilters"></div>
    </div>
    <div id="graphWrap"><svg id="graph" role="img" aria-label="ASOT traceability graph"></svg></div>
  </main>
  <aside class="details">
    <section><h2>Entity Details</h2><div id="details"></div></section>
    <section><h2>Source Evidence</h2><div id="evidence"></div></section>
    <section><h2>Traceability Gaps</h2><div id="gaps"></div></section>
  </aside>
</div>
<script id="viewer-data" type="application/json">__VIEWER_DATA_JSON__</script>
<script>
"use strict";
const data = JSON.parse(document.getElementById("viewer-data").textContent);
const state = {selected:null,scale:1,category:"System Overview",types:new Set(),precision:"",warnOnly:false,hideProv:false,query:""};
const svg = document.getElementById("graph");
const ns = "http://www.w3.org/2000/svg";
const typeNames = [...new Set(data.nodes.map(n=>n.entity_type))].sort();
typeNames.forEach(t=>state.types.add(t));
function txt(el,value){el.textContent = value == null ? "" : String(value);}
function child(tag,parent,attrs){const el = tag==="svg"||tag==="g"||tag==="line"||tag==="circle"||tag==="text" ? document.createElementNS(ns,tag) : document.createElement(tag);for(const k in attrs||{})el.setAttribute(k,attrs[k]);parent.appendChild(el);return el;}
function clear(el){while(el.firstChild)el.removeChild(el.firstChild);}
function matches(node){if(state.hideProv && (node.entity_type==="provenance"||node.entity_type==="source_file"))return false;if(!state.types.has(node.entity_type))return false;if(state.precision && node.provenance_precision!==state.precision)return false;if(state.warnOnly && (!node.warnings||node.warnings.length===0))return false;if(state.category!=="System Overview"){const map={"Components":"component","Requirements":"requirement","Interfaces":"interface","Parameters":"parameter","Physical Models":"physical_model","Behaviors":"behavior","Geometry":"geometry","Source Files":"source_file","Traceability Gaps":"gap"};if(map[state.category]&&node.entity_type!==map[state.category])return false}if(state.query){const hay=JSON.stringify(node).toLowerCase();if(!hay.includes(state.query.toLowerCase()))return false}return true}
function renderHeader(){txt(document.getElementById("title"), data.metadata.title || data.metadata.source_package_filename || "ASOT Traceability Viewer");const meta=document.getElementById("headerMeta");clear(meta);["ASOT "+data.metadata.asot_id,"schema "+data.metadata.asot_schema_version,"traceability "+data.metrics.traceability_percentage+"%","validation "+(data.validation.valid?"valid":"invalid")].forEach(v=>{const s=document.createElement("span");txt(s,v);meta.appendChild(s)});const hm=document.getElementById("headerMetrics");clear(hm);[["Components",data.metrics.components],["Requirements",data.metrics.requirements],["Interfaces",data.metrics.interfaces],["Parameters",data.metrics.parameters],["Physical models",data.metrics.physical_models],["Behaviors",data.metrics.behaviors],["Geometry",data.metrics.geometry],["Provenance",data.metrics.provenance_records]].forEach(([k,v])=>{const d=document.createElement("div");d.className="metric";const b=document.createElement("b");txt(b,v);d.appendChild(b);d.appendChild(document.createTextNode(k));hm.appendChild(d)})}
function renderNav(){const cats=[["System Overview",data.nodes.length],["Components",data.metrics.components],["Requirements",data.metrics.requirements],["Interfaces",data.metrics.interfaces],["Parameters",data.metrics.parameters],["Physical Models",data.metrics.physical_models],["Behaviors",data.metrics.behaviors],["Geometry",data.metrics.geometry],["Source Files",data.source_files.length],["Traceability Gaps",data.traceability_gaps.length]];const c=document.getElementById("categories");clear(c);cats.forEach(([name,count])=>{const b=document.createElement("button");b.className="navitem"+(state.category===name?" active":"");b.addEventListener("click",()=>{state.category=name;renderAll()});const l=document.createElement("span");const r=document.createElement("span");txt(l,name);txt(r,count);b.appendChild(l);b.appendChild(r);c.appendChild(b)});const ts=document.getElementById("traceSummary");clear(ts);[["precise",data.metrics.precise_provenance_count,"precise"],["whole-file",data.metrics.whole_file_provenance_count,"whole"],["unresolved",data.metrics.unresolved_count,"bad"],["not-provided",data.metrics.not_provided_count,"bad"],["deferred",data.metrics.deferred_count,"bad"],["broken refs",data.metrics.broken_reference_count,"bad"],["checksum",data.metrics.checksum_mismatch_count,"bad"]].forEach(([k,v,cls])=>{const p=document.createElement("div");p.className="pill "+cls;txt(p,k+": "+v);ts.appendChild(p)});const lim=document.getElementById("limitations");clear(lim);data.limitations.forEach(x=>{const li=document.createElement("li");txt(li,x);lim.appendChild(li)})}
function renderFilters(){const f=document.getElementById("typeFilters");clear(f);typeNames.forEach(t=>{const label=document.createElement("label");label.className="chip";const box=document.createElement("input");box.type="checkbox";box.checked=state.types.has(t);box.addEventListener("change",()=>{box.checked?state.types.add(t):state.types.delete(t);renderGraph()});label.appendChild(box);label.appendChild(document.createTextNode(t));f.appendChild(label)})}
function connectedIds(id){const ids=new Set([id]);data.edges.forEach(e=>{if(e.source_node_id===id)ids.add(e.target_node_id);if(e.target_node_id===id)ids.add(e.source_node_id)});return ids}
function renderGraph(){clear(svg);const nodes=data.nodes.filter(matches);const nodeIds=new Set(nodes.map(n=>n.node_id));const edges=data.edges.filter(e=>nodeIds.has(e.source_node_id)&&nodeIds.has(e.target_node_id));const selected=state.selected?connectedIds(state.selected):null;const g=child("g",svg,{transform:"scale("+state.scale+")"});edges.forEach(e=>{const a=data.nodes.find(n=>n.node_id===e.source_node_id),b=data.nodes.find(n=>n.node_id===e.target_node_id);if(!a||!b)return;const line=child("line",g,{x1:a.layout.x,y1:a.layout.y,x2:b.layout.x,y2:b.layout.y,class:"edge"+(selected&&!selected.has(e.source_node_id)&&!selected.has(e.target_node_id)?" dim":"")+(selected&&selected.has(e.source_node_id)&&selected.has(e.target_node_id)?" highlight":"")});line.dataset.edgeId=e.edge_id});nodes.forEach(n=>{const group=child("g",g,{class:"node"+(n.node_id===state.selected?" selected":"")+(selected&&!selected.has(n.node_id)?" dim":""),transform:"translate("+n.layout.x+" "+n.layout.y+")"});group.addEventListener("click",()=>{state.selected=n.node_id;renderAll()});child("circle",group,{r:16,class:"type-"+n.entity_type});const label=child("text",group,{x:22,y:4});txt(label,n.label.length>30?n.label.slice(0,27)+"...":n.label)});svg.setAttribute("viewBox","0 0 1900 900")}
function renderDetails(){const node=data.nodes.find(n=>n.node_id===state.selected)||data.nodes.find(matches);const d=document.getElementById("details");clear(d);if(!node){txt(d,"No matching node.");return}function row(k,v){const dt=document.createElement("dt"),dd=document.createElement("dd");txt(dt,k);txt(dd,Array.isArray(v)?v.join(", "):typeof v==="object"?JSON.stringify(v,null,2):v);d.appendChild(dt);d.appendChild(dd)}const dl=document.createElement("dl");d.appendChild(dl);const old=d;d.appendChild=dl.appendChild.bind(dl);row("entity type",node.entity_type);row("stable ID",node.entity_id);row("name",node.label);row("description",node.description);row("status",node.status);row("warnings",(node.warnings||[]).join("; ")||"None");row("connected entity IDs",node.connected_entity_ids||[]);row("provenance precision",node.provenance_precision);row("provenance IDs",node.provenance_ids||[]);Object.keys(node.fields||{}).sort().forEach(k=>row(k,node.fields[k]));d.appendChild=old.appendChild.bind(old);renderEvidence(node)}
function renderEvidence(node){const e=document.getElementById("evidence");clear(e);const records=data.nodes.filter(n=>n.entity_type==="provenance"&&(node.provenance_ids||[]).includes(n.entity_id));if(node.entity_type==="provenance")records.push(node);if(records.length===0){txt(e,"No source evidence for this selection.");return}records.forEach(r=>{const dl=document.createElement("dl");e.appendChild(dl);["source_relative_path","source_role","source_sha256","parser_name","parser_status","evidence_type","source_locator","confidence"].forEach(k=>{const dt=document.createElement("dt"),dd=document.createElement("dd");txt(dt,k);txt(dd,r.fields[k]);dl.appendChild(dt);dl.appendChild(dd)});const pre=document.createElement("pre");txt(pre,r.fields.evidence_text_truncated?r.fields.evidence_text+"\\n(truncated to "+data.metadata.evidence_text_max_chars+" chars)":r.fields.evidence_text);e.appendChild(pre);if(r.warnings&&r.warnings.length){const w=document.createElement("div");w.className="warn";txt(w,r.warnings.join("; "));e.appendChild(w)}})}
function renderGaps(){const g=document.getElementById("gaps");clear(g);if(data.traceability_gaps.length===0){const ok=document.createElement("div");ok.className="ok";txt(ok,"No traceability gaps reported.");g.appendChild(ok);return}data.traceability_gaps.forEach(x=>{const p=document.createElement("div");p.className="pill bad";txt(p,x.gap_type+": "+x.description);g.appendChild(p)})}
function renderAll(){renderHeader();renderNav();renderGraph();renderDetails();renderGaps()}
document.getElementById("search").addEventListener("input",e=>{state.query=e.target.value;renderGraph()});
document.getElementById("precision").addEventListener("change",e=>{state.precision=e.target.value;renderGraph()});
document.getElementById("warnOnly").addEventListener("change",e=>{state.warnOnly=e.target.checked;renderGraph()});
document.getElementById("hideProv").addEventListener("change",e=>{state.hideProv=e.target.checked;renderGraph()});
document.getElementById("zoomIn").addEventListener("click",()=>{state.scale=Math.min(2.5,state.scale+.15);renderGraph()});
document.getElementById("zoomOut").addEventListener("click",()=>{state.scale=Math.max(.35,state.scale-.15);renderGraph()});
document.getElementById("reset").addEventListener("click",()=>{state.scale=1;state.selected=null;renderAll()});
renderFilters();renderAll();
</script>
</body>
</html>
"""
