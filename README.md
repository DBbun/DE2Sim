# DE2Sim

### 🔴 [**Live Demo — dbbun.github.io/DE2Sim**](https://dbbun.github.io/DE2Sim/)
Runs entirely in your browser — dashboard, 3D geometry viewer, simulation
viewer, ASOT traceability, and behavior review. No install, no server, no
internet required after the page loads.

DE2Sim converts standards-based digital-engineering artifacts (CAD-export
geometry, a SysMLv2 subset, parametric data) into an Authoritative Source
of Truth (ASOT), AI-assisted behavior proposals reviewed and approved by a
human, and executable low- and high-fidelity simulation output — packaged
as a self-contained, offline-runnable browser demo.

Originally developed for the Army Training Verse Prize Challenge II
("Intelligent Simulation Pipeline").

## Getting the Code

```bash
git clone https://github.com/DBbun/DE2Sim.git
cd DE2Sim
```

To pick up later changes in an existing clone:

```bash
git pull origin master
```

## Setup

- Python 3.10 or later. The core `de2sim` package is standard-library
  only — no `pip install` required to run the pipeline itself.
- The legacy `paper_to_simulator_builder_v3_4.py` script referenced in
  earlier project history has been removed from this repository; it is
  not part of the current `de2sim` pipeline and is not needed to run
  anything below.
- Optional: to use a local generative-AI provider for behavior
  enrichment (`--ai-provider ollama`), install and run
  [Ollama](https://ollama.com) separately and pull a model (e.g.
  `ollama pull gemma3:4b`). Everything else, including the default
  `--ai-provider offline` mode, needs no external services.

## Quickstart

The repo ships a working example engineering package, so you can run the
full pipeline immediately without preparing your own input:

```bash
python -m de2sim.cli.challenge_pipeline \
  --engineering-package demo_outputs/canonical/engineering_package/DBbun-DE2Sim-DemoUAS-Geometry.zip \
  --output out --build-asot
python -m de2sim.cli.challenge_pipeline --output out --propose-behaviors
python -m de2sim.cli.challenge_pipeline --output out --apply-behavior-decisions out/behavior_decisions.json
python -m de2sim.cli.challenge_pipeline --output out --build-simulation
python -m de2sim.cli.challenge_pipeline --output out --build-demo-package
```

The last step writes a self-contained package under `out/` — open its
`demo_dashboard.html` in any browser to see the result (no server, no
internet connection needed). To skip running the pipeline yourself
entirely, the same kind of output is already built and viewable at the
[live demo](https://dbbun.github.io/DE2Sim/) or under
`demo_outputs/canonical/submission_package/`.

## Running Tests

```bash
python -m unittest discover -s tests
```

## Layout

- `de2sim/` — the pipeline package (ingest, geometry, ASOT, provenance,
  behaviors, simulation, visualization, CLI, demo packaging).
- `docs/` — architecture notes and phase-by-phase build documentation.
- `tests/` — unit tests for each pipeline stage.
- `demo_outputs/canonical/` — canonical example run: the source engineering
  package (also used by the Quickstart above), local-AI/ASOT output,
  simulation output, and the final packaged submission demo (open
  `submission_package/DE2Sim_Submission_Demo.zip`, extract, and open
  `demo_dashboard.html` — no Python, internet, or GPU required to view
  it). The interactive `simulation_viewer.html` lives only under
  `submission_package/.../viewers/` to avoid duplicating an ~4 MB file;
  `simulation_output/` keeps the underlying JSON/CSV data without a
  second copy of the viewer.

## How to Add Engineering Data

DE2Sim is command-line only — there is no upload UI. You provide an
**engineering package**: a ZIP file laid out so `de2sim/ingest/` can
classify its contents by folder name:

```
your_package.zip
├── geometry/        → .stl, .glb, .gltf, .obj
├── sysml/           → .sysml files (SysMLv2)
├── parameters/      → .csv, .json, .yaml, .xlsx
├── physical_models/ → .md, .txt, .json, .yaml
└── requirements/    → .csv, .json, .yaml, .md, .txt
```

Then run the CLI, chaining stages as needed:

```bash
python -m de2sim.cli.challenge_pipeline --engineering-package package.zip --output out --build-asot
python -m de2sim.cli.challenge_pipeline --output out --propose-behaviors
python -m de2sim.cli.challenge_pipeline --output out --apply-behavior-decisions out/behavior_decisions.json
python -m de2sim.cli.challenge_pipeline --output out --build-simulation
python -m de2sim.cli.challenge_pipeline --output out --build-demo-package
```

**Caveat:** only structured formats are actually parsed for content —
`.json`/`.yaml` fully, and `.md`/`.txt` in `physical_models/` only for
lines shaped like `name = equation` or `equation: ...`. `.pdf`/`.docx`
files are accepted and referenced for provenance, but their content is
**not** extracted — `physical_model_reader.py` explicitly returns "reader
does not support" for those extensions. Geometry files are likewise
referenced at ingestion and only actually parsed/validated in the later
`--extract-geometry` stage. In short: bring structured data (CSV/JSON/YAML/
STL/SysML), not a raw spec document you expect the pipeline to read for you.

## License

Licensed under the **DBbun Source-Available License v1.0** (see
[`LICENSE`](LICENSE)): free for genuine academic research use. Any
commercial or government use — including evaluation, internal deployment,
or use under a government contract, grant, or prize challenge — requires
a separate license from DBbun LLC. Contact contact@dbbun.com.
