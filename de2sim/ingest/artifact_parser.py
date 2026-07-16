"""Deterministic structured-artifact parsing for DE2Sim Phase 1B."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from de2sim.ingest.geometry_manifest import normalized_extension


SCHEMA_VERSION = "de2sim.parsed_artifacts.v1"
PARSER_VERSION = "phase1b"
DEFERRED_EXTENSIONS = {".pdf", ".docx", ".xlsx"}


class ArtifactParsingError(Exception):
    """Controlled artifact parsing failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, evidence: Any) -> str:
    """Return a deterministic ID from normalized source evidence."""
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{prefix}-{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def read_text_safely(path: Path) -> tuple[str | None, list[str]]:
    try:
        return path.read_text(encoding="utf-8-sig"), []
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), [
                "file contained undecodable bytes; replacement characters were used"
            ]
        except OSError as exc:
            return None, [f"failed to read text: {exc}"]
    except OSError as exc:
        return None, [f"failed to read text: {exc}"]


def parse_json_safely(path: Path) -> tuple[Any | None, list[str]]:
    text, warnings = read_text_safely(path)
    if text is None:
        return None, warnings
    try:
        return json.loads(text), warnings
    except json.JSONDecodeError as exc:
        return None, warnings + [f"malformed JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"]


def parse_simple_scalar(value: str) -> Any:
    stripped = value.strip()
    if stripped == "":
        return ""
    lowered = stripped.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if (stripped.startswith('"') and stripped.endswith('"')) or (
        stripped.startswith("'") and stripped.endswith("'")
    ):
        return stripped[1:-1]
    try:
        if any(ch in stripped for ch in (".", "e", "E")):
            return float(stripped)
        return int(stripped)
    except ValueError:
        return stripped


def parse_simple_yaml(text: str) -> tuple[Any | None, list[str]]:
    """Parse a conservative, dependency-free YAML subset."""
    warnings: list[str] = []
    if any(token in text for token in ("&", "*", "!")):
        warnings.append("YAML anchors, aliases, or custom tags are outside the supported subset")
        return None, warnings

    lines = [(idx, raw.rstrip()) for idx, raw in enumerate(text.splitlines(), start=1)]
    meaningful = [(idx, raw) for idx, raw in lines if raw.strip() and not raw.lstrip().startswith("#")]
    if not meaningful:
        return {}, warnings

    if all(raw.lstrip().startswith("-") for _, raw in meaningful):
        items: list[Any] = []
        for line_no, raw in meaningful:
            if raw.startswith(" ") or raw.startswith("\t"):
                warnings.append(f"line {line_no}: nested YAML is outside the supported subset")
                continue
            item_text = raw.lstrip()[1:].strip()
            if not item_text:
                warnings.append(f"line {line_no}: empty YAML list item ignored")
                continue
            if ":" in item_text:
                key, value = item_text.split(":", 1)
                items.append({key.strip(): parse_simple_scalar(value)})
            else:
                items.append(parse_simple_scalar(item_text))
        return items, sorted(set(warnings))

    mapping: dict[str, Any] = {}
    for line_no, raw in meaningful:
        if raw.startswith(" ") or raw.startswith("\t"):
            warnings.append(f"line {line_no}: nested YAML is outside the supported subset")
            continue
        if raw.lstrip().startswith("-"):
            warnings.append(f"line {line_no}: mixed mapping/list YAML is outside the supported subset")
            continue
        if ":" not in raw:
            warnings.append(f"line {line_no}: YAML line is not a scalar key-value mapping")
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        if not key:
            warnings.append(f"line {line_no}: empty YAML key ignored")
            continue
        mapping[key] = parse_simple_scalar(value)
    return mapping, sorted(set(warnings))


def common_record(
    prefix: str,
    source_relative_path: str,
    source_role: str,
    parser_name: str,
    source_locator: str,
    payload: dict[str, Any],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    clean_warnings = sorted(set(warnings or []))
    evidence = {
        "source_relative_path": source_relative_path,
        "source_locator": source_locator,
        "payload": payload,
    }
    return {
        "stable_id": stable_id(prefix, evidence),
        "source_relative_path": source_relative_path,
        "source_role": source_role,
        "parser_name": parser_name,
        "source_locator": source_locator,
        "warnings": clean_warnings,
        **payload,
    }


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda item: (
            str(item.get("source_relative_path", "")),
            str(item.get("source_locator", "")),
            str(item.get("stable_id", "")),
        ),
    )


def _safe_source_path(extraction_root: Path, relative_path: str) -> Path:
    source = (extraction_root / Path(*PurePosixPath(relative_path).parts)).resolve()
    root = extraction_root.resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise ArtifactParsingError(f"manifest path resolves outside extraction root: {relative_path}") from exc
    return source


def _deferred_entry(relative_path: str, role: str, reason: str, recommended: str) -> dict[str, str]:
    return {
        "source_relative_path": relative_path,
        "role": role,
        "reason": reason,
        "recommended_optional_parser": recommended,
    }


def _status_from_result(records: int, warnings: list[str]) -> str:
    if records and warnings:
        return "partially_parsed"
    if records:
        return "parsed"
    if warnings:
        return "failed"
    return "unsupported"


def parse_artifacts_from_manifest(manifest_path: Path | str) -> Path:
    """Parse supported Phase 1B structured artifacts and write parsed_artifacts.json."""
    from de2sim.ingest.parameter_reader import read_parameters
    from de2sim.ingest.physical_model_reader import read_physical_models
    from de2sim.ingest.requirement_reader import read_requirements
    from de2sim.ingest.sysml_v2_reader import read_sysml

    manifest_file = Path(manifest_path)
    output_dir = manifest_file.parent
    manifest_sha = sha256_file(manifest_file)
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactParsingError(f"failed to read package manifest: {exc}") from exc

    extraction_root = (output_dir / manifest.get("extraction_root", "work/package")).resolve()
    requirements: list[dict[str, Any]] = []
    parameters: list[dict[str, Any]] = []
    sysml_elements: list[dict[str, Any]] = []
    sysml_relationships: list[dict[str, Any]] = []
    physical_models: list[dict[str, Any]] = []
    geometry_extractions: list[dict[str, Any]] = []
    deferred_files: list[dict[str, str]] = []
    warnings: list[str] = []

    for file_entry in manifest.get("files", []):
        relative_path = str(file_entry.get("relative_path", ""))
        role = str(file_entry.get("role", "unsupported"))
        extension = normalized_extension(relative_path)
        status = "unsupported"
        try:
            source_path = _safe_source_path(extraction_root, relative_path)
            if role == "geometry":
                if relative_path == "geometry/geometry_linkage.json":
                    from de2sim.geometry.pipeline import GeometryError, extract_geometry_from_package

                    try:
                        geometry_extractions.append(extract_geometry_from_package(extraction_root, relative_path))
                        status = "parsed"
                    except GeometryError as exc:
                        status = "failed"
                        warnings.append(f"{relative_path}: {exc}")
                elif extension == ".stl":
                    status = "referenced_not_parsed"
                    deferred_files.append(
                        _deferred_entry(
                            relative_path,
                            role,
                            "STL parsing requires explicit geometry/geometry_linkage.json metadata",
                            "de2sim Phase 6C geometry parser",
                        )
                    )
                else:
                    status = "referenced_not_parsed"
                    deferred_files.append(
                        _deferred_entry(
                            relative_path,
                            role,
                            "geometry files are referenced but not parsed in Phase 1B",
                            "future geometry/CAD parser",
                        )
                    )
            elif extension in DEFERRED_EXTENSIONS:
                status = "deferred"
                recommended = {
                    ".pdf": "PDF text/table parser",
                    ".docx": "DOCX document parser",
                    ".xlsx": "XLSX spreadsheet parser",
                }[extension]
                deferred_files.append(
                    _deferred_entry(relative_path, role, f"{extension} parsing is deferred in Phase 1B", recommended)
                )
            elif role == "requirements":
                records, file_warnings = read_requirements(source_path, relative_path, role)
                requirements.extend(records)
                warnings.extend(f"{relative_path}: {warning}" for warning in file_warnings)
                status = _status_from_result(len(records), file_warnings)
            elif role == "parameters":
                records, file_warnings = read_parameters(source_path, relative_path, role)
                parameters.extend(records)
                warnings.extend(f"{relative_path}: {warning}" for warning in file_warnings)
                status = _status_from_result(len(records), file_warnings)
            elif role == "sysml":
                elements, relationships, file_warnings = read_sysml(source_path, relative_path, role)
                sysml_elements.extend(elements)
                sysml_relationships.extend(relationships)
                warnings.extend(f"{relative_path}: {warning}" for warning in file_warnings)
                status = _status_from_result(len(elements) + len(relationships), file_warnings)
            elif role == "physical_model":
                records, file_warnings = read_physical_models(source_path, relative_path, role)
                physical_models.extend(records)
                warnings.extend(f"{relative_path}: {warning}" for warning in file_warnings)
                status = _status_from_result(len(records), file_warnings)
            else:
                status = "unsupported"
                deferred_files.append(
                    _deferred_entry(
                        relative_path,
                        role,
                        "file role or extension is not supported by Phase 1B structured parsing",
                        "role-specific parser",
                    )
                )
        except ArtifactParsingError as exc:
            status = "failed"
            warnings.append(f"{relative_path}: {exc}")
        file_entry["parser_status"] = status

    parsed = {
        "schema_version": SCHEMA_VERSION,
        "package_filename": manifest.get("package_filename", ""),
        "package_sha256": manifest.get("package_sha256", ""),
        "package_manifest_sha256": manifest_sha,
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "requirements": _sort_records(requirements),
        "parameters": _sort_records(parameters),
        "sysml_elements": _sort_records(sysml_elements),
        "sysml_relationships": _sort_records(sysml_relationships),
        "physical_models": _sort_records(physical_models),
        "geometry_extractions": sorted(geometry_extractions, key=lambda item: str(item.get("geometry_id", ""))),
        "deferred_files": sorted(deferred_files, key=lambda item: (item["source_relative_path"], item["role"])),
        "warnings": sorted(set(warnings)),
        "record_counts": {
            "requirements": len(requirements),
            "parameters": len(parameters),
            "sysml_elements": len(sysml_elements),
            "sysml_relationships": len(sysml_relationships),
            "physical_models": len(physical_models),
            "geometry_extractions": len(geometry_extractions),
            "deferred_files": len(deferred_files),
            "warnings": len(set(warnings)),
        },
    }

    parsed_path = output_dir / "parsed_artifacts.json"
    with parsed_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(parsed, stream, indent=2, sort_keys=False)
        stream.write("\n")

    with manifest_file.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=False)
        stream.write("\n")

    return parsed_path
