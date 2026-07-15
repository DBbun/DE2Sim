# DE2Sim Architecture

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
tests/
  __init__.py
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

## Preserved Boundaries

Phase 1B intentionally does not implement:

- ASOT creation
- AI behavior generation
- simulation generation
- Godot export
- packaging
- deployment
- full SysML v2 semantic validation
- PDF, DOCX, XLSX, or binary CAD parsing

Future phases will add those capabilities under `de2sim/` while keeping the
legacy DBbun CLI operational. Unsupported files remain listed in the manifest
instead of being dropped.
