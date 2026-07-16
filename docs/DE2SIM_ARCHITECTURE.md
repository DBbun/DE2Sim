# DE2Sim Architecture

## Phase 4B Scope

Phase 4B refines the offline behavior proposal provider without adding
simulation execution, Godot export, generated executable code, or automatic
approval. The legacy DBbun script remains unchanged.

When explicit ASOT evidence includes a low-battery return-to-base requirement,
a battery-threshold parameter, and a source-derived `ReturnToBase` behavior or
equivalent explicit action, the offline provider emits a single operational
UAS proposal named `Low Battery Return-to-Base`. The state-machine order is
`preflight -> mission_flight -> return_to_base -> landed`, guards use symbolic
parameter names, source-derived behaviors are linked, and unresolved ownership
is listed as an assumption rather than inferred.

When the required evidence is absent, Phase 4B preserves Phase 4A generic
offline proposal behavior and records a controlled warning describing the
missing UAS evidence. Duplicate component definitions and instances with the
same normalized name are suppressed for generic proposals.

The behavior review page renders states in transition order, keeps transition
labels clear of state circles, shows linked source-derived behaviors, and
badges deterministic offline proposals as not generative AI.

## Phase 4A Scope

Phase 4A adds AI-assisted behavior proposals, local human review, and explicit
approval decisions. It does not implement simulations, Godot export, or
automatic approval of generated content.

Phase 4A adds:

- `de2sim/behaviors/`
- `de2sim/visualization/behavior_review.py`
- `--propose-behaviors`
- `--ai-provider offline|openai|anthropic`
- `--apply-behavior-decisions PATH_TO_JSON`
- `behavior_prompt.json`
- `behavior_proposals.json`
- `behavior_review.html`
- `behavior_generation_report.json`
- `behavior_decisions.json`
- `asot_with_approved_behaviors.json`
- `behavior_approval_report.json`

`--propose-behaviors` automatically performs secure ZIP ingestion, artifact
parsing, ASOT construction, ASOT validation, provenance construction,
traceability validation, and proposal generation:

```text
python -m de2sim.cli.challenge_pipeline --engineering-package package.zip --output out --propose-behaviors
```

The default provider is `offline`, which creates deterministic demonstration
candidates from explicit ASOT requirements, parameters, physical models, source
provenance, and existing source-derived behaviors. Offline candidates are
labeled `generated_by = "offline_template"` and are not described as
generative-AI output.

The standalone `behavior_review.html` uses native SVG and local JavaScript only.
It allows a reviewer to download decisions JSON. The browser does not modify
`asot.json`; decisions must be applied through the CLI:

```text
python -m de2sim.cli.challenge_pipeline --output out --apply-behavior-decisions out/behavior_decisions.json
```

Only approved proposals enter `asot_with_approved_behaviors.json`. Rejected and
needs-revision proposals remain in the approval report. Existing source-derived
behaviors are preserved, and proposed behavior content is never executed or
evaluated.

## Phase 3C Scope

Phase 3C improves the interactive ASOT traceability viewer without changing
pipeline behavior, ASOT construction, provenance construction, or the legacy
DBbun script.

Phase 3C adds viewer polish only:

- deterministic collapsed layered graph layout
- automatic visible-node bounds calculation and fit-to-canvas behavior
- `Fit graph`, zoom in, zoom out, reset, wheel zoom, and drag pan controls
- larger readable labels, safe tooltip text, node legend, node-type colors,
  deterministic node shapes, directional edge markers, and selection fading
- `Show engineering only` and `Show traceability` modes
- clearer details-panel sections and explicit `No source evidence available`
  messaging
- package-scoped wording: `Traceability coverage for this processed package`
- responsive three-panel layout with independently scrolling side panels

Phase 3C does not implement AI behavior generation, simulation generation,
Godot export, ZIP deployment packaging, exact replayability, CAD parsing, or
field-complete provenance.

## Phase 3B Scope

Phase 3B adds a standalone interactive ASOT traceability viewer. It remains
dependency-free and uses only the Python standard library plus embedded HTML,
CSS, and JavaScript. The legacy DBbun content-to-simulator script remains
unchanged.

Phase 3B adds:

- `de2sim/visualization/traceability_viewer.py`
- `--build-viewer` on the Challenge II CLI
- `asot_traceability_viewer.html`
- `viewer_data.json`
- `docs/TRACEABILITY_VIEWER.md`

`--build-viewer` automatically performs secure ZIP ingestion, artifact parsing,
ASOT construction, ASOT validation, provenance construction, traceability
validation, and viewer generation:

```text
python -m de2sim.cli.challenge_pipeline --engineering-package package.zip --output out --build-viewer
```

The generated HTML is standalone and opens locally without a web server. It
embeds normalized viewer data directly in the page and writes the same data to
`viewer_data.json`. Graph nodes and edges are derived only from explicit ASOT
and provenance relationships.

Phase 3B does not implement AI behavior generation, simulation generation,
Godot export, ZIP deployment packaging, exact replayability, CAD parsing, or
field-complete provenance.

## Phase 3A Scope

Phase 3A adds formal provenance and source traceability. It remains
dependency-free and uses only the Python standard library. The legacy DBbun
content-to-simulator script remains unchanged.

Phase 3A adds:

- `de2sim/provenance/hashing.py`
- `de2sim/provenance/trace.py`
- `de2sim/provenance/manifest.py`
- `--build-provenance` on the Challenge II CLI
- `provenance_manifest.json`
- `traceability_report.json`
- `traceability_report.md`
- `docs/PROVENANCE_MODEL.md`

`--build-provenance` automatically performs secure ZIP ingestion, artifact
parsing, ASOT construction, ASOT validation, provenance construction, and
traceability validation:

```text
python -m de2sim.cli.challenge_pipeline --engineering-package package.zip --output out --build-provenance
```

The command prints generated paths for `package_manifest.json`,
`parsed_artifacts.json`, `asot.json`, `asot_summary.md`,
`asot_validation.json`, `provenance_manifest.json`,
`traceability_report.json`, and `traceability_report.md`.

Phase 3A does not implement AI behavior generation, simulation generation,
Godot export, ZIP deployment packaging, exact replayability, or complete
field-level provenance.

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
  provenance/
    __init__.py
    hashing.py
    trace.py
    manifest.py
  visualization/
    __init__.py
    behavior_review.py
    traceability_viewer.py
  behaviors/
    __init__.py
    approval.py
    prompt_builder.py
    proposal_generator.py
    providers.py
    schema.py
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
  test_provenance_cli.py
  test_provenance_hashing.py
  test_provenance_manifest.py
  test_provenance_trace.py
  test_traceability_viewer.py
  test_traceability_viewer_cli.py
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

## Phase 3A Behavior

Running the CLI with `--build-provenance` performs Phase 1A ingestion, Phase 1B
artifact parsing, Phase 2B ASOT construction and validation, and then builds a
formal provenance manifest plus traceability reports.

The provenance manifest records source file checksums, parser status, ASOT
checksums, deterministic provenance records, referenced entity IDs, conservative
coverage counts, and warnings. Source files and provenance records are sorted
deterministically. The only runtime-varying provenance field is
`generated_at_utc`.

Traceability validation checks duplicate provenance IDs, broken ASOT and
provenance references, missing files, checksum mismatches, unsupported evidence
types, and invalid confidence values. Warnings are separated from errors.
Validation errors return a controlled nonzero exit code.

Whole-file and geometry-file provenance is valid source traceability, but it is
reported separately from precise row, line, JSON, YAML, or SysML evidence.

## Phase 3B Behavior

Running the CLI with `--build-viewer` performs every earlier required stage,
including provenance and traceability validation, then writes
`asot_traceability_viewer.html` and `viewer_data.json`.

The viewer shows header metrics, category navigation, an interactive native SVG
relationship graph, entity details, source evidence, search and filters,
traceability summary, traceability gaps, and explicit limitations. It uses no
external assets or libraries and does not execute or evaluate uploaded source
content.

## Phase 3C Behavior

The Phase 3C viewer keeps the Phase 3B data model and relationship rules but
uses the central graph canvas more effectively. It calculates visible graph
bounds on initial load and after filtering, fits the active graph into the SVG
viewport, supports zoom and pan controls, and highlights direct relationships
on hover or selection while fading unrelated graph elements.

The navigation panel filters by category and `System Overview` restores all
entity types. `Show engineering only` hides provenance and source-file nodes
without inventing replacement relationships; `Show traceability` restores the
full provenance/source view.

## Preserved Boundaries

Phase 4A intentionally does not implement:

- simulation generation
- Godot export
- packaging
- deployment
- exact replayability
- complete field-level provenance
- full SysML v2 semantic validation
- PDF, DOCX, XLSX, or binary CAD parsing

Future phases will add those capabilities under `de2sim/` while keeping the
legacy DBbun CLI operational. Unsupported files remain listed in the manifest
instead of being dropped.
