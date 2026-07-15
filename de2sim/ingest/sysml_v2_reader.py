"""Narrow, line-oriented SysML v2 artifact reader for Phase 1B."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from de2sim.ingest.artifact_parser import common_record, parse_json_safely, read_text_safely
from de2sim.ingest.geometry_manifest import normalized_extension


PARSER_NAME = "sysml_v2_reader.phase1b"
_DECLARATION = re.compile(
    r"^\s*(package|part\s+def|part|attribute\s+def|attribute|port\s+def|port|requirement\s+def|requirement|action\s+def|action)\s+([A-Za-z_][\w:.-]*)",
    re.IGNORECASE,
)
_RELATIONSHIP = re.compile(r"^\s*(connect|satisfy|verify)\s+(.+?)\s*$", re.IGNORECASE)


def _element(relative_path: str, role: str, locator: str, payload: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    return common_record("sysml-el", relative_path, role, PARSER_NAME, locator, payload, warnings)


def _relationship(relative_path: str, role: str, locator: str, payload: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    return common_record("sysml-rel", relative_path, role, PARSER_NAME, locator, payload, warnings)


def _read_textual(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    text, warnings = read_text_safely(path)
    if text is None:
        return [], [], warnings
    elements: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        decl = _DECLARATION.match(line)
        if decl:
            kind = " ".join(decl.group(1).lower().split())
            name = decl.group(2).rstrip("{;")
            elements.append(
                _element(
                    relative_path,
                    role,
                    f"line:{line_no}",
                    {
                        "kind": kind,
                        "element_id": name,
                        "name": name.split("::")[-1],
                        "owner": None,
                        "value": None,
                        "unit": None,
                        "description": None,
                    },
                )
            )
            continue
        rel = _RELATIONSHIP.match(line)
        if rel:
            relationship_kind = rel.group(1).lower()
            body = rel.group(2).rstrip(";")
            source = None
            target = None
            if " to " in body:
                source, target = [part.strip() for part in body.split(" to ", 1)]
            elif " by " in body:
                target, source = [part.strip() for part in body.split(" by ", 1)]
            relationships.append(
                _relationship(
                    relative_path,
                    role,
                    f"line:{line_no}",
                    {
                        "kind": relationship_kind,
                        "relationship_id": None,
                        "name": None,
                        "source": source,
                        "target": target,
                        "description": body,
                    },
                )
            )
            continue
        warnings.append(f"line {line_no}: unrecognized SysML subset line")
    return elements, relationships, warnings


def _json_items(data: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return [item for item in data[key] if isinstance(item, dict)]
    if isinstance(data, dict) and ("kind" in data or "type" in data):
        return [data]
    return []


def _read_json(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    data, warnings = parse_json_safely(path)
    if data is None:
        return [], [], warnings
    element_items = _json_items(data, "elements")
    relationship_items = []
    if isinstance(data, dict) and isinstance(data.get("relationships"), list):
        relationship_items = [item for item in data["relationships"] if isinstance(item, dict)]
    elements = [
        _element(
            relative_path,
            role,
            f"json:elements:{index}",
            {
                "kind": item.get("kind") or item.get("type"),
                "element_id": item.get("id"),
                "name": item.get("name"),
                "owner": item.get("owner"),
                "value": item.get("value"),
                "unit": item.get("unit"),
                "description": item.get("description"),
            },
        )
        for index, item in enumerate(element_items)
    ]
    relationships = [
        _relationship(
            relative_path,
            role,
            f"json:relationships:{index}",
            {
                "kind": item.get("kind") or item.get("type"),
                "relationship_id": item.get("id"),
                "name": item.get("name"),
                "source": item.get("source"),
                "target": item.get("target"),
                "description": item.get("description"),
            },
        )
        for index, item in enumerate(relationship_items)
    ]
    if not elements and not relationships:
        warnings.append("SysML JSON did not contain supported elements or relationships")
    return elements, relationships, warnings


def read_sysml(path: Path, relative_path: str, role: str = "sysml") -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    extension = normalized_extension(relative_path)
    if extension == ".sysml":
        return _read_textual(path, relative_path, role)
    if extension in {".sysml.json", ".json"}:
        return _read_json(path, relative_path, role)
    return [], [], [f"SysML reader does not support {extension or '<none>'}"]
