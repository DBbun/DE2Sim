# DE2Sim

DE2Sim converts standards-based digital-engineering artifacts (CAD-export
geometry, a SysMLv2 subset, parametric data) into an Authoritative Source
of Truth (ASOT), AI-assisted behavior proposals reviewed and approved by a
human, and executable low- and high-fidelity simulation output — packaged
as a self-contained, offline-runnable browser demo.

Originally developed for the Army Training Verse Prize Challenge II
("Intelligent Simulation Pipeline").

## Layout

- `de2sim/` — the pipeline package (ingest, geometry, ASOT, provenance,
  behaviors, simulation, visualization, CLI, demo packaging).
- `docs/` — architecture notes and phase-by-phase build documentation.
- `tests/` — unit tests for each pipeline stage.
- `paper_to_simulator_builder_v3_4.py` — the legacy content-to-simulator
  builder this project builds on; preserved unchanged.
- `demo_outputs/canonical/` — canonical example run: the source engineering
  package, local-AI/ASOT output, simulation output, and the final packaged
  submission demo (open `submission_package/DE2Sim_Submission_Demo.zip`,
  extract, and open `demo_dashboard.html` — no Python, internet, or GPU
  required to view it).

## License

Licensed under the **DBbun Source-Available License v1.0** (see
[`LICENSE`](LICENSE)): free for genuine academic research use. Any
commercial or government use — including evaluation, internal deployment,
or use under a government contract, grant, or prize challenge — requires
a separate license from DBbun LLC. Contact contact@dbbun.com.
