"""Conservative physical-model readers for DE2Sim Phase 1B."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from de2sim.ingest.artifact_parser import (
    common_record,
    parse_json_safely,
    parse_simple_yaml,
    read_text_safely,
)
from de2sim.ingest.geometry_manifest import normalized_extension


PARSER_NAME = "physical_model_reader.phase1b"
_EQUATION = re.compile(r"^\s*(?:equation|formula)\s*:\s*(.+?)\s*$", re.IGNORECASE)
_NAMED_EQUATION = re.compile(r"^\s*([A-Za-z_][\w .-]{0,80})\s*=\s*(.+?)\s*$")


def _record(relative_path: str, role: str, locator: str, row: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "model_id": row.get("model_id") or row.get("id"),
        "name": row.get("name"),
        "equation": row.get("equation") or row.get("formula"),
        "variables": row.get("variables"),
        "parameters": row.get("parameters"),
        "assumptions": row.get("assumptions"),
        "description": row.get("description"),
        "source_locator": locator,
    }
    return common_record("phys", relative_path, role, PARSER_NAME, locator, payload, warnings)


def _records_from_data(data: Any, relative_path: str, role: str, prefix: str) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("physical_models"), list):
        data = data["physical_models"]
    if isinstance(data, list):
        return [
            _record(relative_path, role, f"{prefix}:{index}", item)
            for index, item in enumerate(data)
            if isinstance(item, dict) and (item.get("equation") or item.get("formula"))
        ]
    if isinstance(data, dict) and (data.get("equation") or data.get("formula")):
        return [_record(relative_path, role, f"{prefix}:0", data)]
    return []


def _read_json(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    data, warnings = parse_json_safely(path)
    if data is None:
        return [], warnings
    return _records_from_data(data, relative_path, role, "json"), warnings


def _read_yaml(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    text, warnings = read_text_safely(path)
    if text is None:
        return [], warnings
    data, yaml_warnings = parse_simple_yaml(text)
    warnings.extend(yaml_warnings)
    if data is None:
        return [], warnings
    return _records_from_data(data, relative_path, role, "yaml"), warnings


def _read_text(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    text, warnings = read_text_safely(path)
    if text is None:
        return [], warnings
    records = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        match = _EQUATION.match(line)
        if match:
            records.append(_record(relative_path, role, f"line:{line_no}", {"equation": match.group(1)}))
            continue
        named = _NAMED_EQUATION.match(line)
        if named:
            records.append(
                _record(
                    relative_path,
                    role,
                    f"line:{line_no}",
                    {"name": named.group(1).strip(), "equation": f"{named.group(1).strip()} = {named.group(2).strip()}"},
                )
            )
    return records, warnings


def read_physical_models(path: Path, relative_path: str, role: str = "physical_model") -> tuple[list[dict[str, Any]], list[str]]:
    extension = normalized_extension(relative_path)
    if extension == ".json":
        return _read_json(path, relative_path, role)
    if extension in {".yaml", ".yml"}:
        return _read_yaml(path, relative_path, role)
    if extension in {".txt", ".md"}:
        return _read_text(path, relative_path, role)
    return [], [f"physical-model reader does not support {extension or '<none>'}"]
