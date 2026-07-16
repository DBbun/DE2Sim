"""Phase 6C geometry linkage, validation, scene, and viewer generation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any

from de2sim.asot.schema import stable_id
from de2sim.geometry.stl import STLParseError, STLParseOptions, parse_stl


LINKAGE_SCHEMA_VERSION = "de2sim.geometry_linkage.v1"
ABS_TOLERANCE = 1e-6
REL_TOLERANCE = 1e-9
VALID_UNITS = {"m"}
KNOWN_LIMITATIONS = [
    "demonstration STL mesh rather than native STEP/BREP CAD",
    "not vendor-authoritative geometry",
    "no articulation",
    "no material model",
    "no mass-property extraction",
    "no aerodynamic derivation",
    "no collision model",
    "no flight certification",
    "browser WebGL viewer is a visualization, not a CAD editor",
]


class GeometryError(Exception):
    """Controlled geometry ingestion failure."""


def extract_geometry_from_package(extraction_root: Path, linkage_relative_path: str = "geometry/geometry_linkage.json") -> dict[str, Any]:
    linkage_path = _safe_member_path(extraction_root, linkage_relative_path)
    if not linkage_path.is_file():
        raise GeometryError("geometry linkage sidecar is missing")
    linkage = load_linkage(linkage_path)
    unit = _text(linkage.get("unit"))
    if not unit:
        raise GeometryError("geometry units are missing")
    source_rel = _safe_rel(_text(linkage.get("source_geometry")))
    source_path = _safe_member_path(extraction_root, source_rel)
    if not source_path.is_file():
        raise GeometryError("STL source is missing")
    try:
        geometry = parse_stl(source_path, unit, STLParseOptions())
    except STLParseError as exc:
        raise GeometryError(str(exc)) from exc
    geometry["source_path"] = source_rel
    extraction = {
        "schema_version": "de2sim.geometry_extraction.v1",
        "linkage_path": linkage_relative_path,
        "linkage_sha256": _sha256(linkage_path),
        "linkage": linkage,
        "geometry": geometry,
        "tolerances": {"absolute": ABS_TOLERANCE, "relative": REL_TOLERANCE},
    }
    extraction["geometry_id"] = geometry_stable_id(extraction)
    return extraction


def load_linkage(path: Path | str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GeometryError(f"malformed geometry linkage JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except OSError as exc:
        raise GeometryError(f"failed to read geometry linkage: {exc}") from exc
    if not isinstance(payload, dict):
        raise GeometryError("geometry linkage root must be an object")
    if payload.get("schema_version") != LINKAGE_SCHEMA_VERSION:
        raise GeometryError("unsupported geometry linkage schema_version")
    return payload


def validate_geometry_extraction(extraction: dict[str, Any], asot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    linkage = _dict(extraction.get("linkage"))
    geometry = _dict(extraction.get("geometry"))
    errors: list[str] = []
    if _text(linkage.get("unit")) not in VALID_UNITS:
        errors.append(f"invalid geometry unit: {_text(linkage.get('unit'))}")
    if _text(linkage.get("authoritativeness")) != "not_vendor_authoritative":
        errors.append("invalid geometry authoritativeness value")
    if _text(linkage.get("source_classification")) != "demonstration_cad_export":
        errors.append("invalid geometry source classification")
    if not _text(geometry.get("source_sha256")):
        errors.append("missing source hash")
    if _text(geometry.get("unit")) != _text(linkage.get("unit")):
        errors.append("source units do not match sidecar units")

    ids = _asot_indexes(asot)
    component_id = _resolve_required(linkage.get("component_source_key"), ids["components"], "component", errors)
    physical_id = _resolve_required(linkage.get("physical_model_source_key"), ids["physical_models"], "physical model", errors)
    dim_keys = linkage.get("dimension_parameter_source_keys") if isinstance(linkage.get("dimension_parameter_source_keys"), dict) else {}
    if not dim_keys:
        errors.append("dimension_parameter_source_keys is missing")
    parameter_ids: dict[str, str] = {}
    for axis in ("x", "y", "z"):
        parameter_ids[axis] = _resolve_required(dim_keys.get(axis), ids["parameters"], f"{axis} dimension parameter", errors)
        param = ids["parameters_by_id"].get(parameter_ids[axis], {})
        expected = param.get("value")
        actual = _dict(geometry.get("dimensions")).get(axis)
        if expected is None:
            errors.append(f"{axis} dimension parameter is missing")
        elif not _close(actual, expected):
            errors.append(f"{axis} dimension mismatch: extracted {actual} {geometry.get('unit')} vs parameter {expected} {param.get('unit')}")
        if param and _text(param.get("unit")) != _text(linkage.get("unit")):
            errors.append(f"{axis} dimension parameter unit mismatch")

    validation = {
        "schema_version": "de2sim.geometry_validation.v1",
        "geometry_id": _text(extraction.get("geometry_id")),
        "valid": not errors,
        "validation_status": "passed" if not errors else "failed",
        "errors": sorted(set(errors)),
        "warnings": _list_text(geometry.get("warnings")),
        "tolerances": {"absolute": ABS_TOLERANCE, "relative": REL_TOLERANCE},
        "dimension_checks": {
            axis: {
                "extracted": _dict(geometry.get("dimensions")).get(axis),
                "parameter_id": parameter_ids.get(axis, ""),
                "passed": bool(parameter_ids.get(axis)) and _close(_dict(geometry.get("dimensions")).get(axis), ids["parameters_by_id"].get(parameter_ids.get(axis, ""), {}).get("value")),
            }
            for axis in ("x", "y", "z")
        },
        "source_hash": _text(geometry.get("source_sha256")),
    }
    linkage_report = {
        "schema_version": "de2sim.geometry_linkage_report.v1",
        "geometry_id": _text(extraction.get("geometry_id")),
        "source_geometry": _text(linkage.get("source_geometry")),
        "linked_component_id": component_id,
        "linked_physical_model_id": physical_id,
        "linked_parameter_ids": parameter_ids,
        "source_provenance_ids": _geometry_provenance_ids(asot, geometry),
        "relationship_source": "explicit geometry_linkage.json sidecar only",
        "valid": validation["valid"],
        "errors": validation["errors"],
    }
    return validation, linkage_report


def geometry_record_from_extraction(extraction: dict[str, Any], validation: dict[str, Any], linkage_report: dict[str, Any]) -> dict[str, Any]:
    linkage = _dict(extraction.get("linkage"))
    geometry = _dict(extraction.get("geometry"))
    source_refs = sorted(set(_list_text(linkage_report.get("source_provenance_ids"))))
    return {
        "stable_id": _text(extraction.get("geometry_id")),
        "name": Path(_text(geometry.get("source_path"))).name,
        "description": "Standards-based STL geometry parsed from explicit package linkage; visualization only.",
        "source_references": source_refs,
        "traceability_status": "precise" if validation.get("valid") else "validation_failed",
        "status": "validated" if validation.get("valid") else "invalid",
        "warnings": _list_text(geometry.get("warnings")),
        "source_relative_path": _text(geometry.get("source_path")),
        "geometry_format": "stl",
        "owning_component_id": "",
        "parser_status": "parsed",
        "coordinate_system": "stl_source_coordinates",
        "unit": _text(geometry.get("unit")),
        "source_path": _text(geometry.get("source_path")),
        "source_sha256": _text(geometry.get("source_sha256")),
        "source_format": _text(geometry.get("source_format")),
        "source_classification": _text(linkage.get("source_classification")),
        "authoritativeness": _text(linkage.get("authoritativeness")),
        "facet_count": int(geometry.get("facet_count", 0) or 0),
        "vertex_count": int(geometry.get("vertex_count", 0) or 0),
        "unique_vertex_count": int(geometry.get("unique_vertex_count", 0) or 0),
        "bounding_box_min": _dict(geometry.get("bounding_box_min")),
        "bounding_box_max": _dict(geometry.get("bounding_box_max")),
        "dimensions": _dict(geometry.get("dimensions")),
        "center": _dict(geometry.get("center")),
        "linked_component_ids": [_text(linkage_report.get("linked_component_id"))] if _text(linkage_report.get("linked_component_id")) else [],
        "linked_physical_model_ids": [_text(linkage_report.get("linked_physical_model_id"))] if _text(linkage_report.get("linked_physical_model_id")) else [],
        "linked_parameter_ids": sorted(_text(item) for item in _dict(linkage_report.get("linked_parameter_ids")).values() if _text(item)),
        "source_provenance_ids": source_refs,
        "validation_status": _text(validation.get("validation_status")),
        "limitations": KNOWN_LIMITATIONS,
    }


def geometry_stable_id(extraction: dict[str, Any]) -> str:
    geometry = _dict(extraction.get("geometry"))
    linkage = _dict(extraction.get("linkage"))
    return stable_id(
        "geometry",
        {
            "source_sha256": _text(geometry.get("source_sha256")),
            "source_path": _text(geometry.get("source_path")),
            "unit": _text(geometry.get("unit")),
            "source_classification": _text(linkage.get("source_classification")),
            "authoritativeness": _text(linkage.get("authoritativeness")),
        },
    )


def build_geometry_scene(extraction: dict[str, Any], validation: dict[str, Any], linkage_report: dict[str, Any]) -> dict[str, Any]:
    geometry = _dict(extraction.get("geometry"))
    return {
        "schema_version": "de2sim.geometry_scene.v1",
        "source_geometry_id": _text(extraction.get("geometry_id")),
        "display_classification": "Demonstration CAD-export mesh - not vendor-authoritative vehicle geometry",
        "vertices": geometry.get("vertices") if isinstance(geometry.get("vertices"), list) else [],
        "triangles": geometry.get("triangles") if isinstance(geometry.get("triangles"), list) else [],
        "source_normals": geometry.get("source_normals") if isinstance(geometry.get("source_normals"), list) else [],
        "bounding_box": {"min": _dict(geometry.get("bounding_box_min")), "max": _dict(geometry.get("bounding_box_max"))},
        "center": _dict(geometry.get("center")),
        "dimensions": _dict(geometry.get("dimensions")),
        "unit": _text(geometry.get("unit")),
        "source_format": _text(geometry.get("source_format")),
        "source_hash": _text(geometry.get("source_sha256")),
        "facet_count": int(geometry.get("facet_count", 0) or 0),
        "linked_asot_ids": {
            "component": _text(linkage_report.get("linked_component_id")),
            "physical_model": _text(linkage_report.get("linked_physical_model_id")),
            "parameters": _dict(linkage_report.get("linked_parameter_ids")),
        },
        "provenance_ids": _list_text(linkage_report.get("source_provenance_ids")),
        "validation": {"status": _text(validation.get("validation_status")), "errors": validation.get("errors", [])},
        "authoritativeness": _text(_dict(extraction.get("linkage")).get("authoritativeness")),
        "limitations": KNOWN_LIMITATIONS,
    }


def write_geometry_outputs(extraction: dict[str, Any], validation: dict[str, Any], linkage_report: dict[str, Any], output_dir: Path | str) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    scene = build_geometry_scene(extraction, validation, linkage_report)
    paths = {
        "geometry_extraction": output / "geometry_extraction.json",
        "geometry_validation": output / "geometry_validation.json",
        "geometry_linkage_report": output / "geometry_linkage_report.json",
        "geometry_scene": output / "geometry_scene.json",
        "geometry_viewer": output / "geometry_viewer.html",
    }
    for key in ("geometry_extraction", "geometry_validation", "geometry_linkage_report", "geometry_scene"):
        payload = {"geometry_extraction": extraction, "geometry_validation": validation, "geometry_linkage_report": linkage_report, "geometry_scene": scene}[key]
        _write_json(payload, paths[key])
    paths["geometry_viewer"].write_text(render_geometry_viewer(scene), encoding="utf-8", newline="\n")
    return paths


def render_geometry_viewer(scene: dict[str, Any]) -> str:
    data = json.dumps(scene, sort_keys=True, ensure_ascii=True).replace("</", "<\\/")
    return _VIEWER_HTML.replace("__GEOMETRY_SCENE__", data)


def _asot_indexes(asot: dict[str, Any]) -> dict[str, Any]:
    indexes: dict[str, Any] = {"components": {}, "physical_models": {}, "parameters": {}, "parameters_by_id": {}}
    for section in ("components", "physical_models", "parameters"):
        for item in asot.get(section, []) if isinstance(asot.get(section), list) else []:
            if not isinstance(item, dict):
                continue
            sid = _text(item.get("stable_id"))
            if not sid:
                continue
            target = indexes[section]
            for token in (sid, item.get("name"), item.get("parameter_id"), item.get("model_id")):
                if _text(token):
                    target[_text(token)] = sid
                    target[_text(token).lower()] = sid
            if section == "parameters":
                indexes["parameters_by_id"][sid] = item
    return indexes


def _resolve_required(value: Any, index: dict[str, str], label: str, errors: list[str]) -> str:
    key = _text(value)
    if not key:
        errors.append(f"{label} source key is missing")
        return ""
    resolved = index.get(key) or index.get(key.lower())
    if not resolved:
        errors.append(f"unknown {label} source key: {key}")
        return ""
    return resolved


def _geometry_provenance_ids(asot: dict[str, Any], geometry: dict[str, Any]) -> list[str]:
    source_path = _text(geometry.get("source_path"))
    source_hash = _text(geometry.get("source_sha256"))
    ids = []
    for item in asot.get("provenance", []) if isinstance(asot.get("provenance"), list) else []:
        if isinstance(item, dict) and (_text(item.get("source_relative_path")) == source_path or _text(item.get("source_sha256")) == source_hash):
            ids.append(_text(item.get("provenance_id")))
    return sorted(item for item in ids if item)


def _safe_member_path(root: Path, relative_path: str) -> Path:
    safe = _safe_rel(relative_path)
    target = (root / Path(*PurePosixPath(safe).parts)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise GeometryError(f"geometry path resolves outside package: {relative_path}") from exc
    return target


def _safe_rel(value: str) -> str:
    path = PurePosixPath(_text(value))
    if not str(path) or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise GeometryError(f"unsafe geometry package path: {value}")
    return "/".join(path.parts)


def _close(actual: Any, expected: Any) -> bool:
    try:
        return math.isclose(float(actual), float(expected), rel_tol=REL_TOLERANCE, abs_tol=ABS_TOLERANCE)
    except (TypeError, ValueError):
        return False


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({_text(item) for item in value if _text(item)})
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


_VIEWER_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DE2Sim Geometry Viewer</title>
<style>*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:#f7f8fa;color:#1f2933}.layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;min-height:100vh}canvas{width:100%;height:100vh;display:block;background:#101820}.panel{padding:14px;border-left:1px solid #c8d0dc;background:white;overflow:auto}.banner{font-weight:bold;color:#8a2d2d;margin-bottom:10px}.tools{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}button{border:1px solid #9baabe;background:#f8fafc;border-radius:6px;padding:7px 9px;cursor:pointer}.active{background:#dbeafe}.kv{font-size:13px;line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:820px){.layout{grid-template-columns:1fr}.panel{border-left:0;border-top:1px solid #c8d0dc}canvas{height:62vh}}</style>
</head><body><div class="layout"><canvas id="gl"></canvas><aside class="panel">
<div class="banner">Demonstration CAD-export mesh - not vendor-authoritative vehicle geometry.</div>
<div class="tools"><button id="solid">Solid</button><button id="wire">Wire</button><button id="box">Box</button><button id="front">Front</button><button id="side">Side</button><button id="top">Top</button><button id="fit">Fit</button><button id="reset">Reset</button></div>
<div class="kv" id="meta"></div></aside></div>
<script id="geometry-scene" type="application/json">__GEOMETRY_SCENE__</script>
<script>
"use strict";
const scene=JSON.parse(document.getElementById("geometry-scene").textContent);
const canvas=document.getElementById("gl");let mode="solid",rx=-0.6,ry=0.7,zoom=2.4,drag=false,last=[0,0];
function S(v){return v==null?"":String(v)}function resize(){const d=window.devicePixelRatio||1;canvas.width=Math.max(1,Math.floor(canvas.clientWidth*d));canvas.height=Math.max(1,Math.floor(canvas.clientHeight*d))}
function mat(){const cx=Math.cos(rx),sx=Math.sin(rx),cy=Math.cos(ry),sy=Math.sin(ry);return [cy,sx*sy,cx*sy,0,cx,-sx,-sy,sx*cy,cx*cy]}
function project(p,m){const c=scene.center||{x:0,y:0,z:0};const s=Math.max(scene.dimensions.x,scene.dimensions.y,scene.dimensions.z)||1;let x=(p[0]-c.x)/s,y=(p[1]-c.y)/s,z=(p[2]-c.z)/s;const X=m[0]*x+m[1]*y+m[2]*z,Y=m[3]*x+m[4]*y+m[5]*z,Z=m[6]*x+m[7]*y+m[8]*z+zoom;return [canvas.width*(0.5+X/Z),canvas.height*(0.5-Y/Z),Z]}
function axes(ctx,m){const o=project([0,0,0],m);[[0.4,0,0,"#ef476f","x"],[0,0.4,0,"#06d6a0","y"],[0,0,0.4,"#ffd166","z"]].forEach(a=>{const p=project([a[0],a[1],a[2]],m);ctx.strokeStyle=a[3];ctx.fillStyle=a[3];ctx.beginPath();ctx.moveTo(o[0],o[1]);ctx.lineTo(p[0],p[1]);ctx.stroke();ctx.fillText(a[4],p[0]+4,p[1]+4)})}
function box(ctx,m){const b=scene.bounding_box||{},mn=b.min||{},mx=b.max||{};const c=[[mn.x,mn.y,mn.z],[mx.x,mn.y,mn.z],[mx.x,mx.y,mn.z],[mn.x,mx.y,mn.z],[mn.x,mn.y,mx.z],[mx.x,mn.y,mx.z],[mx.x,mx.y,mx.z],[mn.x,mx.y,mx.z]],e=[[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];ctx.strokeStyle="#ffd166";ctx.lineWidth=2;e.forEach(x=>{const a=project(c[x[0]],m),b=project(c[x[1]],m);ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()})}
function draw(){resize();const ctx=canvas.getContext("2d"),m=mat(),v=scene.vertices||[],tris=scene.triangles||[];ctx.fillStyle="#101820";ctx.fillRect(0,0,canvas.width,canvas.height);const faces=tris.map(tr=>({tr,z:tr.reduce((a,i)=>a+project(v[i],m)[2],0)/3})).sort((a,b)=>b.z-a.z);faces.forEach(f=>{const pts=f.tr.map(i=>project(v[i],m));ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);ctx.lineTo(pts[1][0],pts[1][1]);ctx.lineTo(pts[2][0],pts[2][1]);ctx.closePath();if(mode==="solid"){ctx.fillStyle="#6db7d9";ctx.fill();ctx.strokeStyle="#24485c";ctx.stroke()}else if(mode==="wire"){ctx.strokeStyle="#e8f4ff";ctx.stroke()}});if(mode==="box")box(ctx,m);axes(ctx,m);requestAnimationFrame(draw)}
function meta(){const ids=scene.linked_asot_ids||{},p=ids.parameters||{};document.getElementById("meta").textContent="Facet count: "+S(scene.facet_count)+"\\nSource format: "+S(scene.source_format)+"\\nSource hash: "+S(scene.source_hash)+"\\nDimensions: "+S(scene.dimensions.x)+" x "+S(scene.dimensions.y)+" x "+S(scene.dimensions.z)+" "+S(scene.unit)+"\\nAuthoritativeness: "+S(scene.authoritativeness)+"\\nLinked component ID: "+S(ids.component)+"\\nLinked physical-model ID: "+S(ids.physical_model)+"\\nLinked parameter IDs: "+S(p.x)+", "+S(p.y)+", "+S(p.z)+"\\nProvenance IDs: "+(scene.provenance_ids||[]).join(", ")+"\\nValidation result: "+S((scene.validation||{}).status)+"\\n\\nVisible limitations:\\n"+(scene.limitations||[]).map(x=>"- "+x).join("\\n")}
["solid","wire","box"].forEach(id=>document.getElementById(id).onclick=()=>{mode=id;document.querySelectorAll("button").forEach(b=>b.classList.remove("active"));document.getElementById(id).classList.add("active")});document.getElementById("front").onclick=()=>{rx=0;ry=0};document.getElementById("side").onclick=()=>{rx=0;ry=1.5708};document.getElementById("top").onclick=()=>{rx=-1.5708;ry=0};document.getElementById("fit").onclick=()=>{zoom=2.4};document.getElementById("reset").onclick=()=>{rx=-0.6;ry=0.7;zoom=2.4};canvas.onmousedown=e=>{drag=true;last=[e.clientX,e.clientY]};canvas.onmouseup=()=>drag=false;canvas.onmouseleave=()=>drag=false;canvas.onmousemove=e=>{if(drag){ry+=(e.clientX-last[0])*0.01;rx+=(e.clientY-last[1])*0.01;last=[e.clientX,e.clientY]}};canvas.onwheel=e=>{e.preventDefault();zoom=Math.max(1.1,Math.min(8,zoom+e.deltaY*0.002))};meta();document.getElementById("solid").classList.add("active");draw();
</script></body></html>
"""
