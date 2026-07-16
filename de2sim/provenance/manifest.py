"""Build DE2Sim Phase 3A provenance manifests and reports."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from de2sim.provenance.hashing import sha256_file, sha256_normalized_json
from de2sim.provenance.trace import (
    calculate_coverage_summary,
    classify_locator,
    provenance_precision,
    validate_traceability,
)


SCHEMA_VERSION = "de2sim.provenance_manifest.v1"


class ProvenanceManifestError(Exception):
    """Controlled provenance manifest failure."""


def build_provenance_manifest(
    asot: dict[str, Any],
    package_manifest: dict[str, Any],
    parsed_artifacts: dict[str, Any],
    package_manifest_path: Path | str,
    parsed_artifacts_path: Path | str,
    asot_path: Path | str,
) -> dict[str, Any]:
    """Build a deterministic provenance manifest, except for generated_at_utc."""
    source_files = _source_files(package_manifest, asot)
    provenance_records = _records_from_asot(asot, package_manifest)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "asot_id": str(asot.get("asot_id", "")),
        "source_package_filename": str(package_manifest.get("package_filename", "")),
        "source_package_sha256": str(package_manifest.get("package_sha256", "")),
        "package_manifest_sha256": sha256_file(package_manifest_path),
        "parsed_artifacts_sha256": sha256_file(parsed_artifacts_path),
        "asot_sha256": sha256_file(asot_path),
        "generated_at_utc": _utc_now(),
        "provenance_records": provenance_records,
        "source_files": source_files,
        "coverage_summary": {},
        "warnings": sorted(set(_warnings(package_manifest) + _warnings(parsed_artifacts) + _warnings(asot.get("validation", {})))),
    }
    manifest["coverage_summary"] = calculate_coverage_summary(asot, manifest)
    return manifest


def write_provenance_outputs(
    asot: dict[str, Any],
    package_manifest: dict[str, Any],
    parsed_artifacts: dict[str, Any],
    output_dir: Path | str,
    package_manifest_path: Path | str,
    parsed_artifacts_path: Path | str,
    asot_path: Path | str,
) -> dict[str, Path]:
    """Write provenance manifest and traceability reports."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = build_provenance_manifest(
        asot,
        package_manifest,
        parsed_artifacts,
        package_manifest_path,
        parsed_artifacts_path,
        asot_path,
    )
    extraction_root = output / str(package_manifest.get("extraction_root", "work/package"))
    report = validate_traceability(asot, manifest, extraction_root)
    manifest["coverage_summary"] = report.coverage_summary
    manifest["warnings"] = sorted(set(manifest.get("warnings", []) + report.warnings))

    manifest_path = output / "provenance_manifest.json"
    report_json_path = output / "traceability_report.json"
    report_md_path = output / "traceability_report.md"
    _write_json(manifest, manifest_path)
    _write_json(report.to_dict(), report_json_path)
    report_md_path.write_text(
        traceability_markdown(asot, package_manifest, manifest, report.to_dict(), parsed_artifacts),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "provenance_manifest": manifest_path,
        "traceability_report_json": report_json_path,
        "traceability_report_md": report_md_path,
    }


def traceability_markdown(
    asot: dict[str, Any],
    package_manifest: dict[str, Any],
    provenance_manifest: dict[str, Any],
    traceability_report: dict[str, Any],
    parsed_artifacts: dict[str, Any] | None = None,
) -> str:
    coverage = traceability_report.get("coverage_summary", {})
    by_type = _entity_counts(asot)
    precision = _precision_counts(provenance_manifest)
    deferred = parsed_artifacts.get("deferred_files", []) if isinstance(parsed_artifacts, dict) else []
    lines = [
        "# DE2Sim Traceability Report",
        "",
        f"- ASOT ID: `{asot.get('asot_id', '')}`",
        f"- Source package: `{package_manifest.get('package_filename', '')}`",
        f"- Overall traceability: `{coverage.get('traceability_percentage', 0.0)}%`",
        f"- Validation status: `{'valid' if traceability_report.get('valid') else 'invalid'}`",
        "",
        "## Counts by ASOT Entity Type",
        "",
    ]
    for key in sorted(by_type):
        lines.append(f"- {key}: {by_type[key]}")
    lines.extend(["", "## Counts by Provenance Precision", ""])
    for key in ("precise", "whole_file", "unresolved"):
        lines.append(f"- {key}: {precision.get(key, 0)}")
    lines.extend(["", "## Unresolved Entities", ""])
    unresolved = traceability_report.get("entities_without_provenance", [])
    lines.extend([f"- `{item}`" for item in unresolved] or ["- None"])
    lines.extend(["", "## Deferred Files", ""])
    if deferred:
        for item in deferred:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('source_relative_path', '')}`: {item.get('reason', '')}")
    else:
        lines.append("- None")
    lines.extend(["", "## Checksum Results", ""])
    mismatches = traceability_report.get("checksum_mismatches", [])
    missing = traceability_report.get("missing_source_files", [])
    if not mismatches and not missing:
        lines.append("- Source file checksums matched recorded manifest values.")
    for item in mismatches:
        lines.append(f"- Checksum mismatch: `{item.get('source_relative_path', '')}`")
    for item in missing:
        lines.append(f"- Missing source file: `{item}`")
    lines.extend(
        [
            "",
            "## Explicit Limitations",
            "",
            "- Provenance is limited to evidence emitted by Phase 1B parsers and package-manifest geometry references.",
            "- Whole-file geometry provenance is not complete field-level traceability.",
            "- No page numbers, coordinates, or source spans are invented when extractors do not provide them.",
            "- This report does not claim exact replayability.",
        ]
    )
    return "\n".join(lines) + "\n"


def _records_from_asot(asot: dict[str, Any], package_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    file_by_path = {str(item.get("relative_path", "")): item for item in package_manifest.get("files", []) if isinstance(item, dict)}
    target_ids_by_provenance: dict[str, set[str]] = {}
    for section in ("components", "requirements", "interfaces", "parameters", "physical_models", "behaviors", "geometry"):
        for entity in asot.get(section, []):
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("stable_id", ""))
            for provenance_id in entity.get("source_references", []):
                if provenance_id:
                    target_ids_by_provenance.setdefault(str(provenance_id), set()).add(entity_id)

    records = []
    for record in asot.get("provenance", []):
        if not isinstance(record, dict):
            continue
        rel = str(record.get("source_relative_path", ""))
        file_entry = file_by_path.get(rel, {})
        locator = str(record.get("source_locator", ""))
        evidence_type = str(record.get("evidence_type") or classify_locator(locator, rel))
        records.append(
            {
                "provenance_id": str(record.get("provenance_id", "")),
                "source_relative_path": rel,
                "source_sha256": str(record.get("source_sha256", "")),
                "source_role": str(record.get("source_role") or file_entry.get("role", "")),
                "parser_name": str(record.get("parser_name", "")),
                "parser_status": str(record.get("parser_status") or file_entry.get("parser_status", "")),
                "source_locator": locator,
                "evidence_type": evidence_type,
                "evidence_text": str(record.get("evidence_text", "")),
                "confidence": float(record.get("confidence", 0.0)),
                "target_entity_ids": sorted(target_ids_by_provenance.get(str(record.get("provenance_id", "")), set())),
                "warnings": sorted(str(item) for item in record.get("warnings", []) if str(item)),
            }
        )
    return sorted(records, key=lambda item: item["provenance_id"])


def _source_files(package_manifest: dict[str, Any], asot: dict[str, Any]) -> list[dict[str, Any]]:
    refs: dict[str, set[str]] = {}
    provenance_by_id = {
        str(record.get("provenance_id", "")): str(record.get("source_relative_path", ""))
        for record in asot.get("provenance", [])
        if isinstance(record, dict)
    }
    for section in ("components", "requirements", "interfaces", "parameters", "physical_models", "behaviors", "geometry"):
        for entity in asot.get(section, []):
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("stable_id", ""))
            for provenance_id in entity.get("source_references", []):
                rel = provenance_by_id.get(str(provenance_id), "")
                if rel:
                    refs.setdefault(rel, set()).add(entity_id)
    source_files = []
    for item in package_manifest.get("files", []):
        if not isinstance(item, dict):
            continue
        rel = str(item.get("relative_path", ""))
        source_files.append(
            {
                "source_relative_path": rel,
                "role": str(item.get("role", "")),
                "size_bytes": int(item.get("size_bytes", 0)),
                "sha256": str(item.get("sha256", "")),
                "parser_status": str(item.get("parser_status", "")),
                "referenced_entity_ids": sorted(refs.get(rel, set())),
                "warnings": sorted(str(warning) for warning in item.get("warnings", []) if str(warning)),
            }
        )
    return sorted(source_files, key=lambda item: item["source_relative_path"])


def _precision_counts(provenance_manifest: dict[str, Any]) -> dict[str, int]:
    counts = {"precise": 0, "whole_file": 0, "unresolved": 0}
    for record in provenance_manifest.get("provenance_records", []):
        if isinstance(record, dict):
            counts[provenance_precision(record)] += 1
    return counts


def _entity_counts(asot: dict[str, Any]) -> dict[str, int]:
    return {
        section: len(asot.get(section, [])) if isinstance(asot.get(section), list) else 0
        for section in ("components", "requirements", "interfaces", "parameters", "physical_models", "behaviors", "geometry")
    }


def _warnings(payload: dict[str, Any]) -> list[str]:
    return [str(item) for item in payload.get("warnings", []) if str(item)] if isinstance(payload.get("warnings"), list) else []


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
