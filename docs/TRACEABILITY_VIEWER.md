# DE2Sim ASOT Traceability Viewer

Phase 3C polishes the standalone, dependency-free ASOT traceability viewer:

```text
python -m de2sim.cli.challenge_pipeline --engineering-package package.zip --output out --build-viewer
```

The command automatically runs secure ZIP ingestion, artifact parsing, ASOT
construction, ASOT validation, provenance construction, traceability
validation, and viewer generation.

It writes:

- `asot_traceability_viewer.html`
- `viewer_data.json`

The HTML file embeds the same normalized data as `viewer_data.json` and opens
locally by double-clicking. It does not require a web server, external scripts,
stylesheets, fonts, images, APIs, CDNs, or network access.

## Phase 3C Viewer Layout

The interactive graph uses deterministic layered SVG layout:

- source files
- provenance records
- components
- interfaces and behaviors
- parameters, requirements, physical models, and geometry

Empty layers are collapsed. On initial load and after search, filtering, or
category changes, the viewer calculates the visible node bounds and fits the
graph into the central SVG canvas. The toolbar includes zoom in, zoom out,
reset, and a clearly labeled `Fit graph` control. Mouse-wheel zoom and
drag-to-pan are supported, with pan bounds clamped so the graph cannot be lost
permanently outside the viewport.

The graph uses larger readable labels, deterministic node shapes, directional
edge markers, relationship-specific edge classes, hover tooltips, direct-edge
highlighting, and selection fading for unrelated nodes and edges. Long labels
are visually truncated in the graph but remain available in the native tooltip,
safe hover tooltip, and entity details panel.

The three-panel layout gives the navigation panel roughly 15% of the width,
the graph roughly 60%, and the details panel roughly 25% on common desktop
viewports. Side panels scroll independently while the graph remains fixed.

## Navigation and Modes

Category navigation filters to the selected entity type. `System Overview`
restores all entity types and keeps category counts visible. The selected
category remains highlighted.

`Show engineering only` hides provenance and source-file nodes and their
traceability edges while preserving existing engineering-to-engineering
relationships. `Show traceability` restores provenance and source-file nodes
and edges. Existing search, precision filtering, warning filtering, and type
filters are preserved.

The traceability metric is labeled explicitly as `Traceability coverage for
this processed package`; it is not presented as a general Challenge II
compliance claim.

## Viewer Data

`viewer_data.json` contains:

- `schema_version`
- `generated_at_utc`
- `metadata`
- `metrics`
- `nodes`
- `edges`
- `source_files`
- `traceability_gaps`
- `validation`
- `limitations`

`generated_at_utc` is the only runtime timestamp. Entity, source-file, node,
edge, and graph-layout ordering is deterministic for identical normalized
inputs.

Evidence text is embedded only from provenance records and is truncated to
`1200` characters. Truncation is represented by `evidence_text_truncated` and a
visible `[truncated]` marker.

## Relationship Rules

The graph includes only explicit ASOT or provenance relationships:

- component to child component, interface, parameter, behavior, or geometry
- requirement to satisfied-by or verified-by entity
- physical model to parameter
- component to physical model when explicit ownership exists
- entity to provenance record
- provenance record to source file

Missing ownership, missing requirement links, unknown SysML relationships, and
unresolved references are not inferred.

## Security Boundaries

The viewer:

- renders dynamic values with safe DOM text assignment
- does not use `eval`, `exec`, `Function()`, or dynamic script construction
- does not use `document.write`
- does not execute source content
- does not evaluate equations
- does not load external URLs
- does not follow links contained in uploaded data
- avoids unrelated absolute paths by preserving source-relative paths only
- escapes embedded JSON so source text cannot terminate the data script

## Limitations

- narrow SysML subset
- geometry referenced but not parsed
- no AI-generated behaviors yet
- no simulation generated yet
- no Godot export yet
- whole-file provenance is not field-level provenance
- no exact replayability claim
