# DE2Sim Repository Audit

Audit target: `paper_to_simulator_builder_v3_4.py`

Scope note: this repository currently contains a single Python application file. This audit is based on the code in that file only.

## 1. Application Entry Point and UI Framework

The application entry point is `main()`, guarded by:

```python
if __name__ == "__main__":
    main()
```

The application is a command-line interface built with Python's standard `argparse` module. It does not use a web UI or desktop UI framework such as Streamlit, Gradio, Flask, FastAPI, Tkinter, PyQt, or Godot.

Primary CLI flags:

- `--input` / `-i`: one or more input files or directories.
- `--output` / `-o`: output directory base.
- `--anthropic-key`: Anthropic API key override.
- `--openai-key`: OpenAI API key override.
- `--patent`: force patent-processing mode.
- `--validate`: run validation after bundle generation.
- `--model`: override the active AI model.
- `--version`: print version and exit.

The orchestration path is:

1. `main()` parses CLI arguments and environment variables.
2. `resolve_inputs()` expands files/directories.
3. `build_bundle()` performs extraction, analysis, code generation, execution, validation, documentation, and input-file copying.

## 2. Supported Uploads

Inputs are local files or directories supplied through `--input`. Directories are scanned one level deep for known extensions.

Supported file groups:

- Documents: `.pdf`, `.docx`
- Tabular data: `.csv`, `.xlsx`, `.xls`
- Plain text and markup: `.txt`, `.md`, `.rst`, `.tex`, `.rtf`, `.log`
- Structured text/config: `.json`, `.yaml`, `.yml`, `.xml`, `.html`, `.htm`, `.toml`, `.ini`, `.cfg`
- Source code: `.py`, `.r`, `.m`, `.jl`, `.c`, `.cpp`, `.h`, `.hpp`, `.java`, `.js`, `.ts`, `.go`, `.rs`, `.scala`, `.sh`, `.bat`, `.ps1`
- Images: `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.tiff`, `.tif`, `.webp`

Extraction dispatch is handled by `extract_file()`. PDFs use PyMuPDF when available, then pypdf fallback. DOCX uses `python-docx`. Excel uses `openpyxl`. Images are base64 encoded for multimodal AI analysis. CSV and text-like files are read into text summaries.

Unknown file extensions can still be accepted by `resolve_inputs()` if they are files, but they are processed as best-effort plain text.

## 3. How AI Is Invoked

The application supports three provider modes:

- Claude via Anthropic SDK when an Anthropic key and package are available.
- OpenAI via OpenAI SDK when an OpenAI key and package are available.
- Offline keyword/template mode when no supported API path is available.

Provider selection priority:

1. `--anthropic-key` or `ANTHROPIC_API_KEY` with installed `anthropic`
2. `--openai-key` or `OPENAI_API_KEY` with installed `openai`
3. Offline mode

Default model constants:

- `CLAUDE_MODEL = "claude-sonnet-4-6"`
- `OPENAI_MODEL = "gpt-5.4-mini"`

The `--model` flag mutates the active model constant based on prefix heuristics. OpenAI token arguments are selected by `_openai_token_kwargs()`, which uses `max_completion_tokens` for newer OpenAI model families and `max_tokens` otherwise.

AI is used in four main ways:

- Analysis: `_build_analysis_prompt()` or `_build_patent_analysis_prompt()` creates a multimodal prompt requesting a structured JSON simulation spec.
- Code generation: `_build_codegen_prompt()` asks the model to create a complete runnable Python simulator from the spec.
- Regeneration: `_build_regen_prompt()` feeds quality failures and previous code back into the model for one retry when output quality is too low.
- Data quality assessment: `_check_data_quality()` optionally asks the same provider to assess generated CSV behavior against the spec.

Claude calls use `client.messages.create()`. OpenAI calls use `client.chat.completions.create()`. Both codegen paths include continuation loops to handle truncated model output.

Patent mode changes the analysis prompt substantially. It front-loads claims, classifies independent/dependent claims, asks for claim constraints, relationships, and claim-source traceability, then instructs generated simulators to enforce constraints.

## 4. How Outputs Are Generated

### Simulation Spec

The simulation spec is produced either by AI analysis or `_offline_spec()`. It is written as `Spec.json` with added metadata:

- `_provider`
- `_dbbun.tool`
- `_dbbun.version`
- `_dbbun.generated_by`
- `_dbbun.run_id`
- `_dbbun.timestamp_utc`
- `_dbbun.copyright`

The spec schema includes titles, domain summary, backend recommendation, state variables, parameters, scenario plan, figure plan, dataset schema, simulator logic, keywords, categories, abstract, value proposition, and data formats. Patent specs also include patent metadata, claim constraints, claim-source fields, and relationships.

### Simulator Code

The generated simulator code is created through:

- `call_claude_codegen()`
- `call_openai_codegen()`
- `_offline_codegen()`

Before writing, `_dbbun_sim_header()` prepends a legal/provenance header. The result is written to `Simulator.py`.

The generated simulator is instructed to:

- Use `numpy`, `matplotlib`, `csv`, `json`, `pathlib`, `dataclasses`, and `typing`.
- Define `MODEL_PROFILE`.
- Run all scenarios.
- Generate CSV datasets and PNG figures.
- Save `summary.json`.
- Support `--output`.

### Datasets and Figures

After writing `Simulator.py`, `build_bundle()` always executes it through `_run_simulator()`:

```text
python Simulator.py --output <bundle>/sim_outputs
```

Expected generated outputs in `sim_outputs/`:

- `simulation_outputs.csv`
- `scenario_summary.csv`
- `parameters_used.csv`
- `summary.json`
- `*.png` figures

The prompt requires these files, but actual production depends on the generated simulator code. The build step checks whether CSV or PNG files exist and can trigger one regeneration round for low quality or missing outputs.

### Documentation

`write_documentation_pdf()` creates `Documentation.pdf` using ReportLab. It includes bundle metadata, source files, abstract/value proposition, parameters, state variables, scenarios, figures with explanations, validation summary when available, and usage guidance.

Important implementation note: `_install_reportlab()` attempts to install ReportLab with pip if the import fails. That is inconsistent with a no-install execution policy, but this audit did not execute the builder and did not install anything.

### README and Notice

`_write_readme()` writes `README.txt`, describing the generated bundle, source files, simulation backend, scenarios, parameters, and run instructions.

`_write_notice()` writes `NOTICE.txt` with ownership and synthetic-output notices.

### Input Copying

At the end of `build_bundle()`, input files are copied into an `input/` subdirectory of the output bundle.

### ZIP Bundles

No ZIP archive generation is implemented in the audited code. There is no use of `zipfile`, `shutil.make_archive()`, or an equivalent archive writer. The code creates an output directory bundle, not a `.zip` bundle.

### Scene3D / Interactive HTML

The module header describes `Scene3D.html`, Three.js generation, recording mode, and a `--no-3d` flag. The implementation searched in this file does not contain the actual Scene3D generation functions, `scene_3d_plan` handling, HTML writer, or `--no-3d` CLI argument. As implemented, the bundle path does not generate `Scene3D.html`.

## 5. Environment Variables and Dependencies

Environment variables:

- `ANTHROPIC_API_KEY`: used when `--anthropic-key` is not supplied.
- `OPENAI_API_KEY`: used when `--openai-key` is not supplied.

Standard-library dependencies:

- `argparse`
- `base64`
- `json`
- `re`
- `shutil`
- `sys`
- `textwrap`
- `dataclasses`
- `pathlib`
- `typing`
- `csv`
- `datetime`
- `uuid`
- `subprocess`

Optional extraction and AI dependencies:

- `fitz` / PyMuPDF
- `pypdf`
- `anthropic`
- `openai`
- `docx` / python-docx
- `openpyxl`
- `pytesseract`
- `PIL` / Pillow

Generated simulator dependencies:

- `numpy`
- `matplotlib`

Documentation dependency:

- `reportlab`

The source header mentions `pip install anthropic openai pymupdf pypdf`, but the actual optional imports go beyond that list.

## 6. Reusable Components for an Intelligent Digital Engineering-to-Simulation Pipeline

Reusable components already present:

- File ingestion router: `resolve_inputs()` and `extract_file()` provide a practical local-file ingestion layer.
- Multimodal document extraction: PDF text, OCR fallback, figure extraction, tables, images, DOCX, CSV, Excel, structured text, source code.
- Patent-aware analysis: patent detection, claims extraction, independent/dependent claim classification, and claim-first prompting.
- Intermediate simulation spec: `Spec.json` acts as a machine-readable bridge between source documents and generated execution artifacts.
- Backend classification: the spec captures a recommended simulation backend such as dynamical system, agent-based, network diffusion, fluid dynamics, or custom.
- Scenario planning: `scenario_plan` provides a reusable structure for experiment/simulation campaigns.
- Parameter and state variable extraction: parameter/state schemas are useful as early engineering-model abstractions.
- Code generation prompt contracts: `_build_codegen_prompt()` encodes strong requirements for runnable code, data outputs, plotting, defensive behavior, and scenario differentiation.
- Execution harness: `_run_simulator()` turns generated source into material datasets and figures.
- Validation layer: `_check_csv()`, `_check_figures()`, `_check_parameters()`, `_check_logic()`, `_check_data_quality()`, and `_fidelity_score()` provide a foundation for automated quality gates.
- Regeneration loop: quality findings can be fed back into codegen for repair.
- Documentation generator: `write_documentation_pdf()` converts spec and outputs into a human-readable engineering report.
- Bundle metadata: `_dbbun` metadata gives each run an ID and timestamp.

These pieces can support the front half of an Intelligent Digital Engineering-to-Simulation Pipeline: ingest evidence, extract design/simulation concepts, generate an executable surrogate, run scenarios, evaluate outputs, and document results.

## 7. Missing Capabilities

### CAD

Missing or incomplete:

- No CAD ingestion for STEP, IGES, STL, OBJ, 3MF, glTF, FBX, DXF, DWG, SLDPRT, CATIA, or similar formats.
- No geometry kernel, meshing pipeline, units normalization, assembly hierarchy, materials, tolerances, coordinate frames, or constraints.
- No mapping from document-derived parameters to geometric features.
- No CAD export or round-trip capability.

### SysML v2

Missing or incomplete:

- No SysML v2 parser, textual syntax support, API integration, or model repository integration.
- No blocks/parts/ports/connectors/requirements/constraints mapping.
- No parametric analysis graph or executable constraint network derived from SysML.
- No traceability between SysML model elements and generated simulator variables.

### ASOT

Missing or incomplete:

- No explicit ASOT schema, ontology, or model exchange format is implemented.
- No typed engineering object graph beyond the ad hoc simulation spec JSON.
- No formal concept of architecture, system, operational thread, test objective, or verification artifact.
- No ASOT-to-simulation or simulation-to-ASOT synchronization layer.

### Provenance

Partially present:

- The bundle records `_dbbun` metadata, run ID, provider, timestamp, and simple parameter source labels.
- Patent mode asks for claim-source traceability.
- Validation reports include fidelity/data quality summaries.

Missing or incomplete:

- No per-field source spans, page coordinates, figure/table bounding boxes, hashes, or citation anchors.
- No immutable provenance graph.
- No input file checksums.
- No prompt/version capture sufficient for exact replay.
- No model response metadata, token accounting, or API request IDs.
- No dataset row-level lineage from source evidence, parameters, scenario, and simulator code version.

### Multiple Fidelities

Partially present:

- Validation computes a high/medium/low fidelity score for generated outputs.

Missing or incomplete:

- No explicit multi-fidelity model architecture.
- No low/medium/high simulator variants.
- No surrogate versus physics model distinction.
- No mesh/time-step/solver fidelity controls.
- No calibration ladder from analytic approximation to numerical simulation to empirical validation.
- No uncertainty quantification or formal sensitivity analysis framework beyond scenarios.

### Godot Export

Missing or incomplete:

- No Godot project generation.
- No `.tscn`, `.gd`, `.godot`, asset import, or scene-tree writer.
- No mapping from spec/state variables to Godot nodes, signals, UI controls, animation, or runtime simulation scripts.
- No 3D asset export path suitable for Godot.
- No interactive executable export targets.

The header advertises Three.js Scene3D generation, but the audited implementation does not contain an active Scene3D writer. Even if restored, Three.js HTML output would not be equivalent to Godot export without a dedicated Godot scene and script generation backend.
