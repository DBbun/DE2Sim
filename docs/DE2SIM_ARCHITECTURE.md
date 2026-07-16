# DE2Sim Architecture

## Phase 2B Scope

Phase 2B builds and validates an ASOT from the Phase 1 engineering-package
outputs. It remains dependency-free and uses only the Python standard library.
The legacy DBbun content-to-simulator script remains unchanged.

Phase 2B adds:

- `de2sim/asot/builder.py`
- `--build-asot` on the Challenge II CLI
- `asot.json`
- `asot_summary.md`
- `asot_validation.json`
- `docs/ASOT_BUILD_MAPPING.md`

`--build-asot` automatically performs secure ZIP ingestion, manifest writing,
structured artifact parsing, parsed artifact writing, ASOT construction, and
ASOT validation:

```text
python -m de2sim.cli.challenge_pipeline --engineering-package package.zip --output out --build-asot
```

The command prints the generated paths for `package_manifest.json`,
`parsed_artifacts.json`, `asot.json` or `asot_invalid.json`,
`asot_summary.md`, and `asot_validation.json`.

Phase 2B does not implement formal Phase 3 provenance, AI-generated behaviors,
simulation generation, Godot export, packaging, deployment, or CAD parsing.

## Phase 2A Scope

Phase 2A adds the versioned Authoritative Source of Truth (ASOT) schema,
deterministic JSON I/O, and structural validation. It remains dependency-free
and uses Python dataclasses plus the standard library only. The legacy DBbun
content-to-simulator script remains unchanged.

Phase 2A does not build ASOT records from parsed artifacts, compute provenance
hashes, generate AI behavior, run simulations, export Godot projects, package
outputs, or continue to Phase 2B.

## Phase 1B Scope

Phase 1B builds on Phase 1A secure engineering-package ingestion by adding
optional deterministic structured-artifact parsing. The legacy DBbun
content-to-simulator script remains unchanged.

The legacy entry point remains:

```text
paper_to_simulator_builder_v3_4.py
```

The new Challenge II scaffold entry point is:

```text
python -m de2sim.cli.challenge_pipeline
```

## Current Package Layout

```text
de2sim/
  __init__.py
  cli/
    __init__.py
    challenge_pipeline.py
  ingest/
    __init__.py
    artifact_parser.py
    geometry_manifest.py
    package_reader.py
    parameter_reader.py
    physical_model_reader.py
    requirement_reader.py
    sysml_v2_reader.py
  asot/
    __init__.py
    builder.py
    schema.py
    io.py
    validators.py
tests/
  __init__.py
  test_asot_builder.py
  test_asot_cli.py
  test_asot_io.py
  test_asot_schema.py
  test_asot_validation.py
  test_artifact_parser.py
  test_geometry_manifest.py
  test_package_reader.py
  test_parameter_reader.py
  test_phase0_scaffold.py
  test_physical_model_reader.py
  test_requirement_reader.py
  test_sysml_v2_reader.py
  fixtures/
    README.md
```

## Phase 1A Behavior

The Challenge CLI supports `--version`, `--engineering-package PATH`, and
`--output PATH`. Phase 1B adds optional `--parse-artifacts`.

`--version` reports the scaffold version. Running without
`--engineering-package` returns a controlled nonzero error. Running with an
engineering package requires `--output` and performs Phase 1A ingestion:

- validate that the package exists, is a regular `.zip` file, and is a valid
  ZIP archive
- reject unsafe archive members, including absolute paths, drive-qualified
  paths, `..` traversal, paths resolving outside the extraction directory, and
  symbolic-link-like entries when detectable
- extract files only to `<output>/work/package/`
- refuse to overwrite an existing nonempty extraction directory
- generate `<output>/package_manifest.json`

The manifest records package-level metadata and one sorted entry per extracted
file. Entries include relative path, role, extension, media type, size, SHA-256,
parser status, and warnings. Geometry files are recorded as references with
`parser_status` set to `referenced_not_parsed`; Phase 1A does not parse or
interpret geometry files as CAD.

Recognized roles are:

- `geometry`
- `sysml`
- `requirements`
- `parameters`
- `physical_model`
- `documentation`
- `unsupported`

## Phase 1B Behavior

Running the CLI with `--parse-artifacts` performs Phase 1A ingestion first and
then parses supported structured artifacts from the extracted package:

```text
python -m de2sim.cli.challenge_pipeline --engineering-package package.zip --output out --parse-artifacts
```

The command writes:

- `<output>/package_manifest.json`
- `<output>/parsed_artifacts.json`

The parser is deterministic where source evidence is deterministic: records are
sorted, stable IDs are hash-derived from normalized source evidence, and parser
failures become warnings rather than unhandled tracebacks. Phase 1B supports a
narrow documented set of CSV, JSON, TXT, Markdown, simple YAML, textual SysML,
and `.sysml.json` inputs. Deferred files are recorded in `deferred_files`.

See `docs/DE2SIM_SUPPORTED_INPUTS.md` for the precise supported and deferred
formats.

## Phase 2A Behavior

The ASOT package is available as a standalone library layer:

```text
de2sim.asot.schema
de2sim.asot.io
de2sim.asot.validators
```

The supported ASOT schema version is `de2sim.asot.v1`. ASOT JSON contains
metadata, components, requirements, interfaces, parameters, physical models,
behaviors, geometry, provenance placeholders, and validation state. Engineering
entities use deterministic stable IDs derived from normalized content and entity
type rather than random UUIDs.

JSON I/O is deterministic, UTF-8, pretty-printed, and uses atomic file
replacement. Structural validation returns errors and warnings separately and
does not mutate the supplied ASOT. Validation detects duplicate IDs,
unsupported schema versions, missing required top-level fields, broken
references, invalid component hierarchy, invalid component/interface links,
invalid ownership, and invalid behavior approval status.

See `docs/ASOT_SCHEMA.md` for field-level schema details.

## Phase 2B Behavior

Running the CLI with `--build-asot` performs Phase 1A ingestion and Phase 1B
artifact parsing even when `--parse-artifacts` is not supplied. Existing
`--parse-artifacts` behavior is preserved.

The ASOT builder maps only explicit source evidence:

- requirements from parsed requirement records with text
- parameters from parsed parameter records
- components from SysML `part`, `part def`, and `package`
- interfaces from SysML `port`, `port def`, and `connect`
- physical models from explicit equation records
- behaviors from SysML `action` and `action def`
- geometry references from package-manifest geometry entries
- preliminary source references from file/locator/parser evidence

Unresolved relationships become warnings. Missing ownership and unknown fields
remain empty instead of being inferred.

If ASOT validation reports errors, the CLI writes `asot_invalid.json` and
`asot_validation.json`, then returns a controlled nonzero exit code. Validation
warnings still permit `asot.json`.

## Preserved Boundaries

Phase 2B intentionally does not implement:

- AI behavior generation
- simulation generation
- Godot export
- packaging
- deployment
- full SysML v2 semantic validation
- PDF, DOCX, XLSX, or binary CAD parsing
- formal Phase 3 provenance hashing or detailed lineage

Future phases will add those capabilities under `de2sim/` while keeping the
legacy DBbun CLI operational. Unsupported files remain listed in the manifest
instead of being dropped.
