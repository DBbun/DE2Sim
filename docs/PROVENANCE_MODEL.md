# DE2Sim Provenance Model

Phase 3A adds formal provenance and source traceability for ASOT records. It is
dependency-free, deterministic where inputs are deterministic, and uses only
evidence produced by secure package ingestion and structured artifact parsing.

Phase 3A does not implement AI behavior generation, simulations, Godot export,
ZIP deployment packaging, exact replayability, or complete field-level
provenance.

## CLI

```text
python -m de2sim.cli.challenge_pipeline --engineering-package package.zip --output out --build-provenance
```

`--build-provenance` automatically runs:

- secure ZIP ingestion
- structured artifact parsing
- ASOT construction
- ASOT validation
- provenance construction
- traceability validation

It writes:

- `package_manifest.json`
- `parsed_artifacts.json`
- `asot.json`
- `asot_summary.md`
- `asot_validation.json`
- `provenance_manifest.json`
- `traceability_report.json`
- `traceability_report.md`

## Hashing

Source files are hashed with SHA-256 over bytes using chunked reads. Normalized
JSON hashes use sorted keys and compact separators. Missing or unreadable files
raise controlled provenance errors rather than Python tracebacks.

## Provenance Records

Each provenance record supports:

- `provenance_id`
- `source_relative_path`
- `source_sha256`
- `source_role`
- `parser_name`
- `parser_status`
- `source_locator`
- `evidence_type`
- `evidence_text`
- `confidence`
- `target_entity_ids`
- `warnings`

Provenance IDs are deterministic SHA-256-derived IDs. Random UUIDs are not used.

## Source Locators

Supported evidence types are:

- `csv_row`
- `text_line`
- `text_line_range`
- `json_pointer`
- `yaml_key_path`
- `sysml_element`
- `sysml_line`
- `whole_file`
- `geometry_file`

The implementation does not invent page numbers, coordinates, source spans, or
field-level evidence that an extractor did not provide.

## Coverage Summary

Coverage counts traceable ASOT engineering entities only:

- components
- requirements
- interfaces
- parameters
- physical models
- behaviors
- geometry records

Metadata-only records are not counted as traceable engineering entities.

Traceability percentage is calculated conservatively:

```text
entities with at least one valid provenance reference / total traceable ASOT entities
```

Whole-file geometry references count as valid provenance references, but they
are reported separately from precise provenance and should not be interpreted as
complete field-level traceability.

## Validation

Traceability validation detects:

- duplicate provenance IDs
- provenance references to nonexistent ASOT entities
- ASOT `source_references` pointing to nonexistent provenance records
- missing source files
- checksum mismatches
- unsupported `evidence_type` values
- confidence outside `0.0` to `1.0`

Validation separates errors from warnings, does not mutate the supplied ASOT or
provenance manifest, and returns a controlled nonzero CLI exit code when
traceability errors occur.

## Limitations

- Provenance is limited to Phase 1B parser evidence and package-manifest
  geometry references.
- Geometry files are referenced, not parsed as CAD.
- Whole-file evidence is not precise field-level evidence.
- PDF, DOCX, XLSX, and unsupported binary source spans remain deferred.
- No external URLs are followed.
- Source content is never executed, equations are never evaluated, and uploaded
  files are never imported.
- Phase 3A does not claim exact replayability.
