"""Conservative requirement readers for DE2Sim Phase 1B."""

from __future__ import annotations

import csv
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


PARSER_NAME = "requirement_reader.phase1b"
_ALIASES = {
    "requirement_id": {"id", "requirement_id", "req_id"},
    "title": {"title", "name"},
    "text": {"text", "requirement", "description"},
    "verification_method": {"verification_method", "verification"},
    "priority": {"priority"},
}
_REQ_ID = re.compile(r"\b([A-Z]{2,10}-\d{1,6})\b")


def _pick(row: dict[str, Any], field: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in _ALIASES[field]:
        if alias in lowered and lowered[alias] not in (None, ""):
            return lowered[alias]
    return None


def _record(relative_path: str, role: str, locator: str, row: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "requirement_id": _pick(row, "requirement_id"),
        "title": _pick(row, "title"),
        "text": _pick(row, "text"),
        "verification_method": _pick(row, "verification_method"),
        "priority": _pick(row, "priority"),
        "source_locator": locator,
    }
    return common_record("req", relative_path, role, PARSER_NAME, locator, payload, warnings)


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


def _items_from_json(data: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)], []
    if isinstance(data, dict) and isinstance(data.get("requirements"), list):
        return [item for item in data["requirements"] if isinstance(item, dict)], []
    if isinstance(data, dict):
        return [data], []
    return [], ["JSON requirements must be an object, a list, or contain a requirements list"]


def _read_json(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    data, warnings = parse_json_safely(path)
    if data is None:
        return [], warnings
    items, item_warnings = _items_from_json(data)
    records = [_record(relative_path, role, f"json:{index}", item) for index, item in enumerate(items)]
    return records, warnings + item_warnings


def _flush_text_record(records: list[dict[str, Any]], relative_path: str, role: str, title: str | None, lines: list[tuple[int, str]]) -> None:
    if not lines:
        return
    first_line = lines[0][0]
    text = " ".join(line for _, line in lines).strip()
    if not text:
        return
    match = _REQ_ID.search(text)
    row = {
        "requirement_id": match.group(1) if match else None,
        "title": title,
        "text": text,
    }
    records.append(_record(relative_path, role, f"line:{first_line}", row))


def _read_text(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    text, warnings = read_text_safely(path)
    if text is None:
        return [], warnings
    records: list[dict[str, Any]] = []
    pending_title: str | None = None
    pending_lines: list[tuple[int, str]] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            _flush_text_record(records, relative_path, role, pending_title, pending_lines)
            pending_title = None
            pending_lines = []
            continue
        if line.startswith("#"):
            _flush_text_record(records, relative_path, role, pending_title, pending_lines)
            pending_title = line.lstrip("#").strip() or None
            pending_lines = []
            continue
        if pending_title:
            pending_lines.append((line_no, line))
        else:
            _flush_text_record(records, relative_path, role, None, [(line_no, line)])
    _flush_text_record(records, relative_path, role, pending_title, pending_lines)
    return records, warnings


def _read_yaml(path: Path, relative_path: str, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    text, warnings = read_text_safely(path)
    if text is None:
        return [], warnings
    data, yaml_warnings = parse_simple_yaml(text)
    warnings.extend(yaml_warnings)
    if data is None:
        return [], warnings
    items = data if isinstance(data, list) else data.get("requirements", data) if isinstance(data, dict) else []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return [], warnings + ["YAML requirements did not contain record mappings"]
    records = [_record(relative_path, role, f"yaml:{index}", item) for index, item in enumerate(items) if isinstance(item, dict)]
    return records, warnings


def read_requirements(path: Path, relative_path: str, role: str = "requirements") -> tuple[list[dict[str, Any]], list[str]]:
    extension = normalized_extension(relative_path)
    if extension == ".csv":
        return _read_csv(path, relative_path, role)
    if extension == ".json":
        return _read_json(path, relative_path, role)
    if extension in {".txt", ".md"}:
        return _read_text(path, relative_path, role)
    if extension in {".yaml", ".yml"}:
        return _read_yaml(path, relative_path, role)
    return [], [f"requirements reader does not support {extension or '<none>'}"]
