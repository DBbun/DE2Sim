# DE2Sim Architecture

## Phase 0 Scope

Phase 0 establishes a modular package boundary for the Challenge II DE2Sim
pipeline while preserving the existing DBbun content-to-simulator script.

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
tests/
  __init__.py
  test_phase0_scaffold.py
  fixtures/
    README.md
```

## Phase 0 Behavior

The Challenge CLI supports `--version`, `--engineering-package PATH`, and
`--output PATH`.

In Phase 0, `--version` reports the scaffold version. Running without
`--engineering-package` returns a controlled nonzero error. Running with an
existing package path confirms the scaffold is installed and explicitly reports
that package ingestion is not implemented yet.

The scaffold does not parse, extract, copy, or write engineering-package
contents. The `--output` option is accepted for interface stability, but Phase 0
does not create pipeline output files.

## Preserved Boundaries

Phase 0 intentionally does not implement:

- engineering-package ingestion
- ASOT creation
- AI behavior generation
- simulation generation
- Godot export
- packaging
- deployment

Future phases will add these capabilities under `de2sim/` while keeping the
legacy DBbun CLI operational.
