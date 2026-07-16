# DE2Sim Simulation Viewer

Phase 5A writes `simulation_viewer.html`, a standalone local playback viewer
for precomputed low/high fidelity telemetry. It requires no web server.

The viewer includes the ASOT title, approved behavior ID, scenario assumption
labels, fidelity selector, side-by-side comparison mode, play/pause/reset,
playback speed, scrubber, mission map, home and waypoint markers, animated UAS
marker, traveled path, telemetry readouts, requirement status, event timeline,
battery and speed charts, fidelity comparison, linked ASOT IDs, provenance IDs,
and explicit limitations.

The viewer also shows a simulation-status card for each fidelity: mission
completion, terminal reason, battery reserve at landing, battery depletion
status, scenario feasibility, and requirement results. Scenario and telemetry
fields are rendered with human-readable labels while retaining exact
machine-readable names as secondary text or tooltips.

Security constraints:

- data is embedded as escaped JSON in an `application/json` script element
- dynamic text is written with `textContent`
- native SVG is used for map and charts
- no external libraries, URLs, fonts, scripts, stylesheets, images, or APIs
- no `eval`, `exec`, `Function`, `document.write`, dynamic scripts, or fetches
- no source-provided HTML is rendered

The viewer is a playback surface only. It does not recompute authoritative
simulation results in the browser.
