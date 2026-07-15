# DE2Sim Implementation Plan

Plan target: adapt the existing DBbun content-to-simulator application into an Army Training Verse Challenge II Intelligent Simulation Pipeline.

Non-goals for this plan:

- Do not rewrite `paper_to_simulator_builder_v3_4.py` from scratch.
- Do not break the current DBbun CLI, input handling, simulator bundle generation, validation, documentation, or patent-aware flow.
- Do not claim multi-engine export, live CAD round-trip, full SysML repository integration, or high-fidelity physics beyond what the phases explicitly implement.
- Initially support one target engine only: Godot.

Architectural direction:

- Preserve `paper_to_simulator_builder_v3_4.py` as the legacy-compatible DBbun CLI entry point.
- Move new Challenge II functionality into modular Python packages under `de2sim/`.
- Add a separate Challenge II CLI entry point so the existing content-to-simulator workflow remains operational.
- Reuse existing extraction, AI invocation, offline fallback, generated simulator, validation, documentation, and bundle-writing logic where it is practical.
- Treat the normalized Authoritative Source of Truth (ASOT) as the stable bridge between ingested engineering evidence, AI-assisted enrichment, simulation generation, Godot export, validation, and packaging.

## Proposed Package Layout

The phases below introduce these packages incrementally:

```text
de2sim/
  __init__.py
  cli/
    __init__.py
    challenge_pipeline.py
  ingest/
    __init__.py
    package_reader.py
    geometry_manifest.py
    sysml_v2_reader.py
    requirement_reader.py
    parameter_reader.py
    physical_model_reader.py
  asot/
    __init__.py
    schema.py
    builder.py
    io.py
    validators.py
  provenance/
    __init__.py
    hashing.py
    trace.py
    manifest.py
  ai/
    __init__.py
    behavior_generator.py
    approval.py
  simulate/
    __init__.py
    fidelity.py
    low_fidelity.py
    higher_fidelity.py
    godot_runtime_contract.py
  godot/
    __init__.py
    project_writer.py
    scene_writer.py
    script_writer.py
    asset_writer.py
  packaging/
    __init__.py
    launcher.py
    bundle.py
  demos/
    __init__.py
    uas_demo.py
tests/
  ...
examples/
  uas_demo_package/
  ...
```

## Phase 0 - Repository Restructuring and Test Baseline

1. Objective.

Establish a safe modular structure and test baseline before adding Challenge II behavior. Confirm the existing DBbun application still runs in its current form.

2. Existing code to reuse.

- `resolve_inputs()`, `extract_file()`, extraction helpers, `build_bundle()`, `_run_simulator()`, `validate_bundle()`, `_write_readme()`, `_write_notice()`, and `write_documentation_pdf()` in `paper_to_simulator_builder_v3_4.py`.
- Existing optional dependency behavior and offline fallback behavior.

3. Exact files to create.

- `de2sim/__init__.py`
- `de2sim/cli/__init__.py`
- `de2sim/cli/challenge_pipeline.py`
- `tests/test_legacy_cli_baseline.py`
- `tests/test_challenge_cli_smoke.py`
- `tests/fixtures/README.md`
- `docs/DE2SIM_ARCHITECTURE.md`

4. Exact existing files to modify.

- `paper_to_simulator_builder_v3_4.py`: no functional changes in this phase unless a guarded import helper is needed. If modified, only add small adapter functions that expose existing extraction/build operations to the new package.

5. Input and output formats.

- Input: existing DBbun inputs remain unchanged.
- New CLI input: `--engineering-package <path.zip>` is stubbed but not functional yet.
- Output: existing DBbun bundle remains unchanged. Challenge CLI emits a clear "not implemented yet" status JSON for smoke testing.

6. Automated tests.

- Verify `python paper_to_simulator_builder_v3_4.py --version` succeeds.
- Verify the new Challenge CLI starts and rejects missing packages with a controlled error.
- Verify no phase creates output files outside the requested output directory.

7. Completion criteria.

- Existing DBbun CLI remains operational.
- New package imports cleanly.
- Smoke tests pass without installing packages.
- No Challenge II functionality is represented as complete.

8. Risks and mitigations.

- Risk: refactoring breaks the monolithic application.
- Mitigation: keep Phase 0 mostly additive and wrap existing functions instead of moving them.
- Risk: tests accidentally rely on unavailable optional packages.
- Mitigation: use text/CSV fixtures and offline paths only.

9. Challenge II requirements addressed.

- Establishes foundation for an incremental Intelligent Simulation Pipeline.
- Protects continuity of existing DBbun functionality.

10. Estimated relative effort.

Small.

## Phase 1 - Digital Engineering Package Ingestion

1. Objective.

Ingest a ZIP engineering package containing geometry, structured SysML v2 information, requirements, parameters, and physical-model documentation. Produce a deterministic package manifest without yet building the full ASOT.

2. Existing code to reuse.

- `resolve_inputs()` path validation concepts.
- `extract_file()`, `extract_text_file()`, `extract_json_file()`, `extract_csv()`, `extract_excel()`, and document extraction helpers for package contents that are already supported.
- `_safe_slug()` for stable output naming.

3. Exact files to create.

- `de2sim/ingest/package_reader.py`
- `de2sim/ingest/geometry_manifest.py`
- `de2sim/ingest/sysml_v2_reader.py`
- `de2sim/ingest/requirement_reader.py`
- `de2sim/ingest/parameter_reader.py`
- `de2sim/ingest/physical_model_reader.py`
- `de2sim/ingest/__init__.py`
- `tests/test_package_reader.py`
- `tests/test_geometry_manifest.py`
- `tests/test_sysml_v2_reader.py`
- `tests/fixtures/engineering_package_minimal.zip`

4. Exact existing files to modify.

- `de2sim/cli/challenge_pipeline.py`: wire real package ingestion behind `--engineering-package`.
- `paper_to_simulator_builder_v3_4.py`: none.

5. Input and output formats.

- Input: `.zip` containing any subset of:
  - Geometry: `.glb`, `.gltf`, `.obj`, `.stl`
  - SysML v2: `.sysml`, `.sysml.json`, `.json`
  - Requirements: `.csv`, `.json`, `.yaml`, `.yml`, `.md`, `.txt`, `.pdf`, `.docx`
  - Parameters: `.csv`, `.json`, `.yaml`, `.yml`, `.xlsx`
  - Physical-model documentation: `.pdf`, `.docx`, `.md`, `.txt`
- Output: `package_manifest.json` with:
  - package hash
  - extracted file list
  - file roles
  - media type
  - byte size
  - checksum
  - relative path
  - parser status
  - warnings

6. Automated tests.

- Read a minimal ZIP and classify files by extension and declared folder.
- Reject unsafe ZIP paths such as absolute paths or `..`.
- Confirm unsupported files are preserved in the manifest but marked unsupported.
- Confirm GLB/OBJ/STL are recorded as geometry references, not parsed as CAD.

7. Completion criteria.

- A valid engineering ZIP produces `package_manifest.json`.
- Unsafe archives are rejected.
- No geometry conversion, SysML completeness, or simulation export is claimed.

8. Risks and mitigations.

- Risk: ZIP ingestion can write outside the workspace.
- Mitigation: sanitize every archive member and extract only under the output work directory.
- Risk: SysML v2 appears in multiple practical forms.
- Mitigation: support a narrow initial subset: textual `.sysml` and JSON-like structured exports with explicit warnings for unknown constructs.

9. Challenge II requirements addressed.

- Supports DE package ingestion.
- Recognizes required artifact types: geometry, SysML v2 information, requirements, parameters, and physical-model documentation.

10. Estimated relative effort.

Medium.

## Phase 2 - Authoritative Source of Truth Data Model

1. Objective.

Build a normalized ASOT model with components, requirements, interfaces, parameters, physical models, behaviors, geometry references, and provenance placeholders.

2. Existing code to reuse.

- Existing `SimulationSpec` concepts: parameters, state variables, scenarios, domain summary, backend rationale.
- Existing JSON write/read patterns for `Spec.json`.
- Existing extraction summaries from Phase 1.

3. Exact files to create.

- `de2sim/asot/schema.py`
- `de2sim/asot/builder.py`
- `de2sim/asot/io.py`
- `de2sim/asot/validators.py`
- `de2sim/asot/__init__.py`
- `tests/test_asot_schema.py`
- `tests/test_asot_builder.py`
- `tests/test_asot_validation.py`
- `docs/ASOT_SCHEMA.md`

4. Exact existing files to modify.

- `de2sim/cli/challenge_pipeline.py`: add `build-asot` stage and write ASOT outputs.
- `paper_to_simulator_builder_v3_4.py`: none.

5. Input and output formats.

- Input: `package_manifest.json` plus parsed Phase 1 artifact records.
- Output:
  - `asot.json`
  - `asot_summary.md`
- ASOT JSON top-level fields:
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

6. Automated tests.

- Validate required top-level ASOT fields.
- Confirm stable IDs are generated for components, requirements, parameters, interfaces, and geometry references.
- Confirm missing optional sections produce warnings, not crashes.
- Confirm invalid references fail validation.

7. Completion criteria.

- A minimal valid engineering package produces a normalized ASOT.
- ASOT validation catches broken internal references.
- Existing DBbun `Spec.json` remains separate from Challenge II `asot.json`.

8. Risks and mitigations.

- Risk: ASOT schema becomes too broad too early.
- Mitigation: define the smallest useful schema and version it as `asot_schema_version`.
- Risk: source files contain incomplete engineering information.
- Mitigation: allow explicit `unknown`, `assumed`, and `not_provided` values with validation warnings.

9. Challenge II requirements addressed.

- Establishes an Authoritative Source of Truth.
- Normalizes components, requirements, interfaces, parameters, physical models, behaviors, geometry references, and provenance fields.

10. Estimated relative effort.

Large.

## Phase 3 - Provenance and Source Traceability

1. Objective.

Attach source traceability to ASOT records, including file checksums, extracted evidence references, parser versions, and field-level provenance where available.

2. Existing code to reuse.

- Existing DBbun `_dbbun` metadata pattern in `Spec.json`.
- Existing patent claim-source traceability prompt concepts.
- Existing validation report file patterns.

3. Exact files to create.

- `de2sim/provenance/hashing.py`
- `de2sim/provenance/trace.py`
- `de2sim/provenance/manifest.py`
- `de2sim/provenance/__init__.py`
- `tests/test_provenance_hashing.py`
- `tests/test_traceability.py`
- `docs/PROVENANCE_MODEL.md`

4. Exact existing files to modify.

- `de2sim/asot/schema.py`: add formal provenance record types.
- `de2sim/asot/builder.py`: populate provenance on ASOT fields.
- `de2sim/asot/validators.py`: validate provenance references.
- `de2sim/cli/challenge_pipeline.py`: write `provenance_manifest.json`.
- `paper_to_simulator_builder_v3_4.py`: none.

5. Input and output formats.

- Input: Phase 1 package manifest, extracted source snippets, ASOT records.
- Output:
  - `provenance_manifest.json`
  - ASOT `provenance` entries with:
    - source file ID
    - checksum
    - parser name/version
    - source path inside package
    - optional page, row, JSON pointer, line range, or SysML element ID
    - confidence and extraction status

6. Automated tests.

- Confirm identical files produce identical checksums.
- Confirm each ASOT requirement, parameter, geometry reference, and physical model has at least one provenance reference or an explicit `not_provided` marker.
- Confirm invalid provenance IDs fail ASOT validation.

7. Completion criteria.

- Every ASOT entity has traceability status.
- Package-level and field-level provenance are written.
- No replay guarantee is claimed unless prompt/model metadata is actually captured in later phases.

8. Risks and mitigations.

- Risk: PDF/DOCX source spans are imprecise.
- Mitigation: start with file/page-level provenance and only add coordinates where extraction supports them.
- Risk: provenance makes ASOT hard to read.
- Mitigation: keep provenance records normalized and referenced by ID.

9. Challenge II requirements addressed.

- Provides source traceability and provenance suitable for audit and validation.

10. Estimated relative effort.

Medium.

## Phase 4 - AI-Assisted Behavior and Attribute Generation

1. Objective.

Use AI to propose missing behaviors and attributes from the ASOT and source evidence, while requiring human approval before any AI-generated behavior is exported.

2. Existing code to reuse.

- `call_claude_analysis()`, `call_openai_analysis()`, `_build_analysis_prompt()`, `_parse_llm_json()`, `_offline_spec()`, and provider selection patterns.
- Existing offline keyword fallback approach.
- Existing prompt style that requests structured JSON.

3. Exact files to create.

- `de2sim/ai/behavior_generator.py`
- `de2sim/ai/approval.py`
- `de2sim/ai/__init__.py`
- `tests/test_behavior_generator_offline.py`
- `tests/test_behavior_approval.py`
- `docs/AI_APPROVAL_WORKFLOW.md`

4. Exact existing files to modify.

- `de2sim/asot/schema.py`: add `approval_status`, `generated_by`, and `generation_rationale` fields for behaviors and attributes.
- `de2sim/asot/validators.py`: reject export when AI-generated behaviors are not approved.
- `de2sim/cli/challenge_pipeline.py`: add `generate-behaviors`, `list-pending-approvals`, and `approve-behavior` commands.
- `paper_to_simulator_builder_v3_4.py`: none.

5. Input and output formats.

- Input: `asot.json`, `provenance_manifest.json`, optional API keys using existing provider conventions.
- Output:
  - `behavior_candidates.json`
  - updated `asot.json` only after approval
- Behavior candidate fields:
  - `candidate_id`
  - `target_component_id`
  - `behavior_type`
  - `state_variables`
  - `parameters_used`
  - `trigger_conditions`
  - `outputs`
  - `source_evidence`
  - `confidence`
  - `approval_status`

6. Automated tests.

- Confirm offline generation can produce deterministic placeholder candidates for fixtures.
- Confirm unapproved candidates cannot be exported to simulation or Godot.
- Confirm approval writes an audit record with user, timestamp, and candidate ID.
- Confirm generated fields retain source evidence links.

7. Completion criteria.

- AI candidates are separated from approved ASOT content.
- Export validators block unapproved AI-generated behaviors.
- Human approval state is persisted.

8. Risks and mitigations.

- Risk: AI invents unsupported behavior.
- Mitigation: require source evidence, confidence, and human approval before export.
- Risk: approval workflow becomes cumbersome.
- Mitigation: provide CLI review commands and concise candidate summaries.

9. Challenge II requirements addressed.

- AI-assisted behavior and attribute generation.
- Human approval gate before AI-generated behaviors are exported.

10. Estimated relative effort.

Medium.

## Phase 5 - Low- and Higher-Fidelity Simulation Generation

1. Objective.

Generate two simulation fidelities from the same ASOT: a low-fidelity deterministic/kinematic model and a higher-fidelity model that includes more detailed dynamics or subsystem interactions where ASOT data supports them.

2. Existing code to reuse.

- `_build_codegen_prompt()`, `call_claude_codegen()`, `call_openai_codegen()`, `_offline_codegen()`, `_run_simulator()`, `_check_csv()`, `_check_figures()`, `_check_parameters()`, `_check_logic()`, `_fidelity_score()`, and `validate_bundle()`.
- Existing simulator output expectations: CSV, summary JSON, PNG figures.

3. Exact files to create.

- `de2sim/simulate/fidelity.py`
- `de2sim/simulate/low_fidelity.py`
- `de2sim/simulate/higher_fidelity.py`
- `de2sim/simulate/godot_runtime_contract.py`
- `de2sim/simulate/__init__.py`
- `tests/test_fidelity_selection.py`
- `tests/test_low_fidelity_generation.py`
- `tests/test_higher_fidelity_generation.py`
- `docs/SIMULATION_FIDELITY.md`

4. Exact existing files to modify.

- `de2sim/asot/schema.py`: add `simulation_models` metadata.
- `de2sim/asot/validators.py`: validate enough data exists for each requested fidelity.
- `de2sim/cli/challenge_pipeline.py`: add `generate-simulations` stage.
- `paper_to_simulator_builder_v3_4.py`: optional adapter only if reused code must be called without invoking the legacy bundle path.

5. Input and output formats.

- Input: approved `asot.json`.
- Output:
  - `sim/low/Simulator.py`
  - `sim/low/simulation_outputs.csv`
  - `sim/low/summary.json`
  - `sim/high/Simulator.py`
  - `sim/high/simulation_outputs.csv`
  - `sim/high/summary.json`
  - `simulation_manifest.json`
- Shared runtime contract:
  - `time_s`
  - `entity_id`
  - `component_id`
  - state fields
  - event fields
  - fidelity label

6. Automated tests.

- Confirm both fidelity generators consume the same ASOT fixture.
- Confirm outputs include the required runtime contract fields.
- Confirm higher-fidelity generation fails gracefully when required parameters are missing.
- Confirm generated simulators can run using only available project dependencies.

7. Completion criteria.

- The same ASOT produces low- and higher-fidelity simulator artifacts.
- Fidelity limits are documented in the manifest.
- Validation distinguishes "higher fidelity generated" from "physically authoritative high fidelity."

8. Risks and mitigations.

- Risk: higher fidelity is overstated.
- Mitigation: label it "higher-fidelity" and document assumptions, missing parameters, and model limitations.
- Risk: generated code quality varies.
- Mitigation: reuse existing validation and regeneration patterns where available.

9. Challenge II requirements addressed.

- Generates two fidelities from one ASOT.
- Supports low- and higher-fidelity simulation paths without claiming unsupported full physics.

10. Estimated relative effort.

Large.

## Phase 6 - Godot Project Export

1. Objective.

Export the approved ASOT and simulation runtime contract to a Godot project with scene structure, assets, scripts, and metadata for one target engine: Godot.

2. Existing code to reuse.

- Existing generated simulator output contract from Phase 5.
- Existing bundle output directory patterns.
- Existing geometry references from Phase 1 and ASOT geometry records.

3. Exact files to create.

- `de2sim/godot/project_writer.py`
- `de2sim/godot/scene_writer.py`
- `de2sim/godot/script_writer.py`
- `de2sim/godot/asset_writer.py`
- `de2sim/godot/__init__.py`
- `tests/test_godot_project_writer.py`
- `tests/test_godot_scene_writer.py`
- `tests/test_godot_export_approval_gate.py`
- `docs/GODOT_EXPORT.md`

4. Exact existing files to modify.

- `de2sim/simulate/godot_runtime_contract.py`: finalize runtime data consumed by Godot.
- `de2sim/asot/validators.py`: enforce approval gate before export.
- `de2sim/cli/challenge_pipeline.py`: add `export-godot` stage.
- `paper_to_simulator_builder_v3_4.py`: none.

5. Input and output formats.

- Input:
  - approved `asot.json`
  - `simulation_manifest.json`
  - referenced `.glb`, `.gltf`, `.obj`, or `.stl` geometry
- Output Godot project:
  - `godot/project.godot`
  - `godot/scenes/Main.tscn`
  - `godot/scenes/components/*.tscn`
  - `godot/scripts/simulation_player.gd`
  - `godot/scripts/asot_loader.gd`
  - `godot/data/asot.json`
  - `godot/data/simulation_manifest.json`
  - `godot/assets/geometry/...`

6. Automated tests.

- Confirm required Godot files are written.
- Confirm exported data includes only approved behaviors.
- Confirm scene files reference copied assets using Godot-compatible relative paths.
- Confirm unsupported geometry is listed in export warnings rather than silently dropped.

7. Completion criteria.

- A Godot project folder opens as a project structure.
- Export includes ASOT data, simulation data, scripts, scenes, and geometry references where available.
- No Unity, Unreal, WebGL, or multi-engine support is claimed.

8. Risks and mitigations.

- Risk: OBJ/STL import behavior depends on Godot version and import settings.
- Mitigation: prefer GLB/GLTF when available and document warnings for other formats.
- Risk: generated Godot scenes become too complex.
- Mitigation: start with one main scene, component nodes, asset references, and a simple simulation playback script.

9. Challenge II requirements addressed.

- Provides the initial target-engine export path.
- Restricts scope to Godot as required.

10. Estimated relative effort.

Large.

## Phase 7 - Automated Packaging and Launch

1. Objective.

Create a repeatable package containing ASOT, simulations, Godot export, provenance, validation outputs, and launcher scripts. Provide a controlled launch path without claiming a compiled game export unless Godot export tooling is actually configured.

2. Existing code to reuse.

- `_write_readme()`, `_write_notice()`, `_unique_output_dir()`, and output bundle conventions.
- Existing generated validation/documentation patterns.

3. Exact files to create.

- `de2sim/packaging/bundle.py`
- `de2sim/packaging/launcher.py`
- `de2sim/packaging/__init__.py`
- `tests/test_bundle_packaging.py`
- `tests/test_launcher_generation.py`
- `docs/PACKAGING_AND_LAUNCH.md`

4. Exact existing files to modify.

- `de2sim/cli/challenge_pipeline.py`: add `package` and `launch` stages.
- `paper_to_simulator_builder_v3_4.py`: none.

5. Input and output formats.

- Input:
  - `asot.json`
  - `provenance_manifest.json`
  - `simulation_manifest.json`
  - Godot project folder
  - validation reports
- Output:
  - `de2sim_package.zip`
  - `README.md`
  - `NOTICE.txt`
  - `launch_godot_project.ps1`
  - `launch_godot_project.bat`
  - `package_manifest.json`

6. Automated tests.

- Confirm ZIP contains required artifacts.
- Confirm launcher scripts reference relative paths.
- Confirm package manifest checksums match packaged files.
- Confirm packaging fails if unapproved AI behaviors are present in exportable content.

7. Completion criteria.

- One command packages the Challenge II pipeline outputs.
- Windows launch scripts are generated.
- Packaging does not require installing packages.

8. Risks and mitigations.

- Risk: local Godot executable path varies.
- Mitigation: launcher accepts `GODOT_EXE` environment variable and otherwise gives a clear message.
- Risk: ZIP contains stale files from previous runs.
- Mitigation: build package from an explicit manifest, not by blindly zipping the output directory.

9. Challenge II requirements addressed.

- Automated packaging and launch.
- Supports a Windows-friendly launch path.

10. Estimated relative effort.

Medium.

## Phase 8 - UAS Demonstration Package

1. Objective.

Provide one representative UAS demonstration package that exercises ingestion, ASOT creation, provenance, AI-assisted behavior approval, two-fidelity simulation generation, Godot export, packaging, and launch.

2. Existing code to reuse.

- All prior Challenge II modules.
- Existing DBbun documentation style for human-readable outputs where useful.

3. Exact files to create.

- `de2sim/demos/uas_demo.py`
- `de2sim/demos/__init__.py`
- `examples/uas_demo_package/README.md`
- `examples/uas_demo_package/sysml/uas.sysml`
- `examples/uas_demo_package/requirements/requirements.csv`
- `examples/uas_demo_package/parameters/uas_parameters.json`
- `examples/uas_demo_package/physical_models/flight_model.md`
- `examples/uas_demo_package/geometry/README.md`
- `tests/test_uas_demo.py`
- `docs/UAS_DEMONSTRATION.md`

4. Exact existing files to modify.

- `de2sim/cli/challenge_pipeline.py`: add `create-uas-demo` or `--demo uas` option.
- `paper_to_simulator_builder_v3_4.py`: none.

5. Input and output formats.

- Input: representative UAS demo source files. Geometry may initially be a simple placeholder GLB if available or a documented geometry reference placeholder if no real asset is included.
- Output:
  - `uas_engineering_package.zip`
  - `asot.json`
  - low- and higher-fidelity simulation outputs
  - Godot project
  - packaged demo ZIP
  - UAS demo validation summary

6. Automated tests.

- Confirm demo package can be generated.
- Confirm demo package passes Phase 1 ingestion.
- Confirm ASOT contains UAS components such as airframe, propulsion, power, flight controller, sensor payload, datalink, and ground control interface.
- Confirm simulations run and produce expected output files.
- Confirm Godot export is blocked until AI-generated behaviors, if any, are approved.

7. Completion criteria.

- A representative UAS demo exercises the full implemented pipeline.
- The demo is honest about simplified models and placeholder assets.
- The demo can be rebuilt from repository files.

8. Risks and mitigations.

- Risk: demo data appears operationally sensitive.
- Mitigation: use generic, non-sensitive, synthetic UAS parameters and simple toy requirements.
- Risk: placeholder geometry weakens demonstration.
- Mitigation: document geometry status clearly and prefer an included simple, non-sensitive GLB when practical.

9. Challenge II requirements addressed.

- Provides one representative UAS demonstration.
- Demonstrates DE package to ASOT to two fidelities to Godot package.

10. Estimated relative effort.

Medium.

## Phase 9 - Validation, Security, Documentation, and Windows Launcher

1. Objective.

Harden the pipeline with validation gates, security checks, documentation, and Windows launcher behavior suitable for a Challenge II demonstration package.

2. Existing code to reuse.

- `_run_simulator()`, `_check_csv()`, `_check_figures()`, `_check_parameters()`, `_check_logic()`, `_check_data_quality()`, `_fidelity_score()`, `validate_bundle()`, `_write_validation_txt()`, and documentation generation concepts.
- Existing warnings around unsupported optional dependencies.

3. Exact files to create.

- `de2sim/security.py`
- `de2sim/validation.py`
- `tests/test_security_zip_safety.py`
- `tests/test_export_validation_gates.py`
- `tests/test_windows_launcher_paths.py`
- `docs/VALIDATION_SECURITY_AND_OPERATIONS.md`
- `docs/CHALLENGE_II_USER_GUIDE.md`
- `docs/CHALLENGE_II_DEVELOPER_GUIDE.md`

4. Exact existing files to modify.

- `de2sim/cli/challenge_pipeline.py`: add final `validate-all` command and stricter exit codes.
- `de2sim/packaging/launcher.py`: finalize Windows launcher behavior.
- `de2sim/packaging/bundle.py`: include validation and security reports.
- `de2sim/asot/validators.py`: enforce final export requirements.
- `paper_to_simulator_builder_v3_4.py`: none unless legacy helper reuse requires a non-behavioral import guard.

5. Input and output formats.

- Input: full pipeline output directory.
- Output:
  - `validation_report.json`
  - `validation_report.md`
  - `security_report.json`
  - `windows_launch_report.txt`
  - final packaged ZIP

6. Automated tests.

- Confirm unsafe ZIP paths are rejected.
- Confirm unsupported external references are reported.
- Confirm unapproved AI behaviors fail final validation.
- Confirm missing Godot export fails packaging with a clear error.
- Confirm Windows scripts quote paths with spaces.
- Confirm legacy DBbun CLI still passes baseline smoke tests.

7. Completion criteria.

- Final validation reports are produced.
- Security checks cover archive extraction, path traversal, generated script paths, and export approval gates.
- User and developer documentation explain actual supported capabilities and known limitations.
- Windows launcher scripts are tested for path construction.

8. Risks and mitigations.

- Risk: documentation overstates maturity.
- Mitigation: maintain a "supported now" and "not yet supported" section.
- Risk: validation cannot prove physical correctness.
- Mitigation: validate structural consistency, runnable outputs, traceability, approval status, and documented assumptions rather than claiming authoritative physics validation.

9. Challenge II requirements addressed.

- Validation, security, documentation, and Windows launcher.
- Demonstrates a controlled, auditable pipeline without unsupported capability claims.

10. Estimated relative effort.

Medium.

## Cross-Phase Acceptance Gates

- `paper_to_simulator_builder_v3_4.py --version` remains functional after every phase.
- Existing DBbun content-to-simulator bundle generation remains available.
- New Challenge II functionality is placed under `de2sim/` packages.
- ASOT is the source for both simulation fidelities.
- AI-generated behaviors are never exported unless approved.
- Godot remains the only target engine until an explicit later phase adds another target.
- Tests use local fixtures and do not require package installation.
- The implementation documents unsupported capabilities instead of implying them.
