# DE2Sim Architecture

## Phase 1A Scope

Phase 1A adds secure engineering-package ingestion and deterministic
package-manifest generation while preserving the existing DBbun
content-to-simulator script.

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
    geometry_manifest.py
    package_reader.py
tests/
  __init__.py
  test_geometry_manifest.py
  test_package_reader.py
  test_phase0_scaffold.py
  fixtures/
    README.md
```

## Phase 1A Behavior

The Challenge CLI supports `--version`, `--engineering-package PATH`, and
`--output PATH`.

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

## Preserved Boundaries

Phase 1A intentionally does not implement:

- ASOT creation
- AI behavior generation
- simulation generation
- Godot export
- packaging
- deployment

Future phases will add those capabilities under `de2sim/` while keeping the
legacy DBbun CLI operational. Unsupported files remain listed in the manifest
instead of being dropped.
