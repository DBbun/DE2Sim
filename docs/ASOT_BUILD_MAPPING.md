# Phase 2B ASOT Build Mapping

Phase 2B builds `asot.json` from the Phase 1 outputs:

- `package_manifest.json`
- `parsed_artifacts.json`

The builder is conservative. It copies explicit source evidence into ASOT
records and leaves unknown ownership, direction, exchanged items, and
relationships empty unless the parsed records contain direct evidence.

## Metadata

- `title` comes from explicit package metadata when present. Otherwise it uses
  the ZIP filename stem.
- `source_package_filename` and `source_package_sha256` come from the package
  manifest.
- `parsed_artifacts_sha256` is the SHA-256 of `parsed_artifacts.json`.
- `generator_name` is `de2sim.asot.builder`.
- `generator_version` is `phase2b`.
- `asot_id` is deterministic and derived from source package identity, parsed
  artifact hash, title, and generator identity.

`created_at_utc` is runtime metadata and may differ between builds.

## Requirements

Parsed requirement records become ASOT requirement records when they contain
explicit requirement text. The builder preserves:

- requirement ID
- title/name
- text
- verification method
- priority
- preliminary source references

Missing requirement text is not generated.

## Parameters

Parsed parameter records become ASOT parameter records when they contain an
explicit name or parameter ID. Numeric values remain JSON numbers. Non-numeric
values are stored as `symbolic_expression`. Units, minimums, maximums, and
descriptions are copied without unit conversion or normalization.

Ownership remains empty unless a future parser supplies explicit supported
ownership evidence.

## SysML Components

Components are created only from explicit SysML component-like elements:

- `part`
- `part def`
- `package`

Parent/owner relationships are added only when the referenced owner resolves to
an ASOT component unambiguously. Other SysML elements are not treated as
components.

## Interfaces

Interfaces are created from explicit:

- `port`
- `port def`
- `connect`

Connect source and target component links are added only when both references
resolve safely. Unresolved references become validation warnings.

## Physical Models

Physical-model records become ASOT physical model records when they contain an
explicit equation. Equations are preserved exactly as text and are never
evaluated. Variables, assumptions, descriptions, and preliminary source
references are copied when present.

## Behaviors

Behaviors are created only from explicit SysML:

- `action`
- `action def`

They are marked as source-derived:

- `generated_by = "source"`
- `approval_status = "approved"`

Phase 2B does not generate AI behaviors.

## Geometry

Every package-manifest geometry entry becomes one ASOT geometry record. The
builder preserves:

- `source_relative_path`
- extension-derived format
- `parser_status = "referenced_not_parsed"`

Phase 2B does not parse CAD or claim geometry conversion.

## Preliminary Provenance

The builder creates file/locator-level preliminary provenance records using:

- source relative path
- source locator
- parser name
- source file SHA-256 when available

This is not field-complete, replayable Phase 3 provenance.

## Relationship Handling

Explicit `satisfy` and `verify` relationships populate requirement
`satisfied_by_ids` and `verified_by_ids` only when the requirement and related
entity resolve safely. Unresolved references are warnings, not invented links.

## Validation Outputs

`--build-asot` writes:

- `asot.json` when validation has no errors
- `asot_invalid.json` when validation has errors
- `asot_summary.md`
- `asot_validation.json`

Warnings do not prevent `asot.json` from being written.
