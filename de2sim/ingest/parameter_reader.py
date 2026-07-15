"""Conservative parameter readers for DE2Sim Phase 1B."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from de2sim.ingest.artifact_parser import (
    common_record,
    parse_json_safely,
    parse_simple_scalar,
    parse_simple_yaml,
    read_text_safely,
)
from de2sim.ingest.geometry_manifest import normalized_extension


PARSER_NAME = "parameter_reader.phase1b"
_ALIASES = {
    "parameter_id": {"id", "parameter_id", "param_id"},
    "name": {"name", "parameter", "param"},
    "value": {"value", "default", "nominal"},
    "unit": {"unit", "units"},
    "minimum": {"minimum", "min"},
    "maximum": {"maximum", "max"},
    "description": {"description", "text"},
}
_ASSIGNMENT = re.compile(r"^\s*([A-Za-z_][\w.-]*)\s*[:=]\s*(.+?)\s*$")


def _pick(row: dict[str, Any], field: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in _ALIASES[field]:
        if alias in lowered and lowered[alias] not in (None, ""):
            return lowered[alias]
    return None


def _coerce(value: Any) -> Any:
    if isinstance(value, str):
        return parse_simple_scalar(value)
    return value


def _record(relative_path: str, role: str, locator: str, row: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "parameter_id": _pick(row, "parameter_id"),
        "name": _pick(row, "name"),
        "value": _coerce(_pick(row, "value")),
        "unit": _pick(row, "unit"),
        "minimum": _coerce(_pick(row, "minimum")),
        "maximum": _coerce(_pick(row, "maximum")),
        "description": _pick(row, "description"),
        "source_locator": locator,
    }
    return common_record("param", relative_path, role, PARSER_NAME, locator, payload, warnings)


def _dict_to_records(data: Any, relative_path: str, role: str, locator_prefix: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(data, list):
        for index, item in enumerate(data):
            if isinstance(item, dict):
                records.append(_record(relative_path, role, f"{locator_prefix}:{index}", item))
        return records
    if isinstance(data, dict) and isinstance(data.get("parameters"), list):
        return _dict_to_records(data["parameters"], relative_path, role, locator_prefix)
    if isinstance(data, dict):
        if any(key.lower() in _ALIASES["name"] | _ALIASES["value"] for key in map(str, data.keys())):
            records.append(_record(relative_path, role, f"{locator_prefix}:0", data))
        else:
            for key, value in sorted(data.items()):
                row = {"name": key, "value": value}
                records.append(_record(relative_path, role, f"{locator_prefix}:{key}", row))
    return records


def _read_csv(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    text, warnings = read_text_safely(path)
    if text is None:
        return [], warnings
    rows = csv.DictReader(text.splitlines())
    records = []
    for index, row in enumerate(rows, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        records.append(_record(relative_path, role, f"row:{index}", row))
    return records, warnings


def _read_json(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    data, warnings = parse_json_safely(path)
    if data is None:
        return [], warnings
    return _dict_to_records(data, relative_path, role, "json"), warnings


def _read_yaml(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    text, warnings = read_text_safely(path)
    if text is None:
        return [], warnings
    data, yaml_warnings = parse_simple_yaml(text)
    warnings.extend(yaml_warnings)
    if data is None:
        return [], warnings
    return _dict_to_records(data, relative_path, role, "yaml"), warnings


def _read_text(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    text, warnings = read_text_safely(path)
    if text is None:
        return [], warnings
    records = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        match = _ASSIGNMENT.match(raw)
        if not match:
            continue
        records.append(_record(relative_path, role, f"line:{line_no}", {"name": match.group(1), "value": match.group(2)}))
    return records, warnings


def read_parameters(path: Path, relative_path: str, role: str = "parameters") -> tuple[list[dict[str, Any]], list[str]]:
    extension = normalized_extension(relative_path)
    if extension == ".csv":
        return _read_csv(path, relative_path, role)
    if extension == ".json":
        return _read_json(path, relative_path, role)
    if extension in {".yaml", ".yml"}:
        return _read_yaml(path, relative_path, role)
    if extension in {".txt", ".md"}:
        return _read_text(path, relative_path, role)
    return [], [f"parameter reader does not support {extension or '<none>'}"]
