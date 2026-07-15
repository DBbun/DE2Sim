# DE2Sim ASOT Schema

Phase 2A defines a versioned, dependency-free Authoritative Source of Truth
(ASOT) JSON document. It does not build ASOT records from parsed artifacts,
compute provenance hashes, generate AI behavior, run simulations, export Godot,
or package outputs.

## Schema Version

The supported schema version is:

```text
de2sim.asot.v1
```

An ASOT document contains these required top-level fields:

- `schema_version`
- `asot_id`
- `metadata`
- `components`
- `requirements`
- `interfaces`
- `parameters`
- `physical_models`
- `behaviors`
- `geometry`
- `provenance`
- `validation`

Optional sections may be empty lists.

## Metadata

`metadata` contains:

- `title`
- `created_at_utc`
- `source_package_filename`
- `source_package_sha256`
- `parsed_artifacts_sha256`
- `generator_name`
- `generator_version`

## Common Engineering Entity Fields

Components, requirements, interfaces, parameters, physical models, behaviors,
and geometry records contain:

- `stable_id`
- `name`
- `description`
- `source_references`
- `status`
- `warnings`

Stable IDs are deterministic SHA-256-derived identifiers based on normalized
content and entity type. Phase 2A does not use random UUIDs.

## Entity-Specific Fields

Components add:

- `component_type`
- `parent_component_id`
- `child_component_ids`
- `interface_ids`
- `parameter_ids`
- `behavior_ids`
- `geometry_ids`

Requirements add:

- `requirement_id`
- `text`
- `verification_method`
- `priority`
- `satisfied_by_ids`
- `verified_by_ids`

Interfaces add:

- `interface_type`
- `source_component_id`
- `target_component_id`
- `port_names`
- `direction`
- `exchanged_items`

Parameters add:

- `value`
- `unit`
- `minimum`
- `maximum`
- `symbolic_expression`
- `owning_component_id`

Physical models add:

- `equation`
- `variables`
- `parameter_ids`
- `assumptions`
- `owning_component_ids`

Behaviors add:

- `behavior_type`
- `states`
- `triggers`
- `actions`
- `owning_component_id`
- `generated_by`
- `approval_status`

Supported `approval_status` values are `not_required`, `pending`, `approved`,
and `rejected`.

Geometry records add:

- `source_relative_path`
- `geometry_format`
- `owning_component_id`
- `parser_status`
- `coordinate_system`
- `unit`

Provenance records are placeholders in Phase 2A, but support:

- `provenance_id`
- `source_relative_path`
- `source_sha256`
- `source_locator`
- `parser_name`
- `confidence`

## JSON I/O

`de2sim.asot.io` writes deterministic, UTF-8, pretty-printed JSON and uses
atomic file replacement. Malformed JSON produces controlled `ASOTIOError`
exceptions.

## Structural Validation

`de2sim.asot.validators.validate_asot()` reports errors and warnings
separately and never mutates the supplied ASOT. It detects duplicate IDs,
unsupported schema versions, missing required top-level fields, broken
references, invalid component hierarchy, invalid component/interface links,
invalid parameter, behavior, geometry, and model ownership, and invalid behavior
approval status.
